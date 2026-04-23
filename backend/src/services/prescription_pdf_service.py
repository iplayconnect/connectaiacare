"""Geração de PDF da receita médica — CFM 2.314/2022.

Layout inspirado em receituários brasileiros tradicionais:
    - Cabeçalho com identificação do médico + CRM + especialidade
    - Identificação do paciente + idade + condições relevantes
    - Prescrição formatada item a item (medicamento, dose, posologia, duração)
    - Orientações não-farmacológicas
    - Retorno / seguimento
    - Assinatura eletrônica mocked + QR code de verificação (hash do FHIR)
    - Rodapé com informações da plataforma e disclaimers

Verificação anti-fraude: o QR aponta para
    https://care.connectaia.com.br/verificar/<teleconsulta_id>
onde qualquer pessoa pode conferir que o PDF corresponde a uma
teleconsulta realmente assinada.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from io import BytesIO
from typing import Any

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from src.utils.logger import get_logger

logger = get_logger(__name__)


# Paleta da marca ConnectaIACare
BRAND_CYAN = colors.HexColor("#31E1FF")
BRAND_TEAL = colors.HexColor("#14B8A6")
BRAND_DARK = colors.HexColor("#0A1028")
TEXT_MAIN = colors.HexColor("#1a1a1a")
TEXT_MUTED = colors.HexColor("#666666")
BORDER_SOFT = colors.HexColor("#E5E7EB")
DANGER = colors.HexColor("#DC2626")


class PrescriptionPdfService:
    def generate(
        self,
        teleconsultation: dict[str, Any],
        patient: dict[str, Any],
        doctor: dict[str, Any],
        prescription_items: list[dict[str, Any]],
        soap: dict[str, Any] | None = None,
        verify_base_url: str = "https://care.connectaia.com.br",
    ) -> bytes:
        """Gera PDF A4 da receita. Retorna bytes prontos pra HTTP response."""
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # ============================================================
        # 1. Cabeçalho
        # ============================================================
        self._draw_header(c, width, height, teleconsultation)

        # ============================================================
        # 2. Identificação do médico
        # ============================================================
        y = height - 4.5 * cm
        y = self._draw_doctor_block(c, width, y, doctor)

        # ============================================================
        # 3. Identificação do paciente
        # ============================================================
        y = self._draw_patient_block(c, width, y, patient)

        # ============================================================
        # 4. Prescrição (core)
        # ============================================================
        y = self._draw_prescription(c, width, y, prescription_items)

        # ============================================================
        # 5. Orientações (extraídas do SOAP se houver)
        # ============================================================
        if soap:
            y = self._draw_orientations(c, width, y, soap)

        # ============================================================
        # 6. Rodapé com assinatura + QR code
        # ============================================================
        self._draw_signature_and_qr(
            c, width, teleconsultation, doctor, verify_base_url,
        )

        c.showPage()
        c.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(
            "prescription_pdf_generated",
            tc_id=teleconsultation.get("id"),
            items=len(prescription_items or []),
            bytes=len(pdf_bytes),
        )
        return pdf_bytes

    # ======================================================================
    # Layout blocks
    # ======================================================================

    def _draw_header(self, c: canvas.Canvas, width: float, height: float, tc: dict):
        """Faixa superior com branding + nº da teleconsulta + data."""
        # Faixa colorida
        c.setFillColor(BRAND_DARK)
        c.rect(0, height - 2.2 * cm, width, 2.2 * cm, fill=True, stroke=False)

        # Logo (texto estilizado)
        c.setFillColor(BRAND_CYAN)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(2 * cm, height - 1.3 * cm, "ConnectaIA")
        c.setFillColor(colors.white)
        c.drawString(5 * cm, height - 1.3 * cm, "Care")

        c.setFillColor(colors.HexColor("#a0aec0"))
        c.setFont("Helvetica", 8)
        c.drawString(2 * cm, height - 1.75 * cm,
                     "Cuidado integrado com IA · Íris Framework")

        # Número + data no canto direito
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 11)
        num = tc.get("human_id") or 0
        c.drawRightString(width - 2 * cm, height - 1.1 * cm,
                          f"Receita Nº {num:04d}")

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#cbd5e0"))
        signed_at = tc.get("signed_at")
        if signed_at:
            try:
                if isinstance(signed_at, str):
                    dt = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
                else:
                    dt = signed_at
                date_str = dt.strftime("%d de %B de %Y · %H:%M")
            except Exception:
                date_str = str(signed_at)[:19]
        else:
            date_str = datetime.now().strftime("%d/%m/%Y · %H:%M")
        c.drawRightString(width - 2 * cm, height - 1.7 * cm, date_str)

        # Faixa de destaque (teleconsulta)
        c.setFillColor(BRAND_TEAL)
        c.rect(0, height - 2.6 * cm, width, 0.4 * cm, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(2 * cm, height - 2.45 * cm,
                     "TELECONSULTA · CFM 2.314/2022 · LGPD Art. 11")

    def _draw_doctor_block(self, c: canvas.Canvas, width: float, y: float, doctor: dict) -> float:
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(2 * cm, y, "PROFISSIONAL")

        y -= 0.55 * cm
        c.setFillColor(TEXT_MAIN)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(2 * cm, y, doctor.get("full_name") or "Médico(a)")

        y -= 0.55 * cm
        c.setFont("Helvetica", 10)
        c.setFillColor(TEXT_MUTED)
        specialty = ", ".join(doctor.get("specialties") or []) or "Medicina"
        crm = doctor.get("crm_number") or doctor.get("crm_display") or ""
        c.drawString(2 * cm, y, f"{specialty} · {crm}")

        y -= 0.6 * cm
        return y

    def _draw_patient_block(self, c: canvas.Canvas, width: float, y: float, patient: dict) -> float:
        # Fundo suave
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.setStrokeColor(BORDER_SOFT)
        c.rect(2 * cm, y - 2.2 * cm, width - 4 * cm, 2.2 * cm, fill=True, stroke=True)

        x = 2.3 * cm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(x, y - 0.45 * cm, "PACIENTE")

        c.setFillColor(TEXT_MAIN)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y - 1.0 * cm, patient.get("full_name") or "Paciente")

        # Idade + unidade
        parts = []
        age = self._calc_age(patient.get("birth_date"))
        if age:
            parts.append(f"{age} anos")
        gender = patient.get("gender")
        if gender:
            parts.append("♀ Feminino" if gender == "female" else "♂ Masculino")
        if patient.get("care_unit"):
            parts.append(str(patient["care_unit"]))

        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(x, y - 1.5 * cm, " · ".join(parts))

        # Alergias em destaque à direita (CRÍTICO em receita)
        allergies = patient.get("allergies") or []
        if allergies:
            c.setFillColor(DANGER)
            c.setFont("Helvetica-Bold", 8)
            c.drawRightString(width - 2.3 * cm, y - 0.8 * cm,
                              "⚠ ALERGIAS DECLARADAS")
            c.setFont("Helvetica", 9)
            allergy_text = ", ".join(str(a) for a in allergies[:4])
            c.drawRightString(width - 2.3 * cm, y - 1.3 * cm, allergy_text)

        return y - 2.6 * cm

    def _draw_prescription(
        self, c: canvas.Canvas, width: float, y: float, items: list[dict],
    ) -> float:
        # Título
        c.setFillColor(BRAND_TEAL)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, y, "PRESCRIÇÃO")

        c.setStrokeColor(BRAND_TEAL)
        c.setLineWidth(1.5)
        c.line(2 * cm, y - 0.15 * cm, width - 2 * cm, y - 0.15 * cm)

        y -= 0.8 * cm

        if not items:
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(2 * cm, y, "Nenhum medicamento prescrito nesta consulta.")
            return y - 0.8 * cm

        for i, item in enumerate(items, 1):
            # Numeração
            c.setFillColor(BRAND_CYAN)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(2 * cm, y, f"{i})")

            # Nome + dose
            c.setFillColor(TEXT_MAIN)
            c.setFont("Helvetica-Bold", 12)
            name_parts = [item.get("medication") or "Medicação"]
            if item.get("dose"):
                name_parts.append(str(item["dose"]))
            c.drawString(2.6 * cm, y, " ".join(name_parts))

            y -= 0.55 * cm

            # Posologia em linha separada, com bullet
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica", 10)
            schedule = item.get("schedule") or "Conforme orientação"
            duration = item.get("duration")
            line = f"   Tomar: {schedule}"
            if duration:
                line += f"  ·  Duração: {duration}"
            c.drawString(2.6 * cm, y, line)

            if item.get("indication"):
                y -= 0.45 * cm
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(2.6 * cm, y, f"   Indicação: {item['indication']}")

            # Alerta de validação se houver issues sérios
            validation = item.get("validation") or {}
            severity = validation.get("severity")
            if severity in ("high", "critical", "moderate"):
                y -= 0.45 * cm
                c.setFillColor(DANGER if severity in ("high", "critical") else colors.HexColor("#f59e0b"))
                c.setFont("Helvetica-Bold", 8)
                c.drawString(2.6 * cm, y, f"⚠ Atenção clínica: {severity.upper()} — revisar antes de dispensar")

            y -= 0.8 * cm
            c.setStrokeColor(BORDER_SOFT)
            c.setLineWidth(0.3)
            c.line(2.6 * cm, y + 0.3 * cm, width - 2 * cm, y + 0.3 * cm)

        return y

    def _draw_orientations(
        self, c: canvas.Canvas, width: float, y: float, soap: dict,
    ) -> float:
        plan = soap.get("plan") or {}
        non_pharma = plan.get("non_pharmacological") or []
        follow_up = plan.get("return_follow_up") or {}
        trigger_signs = follow_up.get("trigger_signs") or []

        if not non_pharma and not follow_up.get("when") and not trigger_signs:
            return y

        if y < 8 * cm:
            c.showPage()
            y = A4[1] - 2 * cm

        c.setFillColor(BRAND_TEAL)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, y, "ORIENTAÇÕES")
        c.setStrokeColor(BRAND_TEAL)
        c.setLineWidth(1.5)
        c.line(2 * cm, y - 0.15 * cm, width - 2 * cm, y - 0.15 * cm)
        y -= 0.7 * cm

        c.setFillColor(TEXT_MAIN)
        c.setFont("Helvetica", 10)
        for tip in non_pharma[:8]:
            text = self._normalize_item(tip)
            if text:
                y = self._draw_wrapped_line(c, 2.2 * cm, y, f"• {text}", width - 4 * cm)

        # Retorno
        if follow_up.get("when"):
            y -= 0.3 * cm
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2 * cm, y, "Retorno:")
            c.setFont("Helvetica", 10)
            c.setFillColor(TEXT_MAIN)
            c.drawString(3.3 * cm, y, str(follow_up.get("when"))[:120])
            y -= 0.5 * cm

        # Sinais de alerta
        if trigger_signs:
            y -= 0.2 * cm
            c.setFillColor(DANGER)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2 * cm, y, "⚠ Procure pronto-socorro imediatamente se:")
            y -= 0.5 * cm
            c.setFillColor(TEXT_MAIN)
            c.setFont("Helvetica", 10)
            for sign in trigger_signs[:6]:
                text = self._normalize_item(sign)
                if text:
                    y = self._draw_wrapped_line(c, 2.2 * cm, y, f"• {text}", width - 4 * cm)

        return y - 0.3 * cm

    def _draw_signature_and_qr(
        self,
        c: canvas.Canvas,
        width: float,
        tc: dict,
        doctor: dict,
        verify_base_url: str,
    ):
        """Rodapé com assinatura eletrônica + QR code de verificação."""
        # Linha horizontal decorativa
        c.setStrokeColor(BRAND_CYAN)
        c.setLineWidth(1)
        c.line(2 * cm, 5.2 * cm, width - 2 * cm, 5.2 * cm)

        # Bloco de assinatura (lado esquerdo)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(2 * cm, 5 * cm, "ASSINATURA ELETRÔNICA")

        c.setFillColor(TEXT_MAIN)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, 4.4 * cm, doctor.get("full_name") or "Médico(a)")

        crm = doctor.get("crm_number") or ""
        c.setFont("Helvetica", 9)
        c.setFillColor(TEXT_MUTED)
        c.drawString(2 * cm, 3.95 * cm, crm)

        # Hash truncado pra evidência de integridade
        tc_id = str(tc.get("id") or "")
        evidence = hashlib.sha256(tc_id.encode()).hexdigest()[:16]
        c.setFont("Courier", 7)
        c.drawString(2 * cm, 3.55 * cm, f"Evidência: {evidence}")
        c.drawString(2 * cm, 3.25 * cm, f"Método: assinatura eletrônica (demo)")
        c.drawString(2 * cm, 2.95 * cm, "Produção: Vidaas / ICP-Brasil / CFM 2.314/2022")

        # QR code (lado direito)
        verify_url = f"{verify_base_url}/verificar/{tc_id}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(verify_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buf = BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)

        qr_x = width - 5.5 * cm
        qr_y = 2.5 * cm
        c.drawImage(
            ImageReader(qr_buf), qr_x, qr_y,
            width=3 * cm, height=3 * cm, preserveAspectRatio=True,
        )
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7)
        c.drawCentredString(qr_x + 1.5 * cm, qr_y - 0.3 * cm,
                            "Verifique a autenticidade")
        c.setFont("Helvetica-Oblique", 6)
        c.drawCentredString(qr_x + 1.5 * cm, qr_y - 0.65 * cm,
                            "Aponte a câmera do celular ao QR")

        # Rodapé final
        c.setFillColor(BRAND_DARK)
        c.rect(0, 0, width, 1.3 * cm, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 7)
        c.drawString(2 * cm, 0.75 * cm,
                     "ConnectaIACare · Plataforma integrada de cuidado geriátrico assistido por IA")
        c.drawString(2 * cm, 0.4 * cm,
                     "care.connectaia.com.br · suporte@connectaia.com.br · CNPJ XX.XXX.XXX/0001-XX")
        c.setFont("Helvetica-Oblique", 6)
        c.drawRightString(width - 2 * cm, 0.5 * cm,
                          "Este documento é pessoal, intransferível e protegido pela LGPD.")

    # ======================================================================
    # Helpers
    # ======================================================================

    @staticmethod
    def _calc_age(birth_date) -> int | None:
        if not birth_date:
            return None
        try:
            if isinstance(birth_date, str):
                bd = datetime.strptime(birth_date.split("T")[0], "%Y-%m-%d").date()
            else:
                bd = birth_date
            today = datetime.now().date()
            return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except Exception:
            return None

    @staticmethod
    def _normalize_item(item) -> str:
        """Converte objetos em strings pra renderizar. Espelha toDisplayString do frontend."""
        if item is None:
            return ""
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            # campos comuns
            for k in ("description", "text", "item", "name", "medication"):
                if item.get(k):
                    return str(item[k])
            return json.dumps(item, ensure_ascii=False)
        return str(item)

    @staticmethod
    def _draw_wrapped_line(
        c: canvas.Canvas, x: float, y: float, text: str, max_width: float,
    ) -> float:
        """Desenha texto com quebra simples de linha por largura."""
        # Quebra ingênua por palavra — suficiente pra prescrição
        words = text.split()
        line = ""
        line_height = 0.4 * cm
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, "Helvetica", 10) <= max_width:
                line = test
            else:
                c.drawString(x, y, line)
                y -= line_height
                line = word
        if line:
            c.drawString(x, y, line)
            y -= line_height
        return y


# Import lazy — ImageReader precisa ser do módulo correto
from reportlab.lib.utils import ImageReader  # noqa: E402


_instance: PrescriptionPdfService | None = None


def get_prescription_pdf_service() -> PrescriptionPdfService:
    global _instance
    if _instance is None:
        _instance = PrescriptionPdfService()
    return _instance
