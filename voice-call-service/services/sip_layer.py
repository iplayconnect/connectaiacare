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

                # Transport UDP
                tp_cfg = pj.TransportConfig()
                tp_cfg.port = 0  # bind ephemeral local pra signaling
                tp_cfg.portRange = Config.RTP_PORT_MAX - Config.RTP_PORT_MIN
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

                # Conta — display name "ConnectaIA Care" aparece no caller ID
                # do destinatário (quando a operadora preserva o From header).
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

                self._account = pj.Account()
                self._account.create(acc_cfg)

                self._initialized = True
                logger.info(
                    "sip_initialized user=%s domain=%s rtp_range=%d-%d",
                    Config.SIP_USER, Config.SIP_DOMAIN,
                    Config.RTP_PORT_MIN, Config.RTP_PORT_MAX,
                )
                return True
            except Exception as exc:
                logger.exception("sip_initialize_failed")
                return False

    def shutdown(self):
        """Drena chamadas e fecha endpoint."""
        with self._lock:
            if not self._initialized:
                return
            try:
                for ctx in list(self._calls.values()):
                    ctx.hangup()
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

        # TODO_SMOKE: validar que MyCall recebe corretamente os frames de áudio
        call = _MyCall(
            account=self._account,
            call_id_local=call_id,
            on_audio_in=on_audio_in,
            on_call_state=on_call_state,
        )
        prm = pj.CallOpParam(True)
        call.makeCall(dest_uri, prm)
        ctx = CallContext(call_id=call_id, pj_call=call)
        self._calls[call_id] = ctx
        logger.info("sip_dialing call_id=%s dest=%s", call_id, dest_uri)
        return call_id

    def push_audio_8k(self, call_id: str, pcm16_8k: bytes) -> None:
        """Camada externa (audio_bridge depois de downsample) chama isso
        pra que o áudio da Sofia chegue no telefone do paciente."""
        ctx = self._calls.get(call_id)
        if ctx and ctx.pj_call:
            ctx.pj_call.feed_audio_to_sip(pcm16_8k)

    def drain_outbound_audio(self, call_id: str) -> int:
        """Esvazia o buffer de áudio Sofia→SIP. Usado quando o usuário
        interrompe a fala da Sofia — mata o áudio em curso na hora.
        Retorna bytes drenados (telemetria)."""
        ctx = self._calls.get(call_id)
        if ctx and ctx.pj_call:
            return ctx.pj_call.drain_outbound_buffer()
        return 0

    def hangup(self, call_id: str) -> bool:
        ctx = self._calls.pop(call_id, None)
        if not ctx:
            return False
        ctx.hangup()
        return True

    def _normalize_dest(self, destination: str) -> str:
        # Aceita "5551996161700" ou "+5551996161700" ou "sip:..."
        d = destination.strip().lstrip("+")
        if d.startswith("sip:"):
            return d
        return f"sip:{d}@{Config.SIP_DOMAIN}"


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
                if self._frame_count == 1:
                    logger.info("first_audio_frame_received bytes=%d", len(audio_data))
                self._on_audio_in(audio_data)
            except Exception as exc:
                logger.warning("on_frame_received_error: %s", exc)

    class MyCall(pj.Call):
        def __init__(self, account, call_id_local, on_audio_in, on_call_state):
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
