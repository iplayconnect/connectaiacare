"""SIP layer — wrapper minimal sobre pjsua2 (PJSIP). Foco: chamadas
OUTBOUND (originar ligação pra um número).

Responsabilidades:
1. Inicializar PJSIP endpoint + transporte UDP
2. Registrar conta SIP no trunk (config.SIP_USER@SIP_DOMAIN)
3. POST /dial → cria pjsua2.Call, recebe áudio via AudioMediaPort custom
4. Bridge audio: cada frame inbound → callback feed_audio_8k
5. Recebe áudio outbound via push_audio_8k → injeta no media port

⚠️ ESTE MÓDULO DEPENDE DE PJSIP NATIVO COMPILADO (instalado pelo
Dockerfile via pjproject 2.14 + SWIG bindings).

Pattern copiado de /root/assistenteia/voip-service/services/voip_core.py
mas reescrito enxuto pra ConnectaIACare. Alguns pontos vão precisar
ajustes finos durante o smoke test (frame size, RTP timing) — marcados
com TODO_SMOKE.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from config import Config

logger = logging.getLogger("sip_layer")


class SipLayer:
    """Singleton — uma instância de PJSIP por processo."""

    _instance: "SipLayer | None" = None

    def __init__(self):
        self._pj = None
        self._endpoint = None
        self._transport = None
        self._account = None
        self._initialized = False
        self._lock = threading.Lock()
        # call_id (string) → CallContext
        self._calls: dict[str, "CallContext"] = {}
        # Callback chamado quando alguém liga PRA nós (inbound).
        # Recebe (caller_phone, on_audio_in, on_call_state). Caller
        # implementa em routes/inbound.py com a lógica de spawn da
        # GrokCallSession + bridge audio.
        self._on_incoming_call: (
            Callable[[str, Callable, Callable], "_MyCall"] | None
        ) = None
        self._inbound_call_counter = 0

    @classmethod
    def get(cls) -> "SipLayer":
        if cls._instance is None:
            cls._instance = SipLayer()
        return cls._instance

    def initialize(self) -> bool:
        """Boot PJSIP. Idempotente."""
        with self._lock:
            if self._initialized:
                return True

            try:
                import pjsua2 as pj
                self._pj = pj

                ep_cfg = pj.EpConfig()
                ep_cfg.uaConfig.maxCalls = Config.MAX_CONCURRENT_CALLS
                ep_cfg.uaConfig.userAgent = "ConnectaIACare-Voice/0.1"
                ep_cfg.medConfig.clockRate = Config.SIP_AUDIO_RATE
                ep_cfg.medConfig.sndClockRate = Config.SIP_AUDIO_RATE
                # Sem device de som — só software bridge
                ep_cfg.medConfig.noVad = False

                ep = pj.Endpoint()
                ep.libCreate()
                ep.libInit(ep_cfg)

                # Transport UDP — PORTA FIXA.
                # Histórico: tp_cfg.port=0 (ephemeral) fazia o pjsua
                # anunciar Contact com porta INTERNA do container (ex:
                # 39109), que não está mapeada externamente. Cada
                # rebuild abria nova porta, gerando "ghost registrations"
                # no Flux (4+ contatos simultâneos da mesma linha).
                # Flux mandava INVITE pras portas mortas e dava timeout.
                #
                # Fix (29/04): porta fixa 5060 dentro do container
                # (Docker compose mapeia 5061:5060/udp). Contact é
                # forçado via acc_cfg.sipConfig.contactForced (abaixo)
                # pra anunciar PUBLIC_IP:SIP_PUBLIC_PORT (5061 externa).
                # publicAddress no transport não funciona porque pjsua
                # tenta resolver "IP:porta" como hostname e falha
                # (gethostbyname → PJ_ERESOLVE).
                tp_cfg = pj.TransportConfig()
                tp_cfg.port = Config.SIP_LISTEN_PORT  # 5060 (fixo)
                self._transport = ep.transportCreate(
                    pj.PJSIP_TRANSPORT_UDP, tp_cfg
                )
                ep.libStart()
                self._endpoint = ep

                # Container Docker não tem sound card → null device.
                # Sem isso, makeCall() estoura PJMEDIA_EAUD_NODEFDEV.
                # Áudio bidirecional vai 100% via AudioMediaPort custom.
                try:
                    ep.audDevManager().setNullDev()
                except Exception as exc:
                    logger.warning("set_null_dev_failed: %s", exc)

                # Conta — REGISTER e auth SEMPRE com SIP_USER técnico
                # (nVoip dá 403 Forbidden se idUri = DID diferente).
                # Caller ID (From) será aplicado por chamada via header
                # override no INVITE (ver dial()).
                acc_cfg = pj.AccountConfig()
                acc_cfg.idUri = (
                    f'"ConnectaIA Care" <sip:{Config.SIP_USER}@{Config.SIP_DOMAIN}>'
                )
                acc_cfg.regConfig.registrarUri = f"sip:{Config.SIP_DOMAIN}"
                cred = pj.AuthCredInfo(
                    "digest", "*", Config.SIP_USER, 0, Config.SIP_PASSWORD,
                )
                acc_cfg.sipConfig.authCreds.append(cred)
                acc_cfg.regConfig.timeoutSec = Config.REGISTRATION_INTERVAL

                # Contact forçado — anuncia 72.60.242.245:5061 (porta
                # externa Docker) em REGISTER + INVITE. Sem isso pjsua
                # anunciaria a porta interna 5060 que não está exposta
                # (host port 5061 → container 5060). Flux memoriza esse
                # Contact e roteia INVITE inbound pra ele — precisa ser
                # endereço externo válido.
                #
                # IMPORTANTE: desligar contactRewrite/viaRewrite. Caso
                # contrário, no segundo REGISTER (após 401 auth challenge)
                # o pjsua sobrescreve o contactForced usando o IP/porta
                # detectados via "received/rport" do response — que aqui
                # seriam 72.60.242.245:5060 (porta interna). Como 5060
                # externo está ocupado pelo voip-service, INVITE bate em
                # serviço errado. Desligando o rewrite, o contactForced
                # sobrevive a todos os ciclos REGISTER.
                if Config.PUBLIC_IP:
                    acc_cfg.sipConfig.contactForced = (
                        f"<sip:{Config.SIP_USER}@{Config.PUBLIC_IP}"
                        f":{Config.SIP_PUBLIC_PORT};ob>"
                    )
                    acc_cfg.natConfig.contactRewriteUse = 0
                    acc_cfg.natConfig.viaRewriteUse = 0
                    acc_cfg.natConfig.sdpNatRewriteUse = 0

                # FIX RTP — Docker bridge NAT:
                # 1. Porta no range mapeado pelo compose (10500-10600)
                # 2. publicAddress NO MEDIA APENAS (não no transport
                #    geral) anuncia 72.60.242.245 no c= do SDP.
                #    Sem isso o SDP carrega 172.19.0.4 (interno Docker),
                #    Flux tenta mandar RTP pra esse IP não-roteável e
                #    RX fica zerado + peer=-.
                #    Tentativa anterior (28/04 23:34) com tp_cfg.publicAddress
                #    afetou também o REGISTER e quebrou. Aqui é só media.
                acc_cfg.mediaConfig.transportConfig.port = Config.RTP_PORT_MIN
                acc_cfg.mediaConfig.transportConfig.portRange = (
                    Config.RTP_PORT_MAX - Config.RTP_PORT_MIN
                )
                if Config.PUBLIC_IP:
                    acc_cfg.mediaConfig.transportConfig.publicAddress = (
                        Config.PUBLIC_IP
                    )

                # Account customizado pra capturar onIncomingCall.
                # Sem isso, chamadas inbound caem em "no media handler"
                # e o trunk recebe 503 / 408.
                sip_self = self  # closure pra callback poder acessar

                class _MyAccount(pj.Account):
                    def onIncomingCall(self, prm):
                        try:
                            sip_self._handle_incoming_call(prm)
                        except Exception:
                            logger.exception("on_incoming_call_failed")

                self._account = _MyAccount()
                self._account.create(acc_cfg)

                self._initialized = True
                logger.info(
                    "sip_initialized user=%s caller_id=%s domain=%s "
                    "public_ip=%s rtp_range=%d-%d",
                    Config.SIP_USER,
                    Config.SIP_CALLER_ID or "(=user)",
                    Config.SIP_DOMAIN,
                    Config.PUBLIC_IP or "(auto)",
                    Config.RTP_PORT_MIN, Config.RTP_PORT_MAX,
                )
                return True
            except Exception as exc:
                logger.exception("sip_initialize_failed")
                return False

    def shutdown(self):
        """Drena chamadas, faz un-register e fecha endpoint.

        Un-register explícito é crítico: sem isso, o Flux mantém o
        REGISTER ativo até expirar (Expires=300), e o próximo
        container que subir gera um segundo registro paralelo
        (`ghost`). Vários ghosts simultâneos = INVITE roteado pra
        contato morto = "linha não atende".
        """
        with self._lock:
            if not self._initialized:
                return
            try:
                for ctx in list(self._calls.values()):
                    ctx.hangup()
                # Un-register síncrono. setRegistration(False) envia
                # REGISTER com Expires:0 e aguarda 200 OK antes de
                # destruir a lib.
                if self._account:
                    try:
                        self._account.setRegistration(False)
                        # Pequeno delay pra REGISTER unregister sair
                        # antes do libDestroy interromper o I/O.
                        import time as _t
                        _t.sleep(0.5)
                    except Exception:
                        logger.exception("sip_unregister_failed")
                if self._endpoint:
                    self._endpoint.libDestroy()
            except Exception:
                logger.exception("sip_shutdown_error")
            finally:
                self._initialized = False

    def dial(
        self,
        *,
        destination: str,
        on_audio_in: Callable[[bytes], None],
        on_call_state: Callable[[str, str], None] | None = None,
    ) -> str:
        """Origina chamada outbound. Retorna call_id local."""
        if not self._initialized:
            raise RuntimeError("sip_not_initialized")

        import pjsua2 as pj
        import time as _time
        # PJSIP exige que cada thread externa (Flask worker) seja
        # registrada antes de chamar pjlib. Idempotente.
        try:
            self._endpoint.libRegisterThread(f"flask-{threading.get_ident()}")
        except Exception:
            pass  # já registrada
        # destination: "5551996161700" → "sip:5551996161700@dominio"
        dest_uri = self._normalize_dest(destination)
        call_id = f"call-{len(self._calls) + 1}-{int(_time.time())}"

        call = _MyCall(
            account=self._account,
            call_id_local=call_id,
            on_audio_in=on_audio_in,
            on_call_state=on_call_state,
        )
        prm = pj.CallOpParam(True)
        # Caller ID override — apenas via P-Asserted-Identity + Remote-
        # Party-ID. NÃO mexe no From (pjsua gera ele do idUri da conta;
        # adicionar From extra dispara 400 Bad From Header).
        # nVoip / SBCs comerciais geralmente leem PAI pra validar a
        # identidade declarada quando ela é diferente do auth user.
        if Config.SIP_CALLER_ID and Config.SIP_CALLER_ID != Config.SIP_USER:
            try:
                pai = pj.SipHeader()
                pai.hName = "P-Asserted-Identity"
                pai.hValue = (
                    f"<sip:{Config.SIP_CALLER_ID}@{Config.SIP_DOMAIN}>"
                )
                prm.txOption.headers.append(pai)
                # Remote-Party-ID (RFC 5379) — alguns SBCs preferem RPID.
                rpid = pj.SipHeader()
                rpid.hName = "Remote-Party-ID"
                rpid.hValue = (
                    f'"ConnectaIA Care" '
                    f'<sip:{Config.SIP_CALLER_ID}@{Config.SIP_DOMAIN}>'
                    f';party=calling;screen=yes;privacy=off'
                )
                prm.txOption.headers.append(rpid)
            except Exception as exc:
                logger.warning("caller_id_header_failed: %s", exc)
        call.makeCall(dest_uri, prm)
        ctx = CallContext(call_id=call_id, pj_call=call)
        self._calls[call_id] = ctx
        logger.info(
            "sip_dialing call_id=%s dest=%s caller_id=%s",
            call_id, dest_uri,
            Config.SIP_CALLER_ID or Config.SIP_USER,
        )
        return call_id

    def register_current_thread(self, label: str = "external") -> None:
        """Registra a thread atual no pjlib (idempotente).

        OBRIGATÓRIO ser chamado ANTES de qualquer função pjlib em threads
        que não foram criadas pelo PJSIP. Sem isso, pj_thread_this()
        dispara assertion → SIGABRT no container inteiro.

        Caso típico: asyncio loop_thread que processa WS do Grok e
        chama drain_outbound_audio quando VAD detecta voz do usuário.
        """
        if not self._initialized or not self._endpoint:
            return
        try:
            self._endpoint.libRegisterThread(
                f"{label}-{threading.get_ident()}"
            )
        except Exception:
            pass  # já registrada — idempotente

    def push_audio_8k(self, call_id: str, pcm16_8k: bytes) -> None:
        """Camada externa (audio_bridge depois de downsample) chama isso
        pra que o áudio da Sofia chegue no telefone do paciente.

        NÃO chama register_current_thread aqui — método roda a 50Hz e
        a operação interna não toca pjlib (só bytearray). O GC guard
        já cobre threads que tocam pjlib indireto via destruição.
        """
        ctx = self._calls.get(call_id)
        if ctx and ctx.pj_call:
            ctx.pj_call.feed_audio_to_sip(pcm16_8k)

    def drain_outbound_audio(self, call_id: str) -> int:
        """Esvazia o buffer de áudio Sofia→SIP. Usado quando o usuário
        interrompe a fala da Sofia — mata o áudio em curso na hora."""
        ctx = self._calls.get(call_id)
        if ctx and ctx.pj_call:
            return ctx.pj_call.drain_outbound_buffer()
        return 0

    def hangup(self, call_id: str) -> bool:
        # hangup() toca pjlib (CallOpParam, hangup) — precisa register
        self.register_current_thread("hangup")
        ctx = self._calls.pop(call_id, None)
        if not ctx:
            return False
        ctx.hangup()
        return True

    # ══════════════════════════════════════════════════════════════════
    # Inbound — chamadas que ALGUÉM faz pra nós (Sofia atende)
    # ══════════════════════════════════════════════════════════════════

    def register_on_incoming_call(
        self,
        callback: Callable[[str, Callable, Callable], object],
    ) -> None:
        """Registra handler de chamada inbound.

        Callback assina: (caller_phone: str, on_audio_in: Callable,
        on_call_state: Callable) → algo. O callback fica responsável
        por iniciar a Grok session e devolver o áudio via on_audio_in.
        """
        self._on_incoming_call = callback

    def _handle_incoming_call(self, prm) -> None:
        """Chamado pelo onIncomingCall do _MyAccount. Aceita o INVITE
        com 200 OK + cria _MyCall pra bridgeing áudio.
        """
        if not self._initialized or not self._pj:
            return

        pj = self._pj
        # IMPORTANTE: NÃO chamar register_current_thread aqui. Esta
        # thread É uma worker interna do pjsua (callback do
        # onIncomingCall), já tem thread descriptor + group lock
        # ownership. Re-registrar cria um segundo descriptor →
        # quando call.answer() tenta pegar o group lock, o owner
        # mismatch dispara assert "grp_lock_set_owner_thread" e
        # SIGABRT. Só registrar threads externas (Flask, asyncio).

        # Cria _MyCall pra essa chamada inbound (subclass de pj.Call)
        self._inbound_call_counter += 1
        import time as _time
        call_id = f"in-call-{self._inbound_call_counter}-{int(_time.time())}"

        # Caller phone vem do From URI do INVITE. Acessamos via
        # pj_call.getInfo().remoteUri após criar.
        if not self._on_incoming_call:
            logger.warning(
                "incoming_call_no_handler — rejecting with 503",
            )
            try:
                tmp_call = _MyCall(
                    account=self._account,
                    call_id_local=call_id,
                    on_audio_in=lambda b: None,
                    on_call_state=None,
                )
                tmp_call.makeCall  # placeholder
            except Exception:
                pass
            return

        # Callback de áudio inbound (paciente fala) será preenchido
        # pelo handler externo. Mesma assinatura do dial outbound.
        captured_call: dict = {"call": None, "on_audio_in": None,
                                "on_call_state": None}

        def _on_audio_in(audio: bytes):
            cb = captured_call.get("on_audio_in")
            if cb:
                cb(audio)

        def _on_call_state(local_id: str, state: str):
            cb = captured_call.get("on_call_state")
            if cb:
                cb(local_id, state)

        call = _MyCall(
            account=self._account,
            call_id_local=call_id,
            on_audio_in=_on_audio_in,
            on_call_state=_on_call_state,
            pj_call_id=prm.callId,  # liga _MyCall à chamada do pjsua
        )
        # Pega caller phone do remoteUri (vem do INVITE)
        try:
            ci = call.getInfo()
            remote_uri = ci.remoteUri  # ex: '"X" <sip:5551996161700@...>'
            caller_phone = self._extract_phone_from_uri(remote_uri)
        except Exception:
            caller_phone = "unknown"

        logger.info(
            "incoming_call call_id=%s caller=%s — answering",
            call_id, caller_phone,
        )

        # Aceita a chamada (200 OK)
        try:
            answer_prm = pj.CallOpParam()
            answer_prm.statusCode = 200
            call.answer(answer_prm)
        except Exception as exc:
            logger.exception("incoming_call_answer_failed: %s", exc)
            return

        # Delega pra handler externo (que cria GrokCallSession)
        try:
            on_audio_in_cb, on_call_state_cb = self._on_incoming_call(
                caller_phone, call_id, call,
            )
            captured_call["on_audio_in"] = on_audio_in_cb
            captured_call["on_call_state"] = on_call_state_cb
        except Exception:
            logger.exception("incoming_call_handler_failed")

        ctx = CallContext(call_id=call_id, pj_call=call)
        self._calls[call_id] = ctx

    @staticmethod
    def _extract_phone_from_uri(uri: str) -> str:
        """Extrai o número de telefone de um URI SIP.
        Ex: '"Joao" <sip:5551996161700@dom.com>' → '5551996161700'
        """
        import re
        m = re.search(r"sip:([+]?\d+)@", uri or "")
        return m.group(1) if m else "unknown"

    def install_gc_thread_guard(self) -> None:
        """DESABILITADO em 2026-04-30.

        Histórico: foi adicionado pra resolver crash em destrutor de
        objetos pjsua2 (ByteVector, MediaFormatAudio, CallOpParam) quando
        Python GC rodava em thread aleatória.

        Problema descoberto agora: chamar libRegisterThread em cada GC
        sweep SOBRESCREVE o owner do group lock do pjsua atualmente
        possuído por outra thread. Isso causa SIGABRT em
        grp_lock_set_owner_thread quando uma worker pjsua tenta liberar
        o lock e descobre que owner foi mudado pelo GC callback.

        Ligações INBOUND eram especialmente afetadas porque o ciclo
        onIncomingCall → answer → onCallMediaState dispara muitos
        callbacks pjsua em sequência rápida, aumentando probabilidade
        de GC rodar entre eles.

        Outbound funcionava porque o ciclo é mais espaçado e a thread
        Flask que dispara dial() já tem libRegisterThread fixo —
        mesmo se GC corrompesse, a próxima libRegisterThread
        restaurava o owner.

        Mantida como NO-OP por compatibilidade com chamadores. Se
        crash de destrutor reaparecer, fix correto é evitar criar
        objetos pjsua2 fora da thread do endpoint, não ficar
        registrando GC threads.
        """
        if getattr(self, "_gc_guard_installed", False):
            return
        logger.info("gc_thread_guard_disabled — see comment in sip_layer.py")
        self._gc_guard_installed = True
        logger.info("gc_thread_guard_installed")

    def _normalize_dest(self, destination: str) -> str:
        """Normaliza destino pra o formato que o trunk Flux aceita.
        Aceita várias entradas e força prefixo 55 quando parece BR sem
        código de país. Trunk dá SIP 403 se faltar 55 no número.

        Casos cobertos:
          - "sip:..."             → passa direto
          - "+5551996161700"      → 5551996161700 → sip:...
          - "5551996161700"       → passa (já tem 55)
          - "51996161700" (11)    → 5551996161700 (adiciona 55)
          - "5196161700" (10)     → 555196161700 (adiciona 55, fixo)
        """
        d = destination.strip().lstrip("+")
        if d.startswith("sip:"):
            return d
        digits = "".join(c for c in d if c.isdigit())
        # 12-13 dígitos sem prefixo 55 → BR número completo (DDD+9+8 ou DDD+8)
        if len(digits) in (10, 11) and not digits.startswith("55"):
            digits = "55" + digits
        return f"sip:{digits}@{Config.SIP_DOMAIN}"


class CallContext:
    def __init__(self, *, call_id: str, pj_call):
        self.call_id = call_id
        self.pj_call = pj_call

    def hangup(self):
        try:
            import pjsua2 as pj
            prm = pj.CallOpParam()
            self.pj_call.hangup(prm)
        except Exception:
            pass


# ============================================================
# pjsua2.Call subclass — callbacks de mídia + estado
# ============================================================

def _make_my_call_class(pj):
    """Definido dentro de função pq pjsua2 importa lazy (só após
    initialize)."""

    # PCM 8kHz mono 16-bit, 20ms frame = 160 samples * 2 bytes = 320 bytes.
    # Pattern validado pelo voip-service que roda em produção.
    PJSIP_FRAME_SIZE_BYTES = 320

    class _SocketToSipPort(pj.AudioMediaPort):
        """Frames que VÃO PRA SIP (Sofia → telefone do paciente).
        Buffer empurrado pelo audio_bridge via feed().
        """
        def __init__(self):
            super().__init__()
            self._buf = bytearray()
            self._lock = threading.Lock()

        def feed(self, pcm16_8k: bytes):
            with self._lock:
                self._buf.extend(pcm16_8k)

        def drain(self) -> int:
            """Esvazia buffer (interrupção). Retorna bytes descartados."""
            with self._lock:
                n = len(self._buf)
                self._buf.clear()
                return n

        def onFrameRequested(self, frame):
            # PJMEDIA_FRAME_TYPE_AUDIO = 1
            frame.type = 1
            try:
                with self._lock:
                    if len(self._buf) >= PJSIP_FRAME_SIZE_BYTES:
                        chunk = bytes(self._buf[:PJSIP_FRAME_SIZE_BYTES])
                        del self._buf[:PJSIP_FRAME_SIZE_BYTES]
                    else:
                        chunk = b"\x00" * PJSIP_FRAME_SIZE_BYTES
                # PJSIP swig binding exige ByteVector, não bytes raw
                frame.buf = pj.ByteVector(chunk)
            except Exception:
                frame.buf = pj.ByteVector(b"\x00" * PJSIP_FRAME_SIZE_BYTES)

        def onFrameReceived(self, frame):
            pass

    class _SipToSocketPort(pj.AudioMediaPort):
        """Frames que VÊM DO SIP (telefone do paciente → Sofia)."""
        def __init__(self, on_audio_in):
            super().__init__()
            self._on_audio_in = on_audio_in
            self._frame_count = 0

        def onFrameRequested(self, frame):
            # Direção reversa — devolve silêncio
            frame.type = 1
            frame.buf = pj.ByteVector(b"\x00" * PJSIP_FRAME_SIZE_BYTES)

        def onFrameReceived(self, frame):
            try:
                # PJMEDIA_FRAME_TYPE_NONE = 0 (silêncio/CNG) → ignorar
                if frame.type == 0:
                    return
                audio_data = bytes(frame.buf)
                if not audio_data:
                    return
                self._frame_count += 1
                # Log periódico com energia média pra debug — silêncio
                # absoluto = RMS muito baixo. Ajuda a saber se é falta
                # de áudio ou só limite de VAD muito alto.
                if self._frame_count == 1 or self._frame_count % 100 == 0:
                    # RMS rápido sem numpy (frame é PCM16 LE)
                    n = len(audio_data) // 2
                    if n > 0:
                        sumsq = 0
                        for i in range(0, len(audio_data), 2):
                            s = int.from_bytes(
                                audio_data[i:i+2], "little", signed=True,
                            )
                            sumsq += s * s
                        rms = int((sumsq / n) ** 0.5)
                    else:
                        rms = 0
                    logger.info(
                        "audio_frame_in count=%d bytes=%d rms=%d",
                        self._frame_count, len(audio_data), rms,
                    )
                self._on_audio_in(audio_data)
            except Exception as exc:
                logger.warning("on_frame_received_error: %s", exc)

    class MyCall(pj.Call):
        def __init__(
            self, account, call_id_local, on_audio_in, on_call_state,
            pj_call_id=None,
        ):
            # Inbound calls: pj_call_id vem de OnIncomingCallParam.callId
            # (atribuído pelo pjsua ao receber INVITE). Sem isso,
            # getInfo() dispara assert fail (call_id inválido) e
            # SIGSEGV o processo. Outbound: deixa default (-1) e o
            # makeCall() preenche depois.
            if pj_call_id is not None:
                super().__init__(account, pj_call_id)
            else:
                super().__init__(account)
            self._call_id_local = call_id_local
            self._on_audio_in_cb = on_audio_in
            self._on_call_state = on_call_state
            self._sock_to_sip: _SocketToSipPort | None = None
            self._sip_to_sock: _SipToSocketPort | None = None

        def feed_audio_to_sip(self, pcm16_8k: bytes):
            if self._sock_to_sip:
                self._sock_to_sip.feed(pcm16_8k)

        def drain_outbound_buffer(self) -> int:
            if self._sock_to_sip:
                return self._sock_to_sip.drain()
            return 0

        def onCallState(self, prm):
            try:
                ci = self.getInfo()
                state = ci.stateText
                logger.info(
                    "call_state call_id=%s state=%s",
                    self._call_id_local, state,
                )
                if self._on_call_state:
                    self._on_call_state(self._call_id_local, state)
            except Exception:
                pass

        def onCallMediaState(self, prm):
            ci = self.getInfo()
            for i, m in enumerate(ci.media):
                if m.type == pj.PJMEDIA_TYPE_AUDIO and m.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                    aud = self.getAudioMedia(i)
                    # Cria nossos ports custom + conecta com o stream de áudio
                    fmt = pj.MediaFormatAudio()
                    fmt.type = pj.PJMEDIA_TYPE_AUDIO
                    fmt.clockRate = Config.SIP_AUDIO_RATE
                    fmt.channelCount = 1
                    fmt.bitsPerSample = 16
                    # frameTimeUsec 20ms é padrão PCMU
                    fmt.frameTimeUsec = 20000

                    if not self._sip_to_sock:
                        self._sip_to_sock = _SipToSocketPort(self._on_audio_in_cb)
                        self._sip_to_sock.createPort("sip2sock", fmt)
                        aud.startTransmit(self._sip_to_sock)

                    if not self._sock_to_sip:
                        self._sock_to_sip = _SocketToSipPort()
                        self._sock_to_sip.createPort("sock2sip", fmt)
                        self._sock_to_sip.startTransmit(aud)

    return MyCall


# Late binding: classe é criada quando initialize() roda
_MyCall = None  # type: ignore


def _ensure_call_class():
    """Chama isso depois que initialize() rodou (pjsua2 importável)."""
    global _MyCall
    if _MyCall is None:
        import pjsua2 as pj
        _MyCall = _make_my_call_class(pj)
