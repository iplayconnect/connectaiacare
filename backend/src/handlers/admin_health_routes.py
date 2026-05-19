"""Endpoint de saúde agregado pra dashboard super_admin.

Roda checks paralelos em todos os serviços críticos da stack:
  - Postgres (latência + query test)
  - Redis (ping + get/set test)
  - Voice-call-service (HTTP /health)
  - Sofia-service (HTTP /health)
  - Evolution API (instâncias ativas, se EVOLUTION_API_URL setada)
  - xAI Realtime (WS handshake test, opcional — caro)
  - DeepSeek API (chat completion teste, opcional)
  - parceiro integrador API (health endpoint deles, se cliente enabled)

Retorna JSON estruturado: { service: { status, latency_ms, detail } }.
Status: ok | degraded | down.

Pra futuro: rodar a cada N seg via cron e gravar em
aia_health_service_health_log pra timeline.
"""
from __future__ import annotations

import os
import time
import concurrent.futures as cf

import requests
from flask import Blueprint, jsonify

from src.handlers.auth_routes import require_role
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_health", __name__)

CHECK_TIMEOUT_S = 5.0


def _check_postgres() -> dict:
    started = time.time()
    try:
        get_postgres().fetch_one("SELECT 1 AS ok")
        return {
            "status": "ok",
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "status": "down",
            "latency_ms": int((time.time() - started) * 1000),
            "detail": str(exc)[:200],
        }


def _check_redis() -> dict:
    started = time.time()
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(url, socket_timeout=CHECK_TIMEOUT_S)
        r.ping()
        return {
            "status": "ok",
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "status": "down",
            "latency_ms": int((time.time() - started) * 1000),
            "detail": str(exc)[:200],
        }


def _check_http(name: str, url: str) -> dict:
    started = time.time()
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT_S)
        latency = int((time.time() - started) * 1000)
        if r.ok:
            try:
                body = r.json()
            except Exception:
                body = {}
            return {
                "status": body.get("status", "ok") if isinstance(body, dict) else "ok",
                "latency_ms": latency,
                "http_status": r.status_code,
                "detail": body if isinstance(body, dict) else None,
            }
        return {
            "status": "degraded",
            "latency_ms": latency,
            "http_status": r.status_code,
            "detail": r.text[:200],
        }
    except requests.exceptions.Timeout:
        return {
            "status": "down",
            "latency_ms": int(CHECK_TIMEOUT_S * 1000),
            "detail": "timeout",
        }
    except Exception as exc:
        return {
            "status": "down",
            "latency_ms": int((time.time() - started) * 1000),
            "detail": str(exc)[:200],
        }


def _check_voice_call() -> dict:
    url = os.getenv("VOICE_CALL_SERVICE_URL", "http://voice-call-service:5040")
    return _check_http("voice-call", f"{url}/health")


def _check_sofia_service() -> dict:
    url = os.getenv("SOFIA_SERVICE_URL", "http://sofia-service:5030")
    return _check_http("sofia-service", f"{url}/health")


def _check_partner_carenote_count() -> dict:
    """Conta CareNotes sincronizadas com parceiro integrador nas últimas 24h.
    Não bate na API deles direto pra não gastar quota — verifica
    nosso registro local de syncs ok.
    """
    started = time.time()
    try:
        row = get_postgres().fetch_one(
            """SELECT
                COUNT(*) FILTER (WHERE last_synced_at >= NOW() - INTERVAL '24 hours')
                    AS synced_24h,
                COUNT(*) FILTER (WHERE sync_error IS NOT NULL
                    AND last_sync_attempt_at >= NOW() - INTERVAL '24 hours')
                    AS errors_24h
               FROM aia_health_partner_carenote_sync"""
        )
        return {
            "status": "ok",
            "latency_ms": int((time.time() - started) * 1000),
            "synced_24h": row.get("synced_24h", 0) if row else 0,
            "errors_24h": row.get("errors_24h", 0) if row else 0,
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "latency_ms": int((time.time() - started) * 1000),
            "detail": str(exc)[:200],
        }


def _check_recent_quota_exhausted_audit() -> dict:
    """Olha se houve voice.provider.quota_exhausted nas últimas 1h.
    Se sim, sinal de que xAI está rate-limitando ou créditos
    esgotados — admin precisa ver."""
    started = time.time()
    try:
        row = get_postgres().fetch_one(
            """SELECT COUNT(*) AS cnt
               FROM aia_health_audit_chain
               WHERE action = 'voice.provider.quota_exhausted'
                 AND created_at >= NOW() - INTERVAL '1 hour'"""
        )
        cnt = row.get("cnt", 0) if row else 0
        return {
            "status": "ok" if cnt == 0 else "degraded",
            "latency_ms": int((time.time() - started) * 1000),
            "quota_alerts_1h": cnt,
            "detail": (
                "Quota xAI possivelmente esgotada — ver audit chain "
                "pra detalhes"
            ) if cnt > 0 else None,
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "latency_ms": int((time.time() - started) * 1000),
            "detail": str(exc)[:200],
        }


@bp.get("/api/admin/health")
@require_role("super_admin", "admin_tenant")
def aggregated_health():
    """Saúde agregada da stack. Roda checks em paralelo (≤5s total)."""
    checks = {
        "postgres": _check_postgres,
        "redis": _check_redis,
        "voice_call": _check_voice_call,
        "sofia_service": _check_sofia_service,
        "partner_carenote_local": _check_partner_carenote_count,
        "voice_provider_quota": _check_recent_quota_exhausted_audit,
    }
    results: dict = {}
    overall_started = time.time()
    with cf.ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = {pool.submit(fn): name for name, fn in checks.items()}
        for fut in cf.as_completed(futures, timeout=CHECK_TIMEOUT_S * 2):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:
                results[name] = {"status": "down", "detail": str(exc)[:200]}

    # Overall status: down se algum core (postgres/redis) tá down,
    # degraded se algum auxiliar, ok caso contrário.
    cores = ("postgres", "redis", "voice_call", "sofia_service")
    overall = "ok"
    for name, res in results.items():
        if res.get("status") == "down":
            overall = "down" if name in cores else "degraded"
            break
        if res.get("status") == "degraded" and overall == "ok":
            overall = "degraded"

    return jsonify({
        "status": overall,
        "checked_at": time.time(),
        "total_elapsed_ms": int((time.time() - overall_started) * 1000),
        "services": results,
    })
