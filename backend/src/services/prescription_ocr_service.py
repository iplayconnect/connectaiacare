"""Prescription OCR Service — Claude Vision extrai medicamentos de imagens.

Input: imagem (base64) de receita/bula/caixa/organizador de comprimidos.
Output: lista estruturada de medicamentos + dose + posologia, pronta pra
virar `medication_schedules`.

Usa Anthropic Claude Sonnet 4.5 (vision-capable) — entende contexto clínico
brasileiro, letra manuscrita de médico, normaliza dose.

Pós-extração:
    1. Grava em aia_health_medication_imports
    2. Retorna pra frontend pra confirmação do usuário
    3. Após confirmação, popula schedules
"""
from __future__ import annotations

import base64
import json
from typing import Any

import anthropic

from config.settings import settings
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

{{
  "kind": "prescription" | "package" | "leaflet" | "pill_organizer" | "not_medication_related" | "unclear",
  "confidence": 0.0 a 1.0,
  "needs_more_info": "texto em linguagem simples se precisar outra foto, ou null",
  "medications": [
    {{
      "name": "nome principal (comercial ou genérico)",
      "alternative_names": ["outros nomes conhecidos"],
      "dose": "50mg | 1/2 comprimido | 20 gotas",
      "dose_form": "comprimido | cápsula | gotas | ml | spray | pomada",
      "schedule_text": "texto original da posologia (ex: '1 comp 8/8h VO')",
      "parsed_schedule": {{
        "times_per_day": 1 | 2 | 3 | 4,
        "times_of_day": ["07:00", "11:00", ...] | null,
        "prn": true | false,
        "days_of_week": [1,3,5] | null,
        "interval_hours": 8 | null
      }},
      "duration_text": "7 dias | uso contínuo | 1 mês",
      "duration_days": 7 | null,
      "indication": "pra que serve, se mencionado",
      "warnings": ["Em jejum", "Não associar com leite"],
      "with_food": "with" | "without" | "either",
      "field_confidence": {{
        "name": 0.0 a 1.0,
        "dose": 0.0 a 1.0,
        "schedule": 0.0 a 1.0
      }}
    }}
  ],
  "doctor_info": {{
    "name": "se visível em receita",
    "crm": "CRM/UF 12345 se visível"
  }} | null,
  "issue_date": "YYYY-MM-DD se visível em receita" | null,
  "patient_name_on_document": "se visível" | null,
  "notes_for_user": "observações acolhedoras em português pra o paciente/familiar"
}}

Seja conservador em `confidence` — se não tem certeza, reflita."""


# Opções comuns de nome comercial → genérico pra fallback local
COMMERCIAL_TO_GENERIC = {
    "motilium": "domperidona",
    "cozaar": "losartana",
    "aradois": "losartana",
    "renitec": "enalapril",
    "glifage": "metformina",
    "glucoformin": "metformina",
    "aspirina": "ácido acetilsalicílico",
    "aas": "ácido acetilsalicílico",
    "omepral": "omeprazol",
    "losec": "omeprazol",
    "rivotril": "clonazepam",
    "diazepan": "diazepam",
    "haldol": "haloperidol",
    "plasil": "metoclopramida",
}


class PrescriptionOcrService:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = "claude-sonnet-4-5-20250929"
        self.db = get_postgres()

    def analyze_image(
        self,
        image_b64: str,
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Envia imagem pro Claude Vision, retorna extração estruturada."""
        # Limpa eventual prefixo data:image/...;base64,
        clean_b64 = image_b64
        if "," in image_b64[:50]:
            clean_b64 = image_b64.split(",", 1)[1]

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": clean_b64,
                                },
                            },
                            {"type": "text", "text": USER_PROMPT},
                        ],
                    }
                ],
            )

            # Extrai texto + parse JSON
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            text = self._extract_json(text)
            result = json.loads(text)
            result["_model_used"] = self._model
            result["_input_tokens"] = response.usage.input_tokens
            result["_output_tokens"] = response.usage.output_tokens
            return result
        except json.JSONDecodeError as exc:
            logger.error("ocr_json_parse_failed", error=str(exc), text_sample=text[:300] if 'text' in locals() else "")
            return {
                "kind": "unclear",
                "confidence": 0.0,
                "needs_more_info": "Não consegui entender a imagem. Pode tentar outra foto com mais luz?",
                "medications": [],
                "_error": str(exc),
            }
        except Exception as exc:
            logger.error("ocr_claude_failed", error=str(exc))
            return {
                "kind": "unclear",
                "confidence": 0.0,
                "needs_more_info": "Houve um problema ao analisar a imagem. Por favor tente novamente em alguns instantes.",
                "medications": [],
                "_error": str(exc),
            }

    @staticmethod
    def _extract_json(text: str) -> str:
        """Remove possíveis code fences e lê só o objeto JSON."""
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            # pula primeira ```... e última ```
            body = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    if in_block:
                        break
                    in_block = True
                    continue
                if in_block:
                    body.append(line)
            t = "\n".join(body).strip()
        # Se ainda tem lixo antes, busca primeiro '{'
        idx = t.find("{")
        if idx > 0:
            t = t[idx:]
        # Busca último '}' que fecha
        last = t.rfind("}")
        if last > 0:
            t = t[: last + 1]
        return t

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
                result.get("_model_used"),
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
        self.db.execute(
            """
            UPDATE aia_health_medication_imports
            SET confirmation_status = 'confirmed',
                confirmed_at = NOW(),
                user_corrections = %s,
                created_schedule_ids = %s
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
