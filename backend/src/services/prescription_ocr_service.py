"""Prescription OCR Service — extrai medicamentos de imagens via LLMRouter.

Delega escolha de modelo pro router (ADR-025 task='prescription_ocr').
Default: Gemini 2.5 Flash Vision (melhor custo-benefício pra OCR).
Fallback: Claude Sonnet 4 Vision → GPT-5.4 mini.

Pós-extração:
    1. Grava em aia_health_medication_imports
    2. Retorna pra frontend pra confirmação do usuário
    3. Após confirmação, popula schedules
"""
from __future__ import annotations

import base64
import json
from typing import Any

from src.services.llm_router import get_llm_router
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


SYSTEM_PROMPT = """Você é um extrator especializado em medicamentos brasileiros.

Recebe UMA imagem que o usuário enviou (geralmente paciente idoso ou familiar)
e precisa identificar:
    1. Tipo da imagem (receita médica, caixa do medicamento, bula, organizador, outro)
    2. Medicamentos visíveis com nome, dose, posologia, duração
    3. Avisos importantes da bula/caixa se relevantes

REGRAS INVIOLÁVEIS:
1. NUNCA invente dose, nome ou posologia. Se a imagem está borrada/ilegível em
   algum campo, deixe NULL e sinalize em `needs_more_info`.
2. Não confunda nome comercial com genérico (ex: Motilium = Domperidona — inclua ambos).
3. Posologia em receita médica tem convenções BR:
   - "1 cp" = 1 comprimido
   - "VO" = via oral
   - "8/8h" = de 8 em 8 horas
   - "ACM" = antes das refeições
   - "SOS" ou "S/N" = se necessário
   - "uso contínuo" = sem prazo
4. Se NÃO for imagem de medicamento (ex: foto aleatória, selfie), retorne
   kind="not_medication_related" e peça pra enviar foto correta.
5. Se a imagem mostra múltiplos medicamentos, inclua TODOS.
6. Normalize dose: "50 miligramas" → "50mg"; "meio comprimido" → "1/2 comprimido".
7. Se identifica nome comercial conhecido, inclua nome genérico correspondente em
   alternative_names quando apropriado.
"""


USER_PROMPT = """Analise esta imagem e retorne JSON estrito:

{
  "kind": "prescription" | "package" | "leaflet" | "pill_organizer" | "not_medication_related" | "unclear",
  "confidence": 0.0 a 1.0,
  "needs_more_info": "texto em linguagem simples se precisar outra foto, ou null",
  "medications": [
    {
      "name": "nome principal (comercial ou genérico)",
      "alternative_names": ["outros nomes conhecidos"],
      "dose": "50mg | 1/2 comprimido | 20 gotas",
      "dose_form": "comprimido | cápsula | gotas | ml | spray | pomada",
      "schedule_text": "texto original da posologia (ex: '1 comp 8/8h VO')",
      "parsed_schedule": {
        "times_per_day": 1,
        "times_of_day": ["07:00", "11:00"],
        "prn": false,
        "days_of_week": null,
        "interval_hours": 8
      },
      "duration_text": "7 dias | uso contínuo | 1 mês",
      "duration_days": 7,
      "indication": "pra que serve, se mencionado",
      "warnings": ["Em jejum", "Não associar com leite"],
      "with_food": "with",
      "field_confidence": {
        "name": 0.9,
        "dose": 0.95,
        "schedule": 0.6
      }
    }
  ],
  "doctor_info": null,
  "issue_date": null,
  "patient_name_on_document": null,
  "notes_for_user": "observações acolhedoras em português"
}

Seja conservador em `confidence` — se não tem certeza, reflita. Se não houver
dados pra um campo, use null. Retorne APENAS JSON válido, sem comentários."""


