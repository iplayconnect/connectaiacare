"""Webhook WhatsApp · versão assíncrona (Phase B).

Refatora o `/webhook/whatsapp` original pra:
1. Validar + idempotência (Redis SETNX por message_id)
2. Resolver tenant via `instance_name` no path
3. Despachar pra event bus (Redis Streams `sofia:inbound`)
4. Responder <100ms

O processamento pesado (transcrição, LLM, side-effects) fica num
worker pool dedicado consumindo `sofia:inbound`.

URLs novas:
    POST /webhook/whatsapp/v2/<instance_name>

URL legada:
    POST /webhook/whatsapp           (continua síncrono, fallback)

Feature flag `ASYNC_WEBHOOK_ENABLED` (env) liga/desliga.

Migração:
1. Mantemos AMBAS as URLs ativas
2. Configurar Evolution pra postar em /v2/<instance> por tenant
3. Quando 100% do tráfego estiver na v2, deprecar a legada
"""
from __future__ import annotations

import os
import time
import uuid

from flask import Blueprint, jsonify, request

from src.services.audit_log_writer import redact_phone, write_audit
from src.services.event_bus import Streams, get_event_bus
from src.services.idempotency import is_first_occurrence
from src.services.tenant_resolver import get_tenant_resolver
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("webhook_async", __name__)

ASYNC_WEBHOOK_ENABLED = os.getenv("ASYNC_WEBHOOK_ENABLED", "true").lower() == "true"


@bp.post("/webhook/whatsapp/v2/<instance_name>")
def whatsapp_webhook_v2(instance_name: str):
    """Webhook assíncrono. Resposta <100ms. Phase B."""
    started_ns = time.perf_counter_ns()

    if not ASYNC_WEBHOOK_ENABLED:
        return jsonify({
            "status": "error",
            "reason": "async_webhook_disabled",
        }), 503

    event = request.get_json(silent=True)
    if event is None:
        logger.warning("webhook_v2_invalid_json", instance=instance_name)
        return jsonify({"status": "error", "reason": "invalid_json"}), 400

    # 1. Idempotência: extract message_id do Evolution
    msg_id = _extract_message_id(event)
    trace_id = str(uuid.uuid4())

    if msg_id and not is_first_occurrence("wa_msg", msg_id):
        logger.debug(
            "webhook_v2_duplicate",
            msg_id=msg_id, instance=instance_name, trace_id=trace_id,
        )
        return jsonify({
            "status": "ok",
            "reason": "duplicate_skipped",
            "trace_id": trace_id,
        }), 200

    # 2. Tenant resolve
    tenant = get_tenant_resolver().from_evolution_instance(instance_name)
    if tenant is None:
        # Tenant não encontrado pra essa instância → audit + ignore
        logger.warning(
            "webhook_v2_unknown_instance",
            instance=instance_name, trace_id=trace_id,
        )
        write_audit(
            action="webhook_unknown_instance",
            actor="system",
            payload={"instance": instance_name, "trace_id": trace_id},
        )
        return jsonify({
            "status": "ignored",
            "reason": "unknown_instance",
            "trace_id": trace_id,
        }), 200

    # 3. Despacha pra event bus
    try:
        entry_id = get_event_bus().publish(Streams.INBOUND, {
            "event_type": "whatsapp_inbound",
            "tenant_id": tenant.id,
            "instance": instance_name,
            "trace_id": trace_id,
            "received_at": time.time(),
            "payload": event,
            "msg_id": msg_id,
        })
    except Exception as exc:
        logger.exception("webhook_v2_publish_failed", trace_id=trace_id)
        # Fail-soft: retorna 200 pra Evolution não desabilitar webhook
        # (ela faz isso após N falhas consecutivas). Audit pra investigar.
        write_audit(
            action="webhook_publish_failed",
            actor="system",
            tenant_id=tenant.id,
            trace_id=trace_id,
            payload={
                "instance": instance_name,
                "error": str(exc)[:200],
            },
        )
        return jsonify({
            "status": "error",
            "reason": "publish_failed",
            "trace_id": trace_id,
        }), 200

    # 4. Audit redacted (não persiste payload completo aqui — fica
    # em sofia_messages quando worker processar)
    phone_redacted = redact_phone(_extract_phone(event))
    write_audit(
        action="webhook_received",
        actor="system",
        tenant_id=tenant.id,
        trace_id=trace_id,
        payload={
            "instance": instance_name,
            "msg_id": msg_id,
            "phone_redacted": phone_redacted,
            "msg_type": _detect_message_type(event),
            "stream_entry_id": entry_id,
        },
    )

    duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    logger.info(
        "webhook_v2_queued",
        tenant_id=tenant.id,
        instance=instance_name,
        trace_id=trace_id,
        msg_id=msg_id,
        duration_ms=round(duration_ms, 2),
    )

    return jsonify({
        "status": "queued",
        "trace_id": trace_id,
        "stream_entry_id": entry_id,
    }), 200


# ──────────────────────────────────────────────────────────────────
# Helpers (extraem campos do payload Evolution sem importar pipeline)
# ──────────────────────────────────────────────────────────────────


def _extract_message_id(event: dict) -> str | None:
    """Tenta achar message id no payload Evolution. Pode ser:
    - data.key.id
    - data.message.id (alguns)
    - id (top-level)
    """
    if not isinstance(event, dict):
        return None
    # data.key.id (mais comum)
    data = event.get("data") or event
    key = data.get("key") if isinstance(data, dict) else None
    if isinstance(key, dict) and key.get("id"):
        return str(key["id"])
    # message.id
    msg = data.get("message") if isinstance(data, dict) else None
    if isinstance(msg, dict) and msg.get("id"):
        return str(msg["id"])
    # top-level
    if event.get("id"):
        return str(event["id"])
    return None


def _extract_phone(event: dict) -> str | None:
    """Phone do remetente. Evolution coloca em data.key.remoteJid
    (formato 555199...@s.whatsapp.net)."""
    if not isinstance(event, dict):
        return None
    data = event.get("data") or event
    key = data.get("key") if isinstance(data, dict) else None
    if isinstance(key, dict):
        jid = key.get("remoteJid")
        if jid and "@" in jid:
            return jid.split("@")[0]
    return None


def _detect_message_type(event: dict) -> str:
    """text|audio|image|video|document|unknown."""
    if not isinstance(event, dict):
        return "unknown"
    data = event.get("data") or event
    msg = data.get("message") if isinstance(data, dict) else None
    if not isinstance(msg, dict):
        return "unknown"
    if "conversation" in msg or "extendedTextMessage" in msg:
        return "text"
    if "audioMessage" in msg:
        return "audio"
    if "imageMessage" in msg:
        return "image"
    if "videoMessage" in msg:
        return "video"
    if "documentMessage" in msg:
        return "document"
    return "unknown"
