"""JWT utils (HS256) sem dependências externas.

Adaptado do ConnectaIA — assina/verifica JWT pra auth do CRM (Bearer token).
Mesmo formato (header.payload.signature, base64url) e algoritmo (HMAC-SHA256).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class JWTError(Exception):
    """Erro de codificação/decodificação de JWT."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def jwt_encode(payload: dict[str, Any], secret: str, exp_seconds: int = 86400) -> str:
    if not secret:
        raise JWTError("JWT_SECRET not configured")

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {**payload, "iat": now, "exp": now + int(exp_seconds)}

    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def jwt_decode(token: str, secret: str) -> dict[str, Any]:
    if not secret:
        raise JWTError("JWT_SECRET not configured")
    if not token or token.count(".") != 2:
        raise JWTError("invalid_token_format")

    header_b64, payload_b64, sig_b64 = token.split(".", 2)
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(expected_sig_b64, sig_b64):
        raise JWTError("invalid_signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = payload.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise JWTError("token_expired")
    return payload


def extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    parts = auth_header.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
