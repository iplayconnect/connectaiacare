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
    ) -> Any | None:
        if not self.enabled:
            return None

        url = f"{self.base_url}{path}"
        try:
            resp = self._client.request(method, url, params=params, json=json_body)
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
        """Busca o PRIMEIRO caretaker cujo phone bate com o normalizado.

        Retorna dict {id, person, nature} ou None.
        """
        results = self.list_caretakers(phone=phone)
        return results[0] if results else None

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
        """Busca paciente por telefone normalizado (TotalCare aceita
        +5551... ou variações). Retorna dict ou None."""
        results = self.list_patients(phone=phone)
        return results[0] if results else None

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
    ) -> dict | None:
        """Cria CareNote com status explícito (OPEN ou CLOSED).

        Cenário 2 da API Tecnosenior: abre CareNote OPEN pra receber
        addendums depois. Quando passa CLOSED, vira one-off do cenário 1.
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

        body: dict[str, Any] = {
            "caretaker": caretaker_id,
            "patient": patient_id,
            "content": content.strip(),
            "content_resume": resume_clean,
            "status": status,
        }
        if occurred_at:
            body["occurred_at"] = occurred_at
        return self._request("POST", "/care-notes/", json_body=body)

    def create_care_note_bulk(
        self,
        caretaker_id: int,
        patient_id: int,
        content: str,
        content_resume: str,
        addendums: list[dict],
        occurred_at: str | None = None,
        status: str = "OPEN",
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
        return self._request("POST", "/care-notes/bulk/", json_body=body)

    def add_addendum(
        self,
        care_note_id: int,
        content: str,
        content_resume: str,
        occurred_at: str | None = None,
        status: str | None = None,
    ) -> dict | None:
        """POST /care-notes/{id}/addendums/ — adiciona addendum a uma
        CareNote OPEN.

        status='CLOSED' no addendum dispara fechamento da CareNote pai.
        Sem status: addendum normal (CareNote permanece OPEN).
        """
        if not content or not content.strip():
            return None
        resume_clean = (content_resume or "").strip()
        if len(resume_clean) > MAX_CARE_NOTE_RESUME_LEN:
            resume_clean = resume_clean[:MAX_CARE_NOTE_RESUME_LEN - 1].rstrip() + "…"
        if not resume_clean:
            resume_clean = content.strip()[:MAX_CARE_NOTE_RESUME_LEN - 1] + "…"

        body: dict[str, Any] = {
            "content": content.strip(),
            "content_resume": resume_clean,
        }
        if occurred_at:
            body["occurred_at"] = occurred_at
        if status == "CLOSED":
            body["status"] = "CLOSED"
        return self._request(
            "POST", f"/care-notes/{care_note_id}/addendums/", json_body=body,
        )

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
