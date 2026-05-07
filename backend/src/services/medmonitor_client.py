"""HTTP client da API MediMonitor/TotalCare (ADR-019).

Base URL: https://<tenant>.contactto.care/agent/
Auth: Authorization: Api-Key <plaintext-key>
Docs: /docs/Documentação Agente de API.pdf (2026-04-20)

Endpoints utilizados:
    GET  /patients/?search=<nome>&phone=<phone>
    GET  /patients/{id}/
    GET  /caretakers/?search=<nome>&phone=<phone>
    GET  /caretakers/{id}/
    GET  /members/?role=<role>&search=<nome>&phone=<phone>
    GET  /members/{id}/
    POST /care-notes/       { caretaker, patient, content, content_resume, occurred_at? }
    GET  /care-notes/?patient=<id>&occurred_after=<ts>&occurred_before=<ts>
    GET  /care-notes/{id}/

Normalização de telefone:
    API retorna "+5551999999999"; nosso webhook recebe "555196161700".
    Sempre normalizamos com `_normalize_phone()` antes de passar como filtro.

Graceful degradation: erros de rede/auth NÃO levantam exceção para o caller —
retornam None ou [] e logam warning. Isso permite o pipeline continuar funcionando
mesmo se o TotalCare estiver indisponível.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_CARE_NOTE_RESUME_LEN = 500  # limite documentado da API


class MedMonitorClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.medmonitor_api_url or "").rstrip("/")
        self.api_key = api_key or settings.medmonitor_api_key or ""
        self.enabled = bool(self.base_url and self.api_key)
        self._client = httpx.Client(
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Api-Key {self.api_key}",
                "Accept": "application/json",
            },
        ) if self.enabled else None

        if not self.enabled:
            logger.warning("medmonitor_client_disabled", reason="missing_url_or_key")

    # ---------- helpers ----------
    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normaliza telefone pro formato esperado pelo TotalCare: '+5551...'.

        Entrada pode ser: '555196161700', '5551996161700', '+555196161700',
        '51 99616-1700', etc. Remove tudo que não é dígito, adiciona '+' e '55'
        se faltar.
        """
        digits = re.sub(r"\D", "", phone or "")
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = "55" + digits
        return "+" + digits

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        extra_headers: dict | None = None,
    ) -> Any | None:
        if not self.enabled:
            return None

        url = f"{self.base_url}{path}"
        try:
            resp = self._client.request(
                method, url, params=params, json=json_body,
                headers=extra_headers,  # httpx merge com headers da session
            )
        except httpx.RequestError as exc:
            logger.warning("medmonitor_request_error", method=method, path=path, error=str(exc))
            return None

        if resp.status_code == 403:
            logger.error("medmonitor_forbidden_check_apikey_and_tenant", status=403, path=path)
            return None
        if resp.status_code == 404:
            logger.debug("medmonitor_not_found", path=path)
            return None
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:200]
            logger.warning(
                "medmonitor_http_error",
                method=method, path=path, status=resp.status_code, body=body,
            )
            return None

        try:
            return resp.json()
        except Exception as exc:
            logger.warning("medmonitor_json_decode_failed", path=path, error=str(exc))
            return None

    def _multipart_request(
        self,
        method: str,
        path: str,
        files: dict,
        data: dict | None = None,
        extra_headers: dict | None = None,
    ) -> dict[str, Any] | None:
        """Request multipart/form-data com tratamento explícito de 409.

        Retorna:
            • dict (response JSON) em sucesso (200/201)
            • {"_status_code": 409, "_already_uploaded": True} se servidor
              indica que mídia já existe (write-once)
            • None em qualquer outro erro (logado)

        Por que tratamento especial pra 409: o V2 da Tecnosenior usa
        "write-once" pra áudio — tentar segundo upload retorna 409. Isso
        NÃO é erro crítico (provavelmente retry de uma chamada anterior
        que perdemos a resposta). Caller decide o que fazer.
        """
        if not self.enabled:
            return None

        url = f"{self.base_url}{path}"
        try:
            resp = self._client.request(
                method, url, files=files, data=data or {},
                headers=extra_headers,
            )
        except httpx.RequestError as exc:
            logger.warning(
                "medmonitor_multipart_request_error",
                method=method, path=path, error=str(exc),
            )
            return None

        if resp.status_code == 409:
            logger.info(
                "medmonitor_media_already_uploaded",
                path=path, status=409,
            )
            return {"_status_code": 409, "_already_uploaded": True}

        if resp.status_code == 403:
            logger.error("medmonitor_forbidden_multipart", status=403, path=path)
            return None
        if resp.status_code == 404:
            logger.warning("medmonitor_multipart_not_found", path=path)
            return None
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:200]
            logger.warning(
                "medmonitor_multipart_http_error",
                method=method, path=path, status=resp.status_code, body=body,
            )
            return None

        try:
            return resp.json()
        except Exception as exc:
            logger.warning(
                "medmonitor_multipart_json_decode_failed",
                path=path, error=str(exc),
            )
            return None

    # ---------- patients (assistidos) ----------
    def list_patients(
        self,
        search: str | None = None,
        phone: str | None = None,
    ) -> list[dict]:
        params = {}
        if search:
            params["search"] = search
        if phone:
            params["phone"] = self._normalize_phone(phone)
        result = self._request("GET", "/patients/", params=params or None)
        return result or []

    def get_patient(self, patient_id: int | str) -> dict | None:
        return self._request("GET", f"/patients/{patient_id}/")

    # ---------- caretakers (cuidadores) ----------
    def list_caretakers(
        self,
        search: str | None = None,
        phone: str | None = None,
    ) -> list[dict]:
        params = {}
        if search:
            params["search"] = search
        if phone:
            params["phone"] = self._normalize_phone(phone)
        result = self._request("GET", "/caretakers/", params=params or None)
        return result or []

    def get_caretaker(self, caretaker_id: int | str) -> dict | None:
        return self._request("GET", f"/caretakers/{caretaker_id}/")

    def find_caretaker_by_phone(self, phone: str) -> dict | None:
        """Busca caretaker testando 3 variantes do phone — Tecnosenior
        guarda formatos diferentes dependendo do cadastro.

        Variantes testadas, em ordem:
          1. Phone como veio (ex: '51999524816')
          2. Com prefixo 55 (ex: '5551999524816')
          3. Com + e 55 (ex: '+5551999524816')
        """
        return self._find_with_phone_variants(
            "/caretakers/", phone,
        )

    def _find_with_phone_variants(self, path: str, phone: str) -> dict | None:
        """Helper genérico — tenta variantes pra paciente/caretaker."""
        digits = re.sub(r"\D", "", phone or "")
        if not digits:
            return None
        variants = [digits]
        if digits.startswith("55"):
            variants.append(digits[2:])
            variants.append("+" + digits)
        else:
            variants.append("55" + digits)
            variants.append("+55" + digits)
        for v in variants:
            try:
                results = self._request("GET", path, params={"phone": v})
                if isinstance(results, list) and results:
                    logger.debug(
                        "phone_match_via_variant path=%s variant=%s",
                        path, v,
                    )
                    return results[0]
            except Exception:
                continue
        return None

    def find_caretaker_by_cpf(self, cpf: str) -> dict | None:
        """Lookup por CPF — Matheus subiu em 2026-04-29. Aceita CPF
        com ou sem máscara, normaliza pra dígitos."""
        cpf_clean = re.sub(r"\D", "", cpf or "")
        if not cpf_clean:
            return None
        results = self._request("GET", "/caretakers/", params={"cpf": cpf_clean})
        if isinstance(results, list) and results:
            return results[0]
        return None

    def find_patient_by_phone(self, phone: str) -> dict | None:
        """Busca paciente por phone testando variantes — Tecnosenior
        guarda em formatos diferentes."""
        return self._find_with_phone_variants("/patients/", phone)

    def find_patient_by_cpf(self, cpf: str) -> dict | None:
        """Lookup por CPF (após Matheus subir suporte 2026-04-29)."""
        cpf_clean = re.sub(r"\D", "", cpf or "")
        if not cpf_clean:
            return None
        results = self._request("GET", "/patients/", params={"cpf": cpf_clean})
        if isinstance(results, list) and results:
            return results[0]
        return None

    # ---------- members (admin/staff/operators) ----------
    def list_members(
        self,
        search: str | None = None,
        phone: str | None = None,
        role: str | None = None,
    ) -> list[dict]:
        params = {}
        if search:
            params["search"] = search
        if phone:
            params["phone"] = self._normalize_phone(phone)
        if role:
            params["role"] = role
        result = self._request("GET", "/members/", params=params or None)
        return result or []

    def find_member_by_phone(self, phone: str) -> dict | None:
        results = self.list_members(phone=phone)
        return results[0] if results else None

    # ---------- care notes (anotações de cuidado) ----------
    def create_care_note(
        self,
        caretaker_id: int,
        patient_id: int,
        content: str,
        content_resume: str,
        occurred_at: str | None = None,
    ) -> dict | None:
        """Cria uma care-note. Retorna o dict criado ou None em falha.

        Truncamento defensivo de content_resume pra garantir ≤500 chars.
        Se content estiver vazio, retorna None sem chamar API.
        """
        if not content or not content.strip():
            logger.warning("care_note_content_empty")
            return None

        resume_clean = (content_resume or "").strip()
        if len(resume_clean) > MAX_CARE_NOTE_RESUME_LEN:
            resume_clean = resume_clean[:MAX_CARE_NOTE_RESUME_LEN - 1].rstrip() + "…"

        if not resume_clean:
            # Gera fallback básico truncando content
            resume_clean = content.strip()[:MAX_CARE_NOTE_RESUME_LEN - 1] + "…"

        body: dict[str, Any] = {
            "caretaker": caretaker_id,
            "patient": patient_id,
            "content": content.strip(),
            "content_resume": resume_clean,
        }
        if occurred_at:
            body["occurred_at"] = occurred_at

        result = self._request("POST", "/care-notes/", json_body=body)
        if result:
            logger.info(
                "care_note_created",
                note_id=result.get("id"),
                caretaker_id=caretaker_id,
                patient_id=patient_id,
            )
        return result

    def create_care_note_streaming(
        self,
        caretaker_id: int,
        patient_id: int,
        content: str,
        content_resume: str,
        occurred_at: str | None = None,
        status: str = "OPEN",
        closed_reason: str | None = None,
        audio_bytes: bytes | None = None,
        audio_filename: str = "audio.ogg",
        idempotency_key: str | None = None,
    ) -> dict | None:
        """Cria CareNote com status explícito (OPEN ou CLOSED).

        Cenário 2 da API Tecnosenior: abre CareNote OPEN pra receber
        addendums depois. Quando passa CLOSED, vira one-off do cenário 1.

        V2:
            closed_reason: texto livre ≤50 chars. Servidor REJEITA (400)
                se enviado com status=OPEN. Por isso só anexamos quando
                status=CLOSED.
            audio_bytes: se fornecido, usa multipart/form-data e anexa
                áudio na criação (cenário 6.1 do doc V2). Caso contrário,
                JSON normal — caller pode fazer upload separado depois.
            idempotency_key: opcional. Tecnosenior vai habilitar suporte
                nativo nos views (Matheus 2026-05-07). Vai como header
                `Idempotency-Key`; se Tecnosenior aceitar, retry seguro.
                Servidor ignora silenciosamente quando ainda não suportar.
        """
        if not content or not content.strip():
            logger.warning("care_note_content_empty")
            return None
        resume_clean = (content_resume or "").strip()
        if len(resume_clean) > MAX_CARE_NOTE_RESUME_LEN:
            resume_clean = resume_clean[:MAX_CARE_NOTE_RESUME_LEN - 1].rstrip() + "…"
        if not resume_clean:
            resume_clean = content.strip()[:MAX_CARE_NOTE_RESUME_LEN - 1] + "…"
        if status not in ("OPEN", "CLOSED"):
            status = "OPEN"

        # Sanitiza closed_reason: só vai quando CLOSED + truncado a 50 chars
        closed_reason_clean: str | None = None
        if status == "CLOSED" and closed_reason:
            closed_reason_clean = closed_reason.strip()[:50]

        # Idempotência (Tecnosenior habilitando próx. semana — 2026-05-07)
        # vai como header padrão Idempotency-Key
        extra_headers = (
            {"Idempotency-Key": idempotency_key} if idempotency_key else None
        )

        # Branch: multipart com áudio vs JSON normal
        if audio_bytes:
            data: dict[str, Any] = {
                "caretaker": str(caretaker_id),
                "patient": str(patient_id),
                "content": content.strip(),
                "content_resume": resume_clean,
                "status": status,
            }
            if occurred_at:
                data["occurred_at"] = occurred_at
            if closed_reason_clean:
                data["closed_reason"] = closed_reason_clean
            files = {"audio": (audio_filename, audio_bytes, "audio/ogg")}
            result = self._multipart_request(
                "POST", "/care-notes/", files=files, data=data,
                extra_headers=extra_headers,
            )
            if result and result.get("_already_uploaded"):
                # 409 numa criação não faz sentido — servidor não devia
                # retornar isso aqui. Loga e retorna None.
                logger.warning(
                    "medmonitor_carenote_create_409_unexpected",
                    caretaker_id=caretaker_id, patient_id=patient_id,
                )
                return None
            return result

        # JSON path (sem áudio)
        body: dict[str, Any] = {
            "caretaker": caretaker_id,
            "patient": patient_id,
            "content": content.strip(),
            "content_resume": resume_clean,
            "status": status,
        }
        if occurred_at:
            body["occurred_at"] = occurred_at
        if closed_reason_clean:
            body["closed_reason"] = closed_reason_clean
        return self._request(
            "POST", "/care-notes/", json_body=body,
            extra_headers=extra_headers,
        )

    def create_care_note_bulk(
        self,
        caretaker_id: int,
        patient_id: int,
        content: str,
        content_resume: str,
        addendums: list[dict],
        occurred_at: str | None = None,
        status: str = "OPEN",
        closed_reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict | None:
        """Cenário 3/4 da Tecnosenior: cria CareNote + addendums em chamada
        atômica. Cada addendum é {content, content_resume, occurred_at}.

        Atômico: se 1 addendum falhar validação, NADA é gravado.
        """
        if not content or not content.strip():
            return None
        resume_clean = (content_resume or "").strip()
        if len(resume_clean) > MAX_CARE_NOTE_RESUME_LEN:
            resume_clean = resume_clean[:MAX_CARE_NOTE_RESUME_LEN - 1].rstrip() + "…"
        if not resume_clean:
            resume_clean = content.strip()[:MAX_CARE_NOTE_RESUME_LEN - 1] + "…"
        if status not in ("OPEN", "CLOSED"):
            status = "OPEN"

        # closed_reason só vai com CLOSED, ≤50 chars (V2)
        closed_reason_clean: str | None = None
        if status == "CLOSED" and closed_reason:
            closed_reason_clean = closed_reason.strip()[:50]

        body: dict[str, Any] = {
            "caretaker": caretaker_id,
            "patient": patient_id,
            "content": content.strip(),
            "content_resume": resume_clean,
            "status": status,
            "addendums": addendums or [],
        }
        if occurred_at:
            body["occurred_at"] = occurred_at
        if closed_reason_clean:
            body["closed_reason"] = closed_reason_clean

        extra_headers = (
            {"Idempotency-Key": idempotency_key} if idempotency_key else None
        )
        return self._request(
            "POST", "/care-notes/bulk/", json_body=body,
            extra_headers=extra_headers,
        )

    def add_addendum(
        self,
        care_note_id: int,
        content: str,
        content_resume: str,
        occurred_at: str | None = None,
        status: str | None = None,
        closed_reason: str | None = None,
        audio_bytes: bytes | None = None,
        audio_filename: str = "audio.ogg",
        idempotency_key: str | None = None,
    ) -> dict | None:
        """POST /care-notes/{id}/addendums/ — adiciona addendum a uma
        CareNote OPEN.

        status='CLOSED' no addendum dispara fechamento da CareNote pai.
        Sem status: addendum normal (CareNote permanece OPEN).

        V2 (confirmado com Matheus 2026-05-07):
            closed_reason: se enviado junto com status=CLOSED, o servidor
                fecha a CareNote pai com essa razão. Só vai ao wire se
                status=CLOSED.
            audio_bytes: se fornecido, usa multipart/form-data e anexa
                áudio na criação do addendum (cenário 6.3 do doc V2).
        """
        if not content or not content.strip():
            return None
        resume_clean = (content_resume or "").strip()
        if len(resume_clean) > MAX_CARE_NOTE_RESUME_LEN:
            resume_clean = resume_clean[:MAX_CARE_NOTE_RESUME_LEN - 1].rstrip() + "…"
        if not resume_clean:
            resume_clean = content.strip()[:MAX_CARE_NOTE_RESUME_LEN - 1] + "…"

        # Sanitiza closed_reason: só vai com status=CLOSED, ≤50 chars
        closed_reason_clean: str | None = None
        if status == "CLOSED" and closed_reason:
            closed_reason_clean = closed_reason.strip()[:50]

        extra_headers = (
            {"Idempotency-Key": idempotency_key} if idempotency_key else None
        )

        # Branch: multipart com áudio vs JSON
        if audio_bytes:
            data: dict[str, Any] = {
                "content": content.strip(),
                "content_resume": resume_clean,
            }
            if occurred_at:
                data["occurred_at"] = occurred_at
            if status == "CLOSED":
                data["status"] = "CLOSED"
            if closed_reason_clean:
                data["closed_reason"] = closed_reason_clean
            files = {"audio": (audio_filename, audio_bytes, "audio/ogg")}
            result = self._multipart_request(
                "POST",
                f"/care-notes/{care_note_id}/addendums/",
                files=files, data=data,
                extra_headers=extra_headers,
            )
            if result and result.get("_already_uploaded"):
                logger.warning(
                    "medmonitor_addendum_create_409_unexpected",
                    care_note_id=care_note_id,
                )
                return None
            return result

        # JSON path (sem áudio)
        body: dict[str, Any] = {
            "content": content.strip(),
            "content_resume": resume_clean,
        }
        if occurred_at:
            body["occurred_at"] = occurred_at
        if status == "CLOSED":
            body["status"] = "CLOSED"
        if closed_reason_clean:
            body["closed_reason"] = closed_reason_clean
        return self._request(
            "POST", f"/care-notes/{care_note_id}/addendums/", json_body=body,
            extra_headers=extra_headers,
        )

    # ══════════════════════════════════════════════════════════════════
    # V2: Upload separado de mídia (cenários 6.2, 6.4 e §7 do doc)
    # ══════════════════════════════════════════════════════════════════

    def upload_carenote_audio(
        self,
        care_note_id: int,
        audio_bytes: bytes,
        audio_filename: str = "audio.ogg",
        content_type: str = "audio/ogg",
    ) -> dict | None:
        """POST /care-notes/{id}/audio/ — anexa áudio em CareNote já criada.

        Write-once: 2ª chamada retorna 409 (não é erro crítico, é noop
        seguro). Returns:
            • dict da CareNote atualizada com audio_url populado em 200/201
            • {"_already_uploaded": True, "_status_code": 409} se já tem
            • None em outros erros
        """
        if not audio_bytes:
            logger.warning("upload_carenote_audio_empty_bytes")
            return None
        files = {"audio": (audio_filename, audio_bytes, content_type)}
        return self._multipart_request(
            "POST", f"/care-notes/{care_note_id}/audio/", files=files,
        )

    def upload_addendum_audio(
        self,
        care_note_id: int,
        addendum_id: int,
        audio_bytes: bytes,
        audio_filename: str = "audio.ogg",
        content_type: str = "audio/ogg",
    ) -> dict | None:
        """POST /care-notes/{note_id}/addendums/{addendum_id}/audio/

        Servidor valida que addendum_id pertence ao note_id da URL.
        Write-once por addendum.
        """
        if not audio_bytes:
            logger.warning("upload_addendum_audio_empty_bytes")
            return None
        files = {"audio": (audio_filename, audio_bytes, content_type)}
        return self._multipart_request(
            "POST",
            f"/care-notes/{care_note_id}/addendums/{addendum_id}/audio/",
            files=files,
        )

    def upload_carenote_photo(
        self,
        care_note_id: int,
        image_bytes: bytes,
        image_filename: str = "photo.jpg",
        content_type: str = "image/jpeg",
        addendum_id: int | None = None,
    ) -> dict | None:
        """POST /care-notes/{id}/photos/ — anexa foto à CareNote.

        Sem limite de fotos por nota. Se addendum_id fornecido, foto fica
        associada a ele (campo `addendum` no body multipart). Servidor
        valida que addendum pertence à mesma CareNote.

        Diferente do áudio, foto NÃO tem 409 (sem write-once, múltiplas
        fotos OK).
        """
        if not image_bytes:
            logger.warning("upload_carenote_photo_empty_bytes")
            return None
        files = {"image": (image_filename, image_bytes, content_type)}
        data: dict[str, Any] = {}
        if addendum_id is not None:
            data["addendum"] = str(addendum_id)
        return self._multipart_request(
            "POST",
            f"/care-notes/{care_note_id}/photos/",
            files=files, data=data,
        )

    # ══════════════════════════════════════════════════════════════════
    # V2: Health Measures (medidas de saúde — endpoints em dev pelo TS)
    # ══════════════════════════════════════════════════════════════════
    #
    # Unidades padronizadas (alinhadas com Matheus 2026-05-07):
    #   heart_rate          → bpm
    #   blood_pressure_*    → mmHg
    #   blood_glucose       → mg/dL
    #   temperature         → °C
    #   weight              → kg
    #   oxygen_saturation   → %
    #
    # Política de fronteira: o AGENTE faz a extração de áudio/foto/texto
    # natural (NOSSO IP). O TotalCare só recebe dado já estruturado.

    _HEALTH_MEASURE_TYPES = (
        "heart_rate",
        "blood_pressure_systolic",
        "blood_pressure_diastolic",
        "blood_glucose",
        "temperature",
        "weight",
        "oxygen_saturation",
    )

    def list_health_measures(
        self,
        patient_id: int,
        measure_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = 100,
    ) -> list[dict]:
        """GET medidas de saúde de um paciente.

        Endpoint exato a confirmar com Matheus. Por enquanto usamos:
            GET /patients/{id}/health-measures/?type=&since=&until=&limit=
            (geral)
        ou
            GET /patients/{id}/health-measures/{type}/?since=&until=&limit=
            (específico — quando measure_type fornecido)

        Args:
            patient_id: ID TotalCare do paciente
            measure_type: opcional. Se fornecido, usa endpoint específico.
                Aceita um dos _HEALTH_MEASURE_TYPES.
            since/until: ISO 8601 timestamps
            limit: max de registros pra evitar enxurrada

        Retorna lista (vazia se erro pra graceful degrade).
        """
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if limit is not None:
            params["limit"] = limit

        if measure_type:
            if measure_type not in self._HEALTH_MEASURE_TYPES:
                logger.warning(
                    "health_measure_invalid_type", measure_type=measure_type,
                )
                return []
            path = f"/patients/{patient_id}/health-measures/{measure_type}/"
        else:
            path = f"/patients/{patient_id}/health-measures/"

        result = self._request("GET", path, params=params or None)
        if isinstance(result, dict) and "results" in result:
            return result["results"]
        return result if isinstance(result, list) else []

    def create_health_measures_bulk(
        self,
        patient_id: int,
        measures: list[dict],
        idempotency_key: str | None = None,
    ) -> dict | None:
        """POST bulk de medidas de saúde.

        Endpoint exato a confirmar com Matheus. Tendência (alinhamento
        2026-05-07): UM endpoint que recebe array em vez de 1 endpoint por
        tipo, pra alinhar com fluxo conversacional (cuidador relata várias
        medidas, agente confirma com cuidador, faz bulk send).

        Schema do payload:
            POST /patients/{id}/health-measures/bulk/
            {
                "idempotency_key": "uuid",  // opcional — se Tecnosenior expôr
                "measures": [
                    {
                        "type": "heart_rate" | "blood_pressure_systolic" | ...,
                        "value": 78,
                        "unit": "bpm",
                        "measured_at": "2026-05-07T14:30:00Z",
                        "source": "agent_voice" | "agent_photo" | "agent_typed",
                        "confidence": 0.95,
                        "raw_text": "ela tá com 78 batimentos"  // opcional pra audit
                    },
                    ...
                ]
            }

        Validação local: filtra measures com type/value inválidos antes
        de mandar. Atomicidade no servidor depende de como Matheus
        implementar (preferimos all-or-nothing).
        """
        if not measures:
            return None

        # Sanitização local: filtra os com type válido + value numérico
        sanitized: list[dict] = []
        for m in measures:
            if not isinstance(m, dict):
                continue
            mtype = m.get("type")
            if mtype not in self._HEALTH_MEASURE_TYPES:
                logger.warning(
                    "health_measure_skipped_invalid_type",
                    measure_type=mtype,
                )
                continue
            if "value" not in m:
                continue
            try:
                # Aceita int/float/str numérica
                m_value = float(m["value"])
            except (TypeError, ValueError):
                logger.warning(
                    "health_measure_skipped_invalid_value", measure=m,
                )
                continue
            entry: dict[str, Any] = {
                "type": mtype,
                "value": m_value,
                "unit": m.get("unit") or self._default_unit(mtype),
            }
            for k in ("measured_at", "source", "confidence", "raw_text"):
                if m.get(k) is not None:
                    entry[k] = m[k]
            sanitized.append(entry)

        if not sanitized:
            logger.warning("health_measures_bulk_empty_after_sanitize")
            return None

        body: dict[str, Any] = {"measures": sanitized}
        # idempotency_key vai como header padrão Idempotency-Key
        # (Tecnosenior habilitando próx. semana — Matheus 2026-05-07)
        extra_headers = (
            {"Idempotency-Key": idempotency_key} if idempotency_key else None
        )

        return self._request(
            "POST",
            f"/patients/{patient_id}/health-measures/bulk/",
            json_body=body,
            extra_headers=extra_headers,
        )

    @staticmethod
    def _default_unit(measure_type: str) -> str:
        return {
            "heart_rate": "bpm",
            "blood_pressure_systolic": "mmHg",
            "blood_pressure_diastolic": "mmHg",
            "blood_glucose": "mg/dL",
            "temperature": "°C",
            "weight": "kg",
            "oxygen_saturation": "%",
        }.get(measure_type, "")

    def list_care_notes(
        self,
        patient_id: int | list[int] | None = None,
        caretaker_id: int | list[int] | None = None,
        occurred_after: str | None = None,
        occurred_before: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if patient_id is not None:
            params["patient"] = (
                ",".join(str(p) for p in patient_id) if isinstance(patient_id, list) else str(patient_id)
            )
        if caretaker_id is not None:
            params["caretaker"] = (
                ",".join(str(c) for c in caretaker_id) if isinstance(caretaker_id, list) else str(caretaker_id)
            )
        if occurred_after:
            params["occurred_after"] = occurred_after
        if occurred_before:
            params["occurred_before"] = occurred_before

        result = self._request("GET", "/care-notes/", params=params or None)
        return result or []

    # ---------- lifecycle ----------
    def close(self) -> None:
        if self._client:
            self._client.close()


_medmonitor_instance: MedMonitorClient | None = None


def get_medmonitor_client() -> MedMonitorClient:
    global _medmonitor_instance
    if _medmonitor_instance is None:
        _medmonitor_instance = MedMonitorClient()
    return _medmonitor_instance
