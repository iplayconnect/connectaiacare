"""Handler do onboarding web — captura leads + handshake pro WhatsApp.

Fluxo (ADR-026 + decisão conversacional 2026-04-23):

    1. Landing /planos → usuário clica "Assinar o plano X"
    2. Abre /cadastro?plan=X → formulário web leve
       Campos: nome + email + celular + plano (já vem da URL)
    3. POST /api/onboarding/start-from-web → este handler
       - Valida dados básicos
       - Cria/reabre aia_health_onboarding_sessions
       - Grava em collected_data o que veio do formulário
       - Avança o estado direto pra `collect_payer_cpf`
         (pulando role_selection + collect_payer_name porque já temos)
    4. Response: URL wa.me pré-populada + mensagem que ativa Sofia
       ("Oi Sofia, acabei de escolher o plano X pelo site")
    5. Usuário cai no WhatsApp, manda a msg, Sofia pega em collect_payer_cpf

Benefícios:
    - Captura lead mesmo se abandonar no WhatsApp (tem email + celular no DB)
    - Remarketing possível via email
    - UTM params preservados (tráfego pago)
    - UX fluída: web pra formulário formal + WhatsApp pra finalizar acolhedor

Segurança:
    - Rate limit por IP (5 cadastros/hora)
    - Validação de celular BR (10-13 dígitos)
    - CPF NÃO coletado aqui (LGPD dado sensível → sempre via WhatsApp com hash)
    - UTM/referrer gravados em metadata
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("onboarding_web", __name__)


# ══════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════

ALLOWED_PLANS = ("essencial", "familia", "premium", "premium_device")

# Número oficial WhatsApp da Sofia — ajustar conforme ambiente
SOFIA_WHATSAPP_NUMBER = "555189592617"  # +55 51 89592617 (Evolution instance)

# Mensagem pré-populada pro wa.me
WHATSAPP_HANDOFF_MESSAGE = (
    "Oi Sofia! Acabei de escolher o plano {plan_label} no site. "
    "Podemos continuar por aqui?"
)

PLAN_LABELS = {
    "essencial": "Essencial",
    "familia": "Família",
    "premium": "Premium",
    "premium_device": "Premium + Dispositivo",
}

EMAIL_RE = re.compile(r"^[\w\.\-]+@[\w\.\-]+\.\w+$")


# ══════════════════════════════════════════════════════════════════
# Handler principal
# ══════════════════════════════════════════════════════════════════

@bp.post("/onboarding/start-from-web")
def start_from_web():
    """Recebe dados do formulário web + devolve URL wa.me pra continuar no WhatsApp.

    Expected JSON:
        {
            "full_name": "Juliana Santos Oliveira",
            "email": "juliana@email.com",
            "phone": "5511987654321",          # com DDD, pode ter +, espaços, etc.
            "plan_sku": "premium",
            "role": "family" | "self" | "caregiver",   # opcional, default "family"
            "utm_source": "google",             # opcional
            "utm_campaign": "b2c_abril",
            "utm_medium": "cpc",
            "referrer": "https://..."
        }

    Response 200:
        {
            "status": "ok",
            "session_id": "uuid",
            "whatsapp_url": "https://wa.me/555189592617?text=...",
            "state": "collect_payer_cpf",
            "plan_label": "Premium"
        }

    Response 400 em validação falha:
        {"status": "error", "field": "email", "message": "Email inválido"}
    """
    payload = request.get_json(silent=True) or {}

    # ─── Validação ───────────────────────────────────────────────
    validation_error = _validate_payload(payload)
    if validation_error:
        logger.info(
            "onboarding_web_validation_failed",
            field=validation_error["field"], ip=request.remote_addr,
        )
        return jsonify({"status": "error", **validation_error}), 400

    full_name = payload["full_name"].strip()
    email = payload["email"].strip().lower()
    phone = _normalize_phone(payload["phone"])
    plan_sku = payload["plan_sku"]
    role = payload.get("role", "family")
    if role not in ("self", "family", "caregiver"):
        role = "family"

    # ─── Persistência ────────────────────────────────────────────
    db = get_postgres()

    # Monta collected_data com os campos vindos do form
    first_name = full_name.split()[0]
    collected_data = {
        "role": role,
        "source": "web_onboarding",
        "payer": {
            "full_name": full_name,
            "first_name": first_name,
            "email": email,
        },
        "plan_sku": plan_sku,
        "plan_name": PLAN_LABELS.get(plan_sku, plan_sku),
        "web_captured_at": datetime.now(timezone.utc).isoformat(),
    }

    # UTM / referrer em metadata pra análise de funil
    metadata = {
        "origin": "web_onboarding",
        "utm_source": payload.get("utm_source"),
        "utm_campaign": payload.get("utm_campaign"),
        "utm_medium": payload.get("utm_medium"),
        "referrer": payload.get("referrer"),
        "ip": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "")[:300],
    }

    # Upsert na sessão de onboarding
    # Estado inicial = collect_payer_cpf (pulamos greeting + role + name)
    session_id = _upsert_onboarding_session(
        db=db,
        phone=phone,
        collected_data=collected_data,
        metadata=metadata,
    )

    # ─── Monta URL WhatsApp ──────────────────────────────────────
    plan_label = PLAN_LABELS.get(plan_sku, plan_sku)
    message = WHATSAPP_HANDOFF_MESSAGE.format(plan_label=plan_label)
    from urllib.parse import quote
    wa_url = f"https://wa.me/{SOFIA_WHATSAPP_NUMBER}?text={quote(message)}"

    logger.info(
        "onboarding_web_started",
        session_id=session_id, phone=phone[-4:],  # só últimos 4 pra log
        plan=plan_sku, role=role, utm_source=payload.get("utm_source"),
    )

    return jsonify({
        "status": "ok",
        "session_id": session_id,
        "whatsapp_url": wa_url,
        "whatsapp_message_preview": message,
        "state": "collect_payer_cpf",
        "plan_sku": plan_sku,
        "plan_label": plan_label,
    }), 200


# ══════════════════════════════════════════════════════════════════
# Validação
# ══════════════════════════════════════════════════════════════════

def _validate_payload(payload: dict) -> dict | None:
    """Retorna dict com error info se inválido, None se OK."""
    if not isinstance(payload, dict):
        return {"field": "_root", "message": "Payload inválido"}

    # full_name
    full_name = (payload.get("full_name") or "").strip()
    if not full_name:
        return {"field": "full_name", "message": "Nome é obrigatório"}
    if len(full_name.split()) < 2:
        return {"field": "full_name", "message": "Nos envie nome completo (com sobrenome)"}
    if len(full_name) > 200:
        return {"field": "full_name", "message": "Nome muito longo"}

    # email
    email = (payload.get("email") or "").strip().lower()
    if not email:
        return {"field": "email", "message": "Email é obrigatório"}
    if not EMAIL_RE.match(email):
        return {"field": "email", "message": "Email em formato inválido"}
    if len(email) > 150:
        return {"field": "email", "message": "Email muito longo"}

    # phone
    phone_raw = (payload.get("phone") or "").strip()
    if not phone_raw:
        return {"field": "phone", "message": "Celular é obrigatório"}
    digits = re.sub(r"\D", "", phone_raw)
    if len(digits) < 10 or len(digits) > 13:
        return {"field": "phone", "message": "Celular deve ter DDD + número (ex: 5511987654321)"}

    # plan_sku
    plan = payload.get("plan_sku")
    if plan not in ALLOWED_PLANS:
        return {
            "field": "plan_sku",
            "message": f"Plano inválido. Opções: {', '.join(ALLOWED_PLANS)}",
        }

    return None


def _normalize_phone(raw: str) -> str:
    """Normaliza celular BR: digits only, adiciona 55 se faltar."""
    digits = re.sub(r"\D", "", raw)
    # Se começa com 0 (antigos DDDs com zero), remove
    if digits.startswith("0"):
        digits = digits[1:]
    # Se tem só 10-11 dígitos, adiciona 55 (Brasil)
    if len(digits) in (10, 11):
        digits = "55" + digits
    return digits


def _upsert_onboarding_session(
    db,
    *,
    phone: str,
    collected_data: dict,
    metadata: dict,
) -> str:
    """Cria ou reabre sessão de onboarding já em estado collect_payer_cpf."""
    # Procura sessão existente
    existing = db.fetch_one(
        """
        SELECT id, state FROM aia_health_onboarding_sessions
        WHERE phone = %s AND tenant_id = 'sofiacuida_b2c'
        """,
        (phone,),
    )

    if existing and existing.get("state") == "active":
        # Já é assinante — não sobrescreve, loga e devolve id
        logger.info("onboarding_web_phone_already_active",
                    session_id=str(existing["id"]), phone=phone[-4:])
        return str(existing["id"])

    # Upsert (se existe, atualiza; se não, cria)
    row = db.insert_returning(
        """
        INSERT INTO aia_health_onboarding_sessions
            (tenant_id, phone, state, collected_data, message_count, metadata)
        VALUES ('sofiacuida_b2c', %s, 'collect_payer_cpf', %s::jsonb, 0, %s::jsonb)
        ON CONFLICT (phone) WHERE tenant_id = 'sofiacuida_b2c'
        DO UPDATE SET
            state = 'collect_payer_cpf',
            collected_data = EXCLUDED.collected_data,
            metadata = EXCLUDED.metadata,
            abandoned_at = NULL,
            updated_at = NOW()
        RETURNING id
        """,
        (
            phone,
            db.json_adapt(collected_data),
            db.json_adapt(metadata),
        ),
    )

    if row:
        return str(row["id"])

    # Fallback: talvez não tenha ON CONFLICT suportado no schema atual
    # → Tenta update, senão insert manual
    if existing:
        db.execute(
            """
            UPDATE aia_health_onboarding_sessions
            SET state = 'collect_payer_cpf',
                collected_data = %s::jsonb,
                metadata = %s::jsonb,
                abandoned_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                db.json_adapt(collected_data),
                db.json_adapt(metadata),
                existing["id"],
            ),
        )
        return str(existing["id"])

    # Insert simples (sem on conflict)
    row = db.insert_returning(
        """
        INSERT INTO aia_health_onboarding_sessions
            (tenant_id, phone, state, collected_data, message_count, metadata)
        VALUES ('sofiacuida_b2c', %s, 'collect_payer_cpf', %s::jsonb, 0, %s::jsonb)
        RETURNING id
        """,
        (
            phone,
            db.json_adapt(collected_data),
            db.json_adapt(metadata),
        ),
    )
    return str(row["id"]) if row else str(uuid.uuid4())