class PrescriptionOcrService:
    def __init__(self):
        self.db = get_postgres()
        self.router = get_llm_router()

    def analyze_image(
        self,
        image_b64: str,
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Envia imagem pro vision LLM configurado. Retorna JSON estruturado.

        ADR-025: task='prescription_ocr' → Gemini 2.5 Flash Vision.
        Router aplica fallback se primary falhar.
        """
        # Limpa eventual prefixo data:image/...;base64,
        clean_b64 = image_b64
        if "," in image_b64[:50]:
            clean_b64 = image_b64.split(",", 1)[1]

        try:
            result = self.router.complete_json(
                task="prescription_ocr",
                system=SYSTEM_PROMPT,
                user=USER_PROMPT,
                image_b64=clean_b64,
                image_mime=mime_type,
            )
            return result
        except Exception as exc:
            logger.error("ocr_failed", error=str(exc))
            return self._unclear_fallback(str(exc))

    @staticmethod
    def _unclear_fallback(reason: str) -> dict:
        return {
            "kind": "unclear",
            "confidence": 0.0,
            "needs_more_info": "Não consegui analisar a imagem dessa vez. Pode tentar outra foto com boa iluminação?",
            "medications": [],
            "_error": reason,
        }

    # ══════════════════════════════════════════════════════════════════
    # Persistência em aia_health_medication_imports
    # ══════════════════════════════════════════════════════════════════

    def create_import_record(
        self,
        tenant_id: str,
        patient_id: str,
        source_type: str,
        file_b64: str | None = None,
        file_mime: str | None = None,
        uploaded_by_type: str | None = None,
        uploaded_by_id: str | None = None,
        device_user_agent: str | None = None,
    ) -> dict:
        """Grava o upload antes de analisar."""
        size = (len(file_b64) * 3 // 4) if file_b64 else None
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_medication_imports
                (tenant_id, patient_id, source_type, file_b64, file_mime,
                 file_size_bytes, uploaded_by_type, uploaded_by_id,
                 device_user_agent, analysis_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id, uploaded_at
            """,
            (
                tenant_id, patient_id, source_type, file_b64, file_mime,
                size, uploaded_by_type, uploaded_by_id, device_user_agent,
            ),
        )
        return row

    def save_analysis(
        self, import_id: str, result: dict[str, Any],
    ) -> None:
        status = "done" if result.get("medications") else "failed"
        if result.get("kind") == "unclear":
            status = "failed"

        self.db.execute(
            """
            UPDATE aia_health_medication_imports
            SET analysis_status = %s,
                analyzed_at = NOW(),
                model_used = %s,
                raw_extraction = %s,
                parsed_medications = %s,
                needs_more_info = %s,
                error_message = %s
            WHERE id = %s
            """,
            (
                status,
                result.get("_model_used") or result.get("_provider"),
                self.db.json_adapt(result),
                self.db.json_adapt(result.get("medications") or []),
                result.get("needs_more_info"),
                result.get("_error"),
                import_id,
            ),
        )

    def confirm_import(
        self,
        import_id: str,
        user_corrections: list[dict] | None = None,
        created_schedule_ids: list[str] | None = None,
    ) -> None:
        # Cast explícito de TEXT[] pra UUID[] (psycopg2 não infere automaticamente)
        self.db.execute(
            """
            UPDATE aia_health_medication_imports
            SET confirmation_status = 'confirmed',
                confirmed_at = NOW(),
                user_corrections = %s,
                created_schedule_ids = %s::uuid[]
            WHERE id = %s
            """,
            (
                self.db.json_adapt(user_corrections or []),
                created_schedule_ids or [],
                import_id,
            ),
        )

    def get_import(self, import_id: str) -> dict | None:
        return self.db.fetch_one(
            "SELECT * FROM aia_health_medication_imports WHERE id = %s",
            (import_id,),
        )


_instance: PrescriptionOcrService | None = None


def get_prescription_ocr_service() -> PrescriptionOcrService:
    global _instance
    if _instance is None:
        _instance = PrescriptionOcrService()
    return _instance