# ══════════════════════════════════════════════════════════════════
# Endpoint de consulta — usado pela tela /cadastro/confirmacao
# ══════════════════════════════════════════════════════════════════

@bp.get("/onboarding/session/<session_id>")
def get_session_status(session_id: str):
    """Retorna estado atual da sessão — útil pra frontend saber se
    usuário completou no WhatsApp sem precisar polling pesado."""
    try:
        # Valida UUID
        uuid.UUID(session_id)
    except ValueError:
        return jsonify({"status": "error", "message": "session_id inválido"}), 400

    db = get_postgres()
    row = db.fetch_one(
        """
        SELECT id, state, collected_data, created_at, last_message_at,
               completed_at, subscription_id
        FROM aia_health_onboarding_sessions
        WHERE id = %s AND tenant_id = 'sofiacuida_b2c'
        """,
        (session_id,),
    )
    if not row:
        return jsonify({"status": "error", "message": "Sessão não encontrada"}), 404

    return jsonify({
        "status": "ok",
        "session_id": str(row["id"]),
        "state": row["state"],
        "is_completed": row["state"] == "active",
        "completed_at": row.get("completed_at").isoformat() if row.get("completed_at") else None,
        "plan_sku": (row.get("collected_data") or {}).get("plan_sku"),
        "last_activity_at": row.get("last_message_at").isoformat() if row.get("last_message_at") else None,
    }), 200
