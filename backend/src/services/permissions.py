"""Permissions/RBAC central — fundação dos Blocos C (perfis customizáveis) e D.

Permissões são strings no formato `recurso:ação[:escopo]`, ex:
    "patients:read"
    "patients:write"
    "events:read"
    "users:write"
    "*"  → wildcard, acesso total

Resolução em cascata (precedência decrescente):
    1. user.permissions  — override explícito (admin pode forçar lista por user)
    2. profile.permissions — perfil customizado (Bloco C, tabela aia_health_profiles)
    3. ROLE_PERMISSIONS[role] — fallback hardcoded por role

Mantemos o fallback hardcoded simples e explícito. Quando alguém criar perfil
custom no admin, o profile_id do user vence o fallback automaticamente.
"""
from __future__ import annotations

# ROLE_PERMISSIONS — fallback quando user/profile não têm permissions explícitas.
# Manter conservador: cada role recebe o mínimo viável pra seu trabalho.
# super_admin tem "*" (acesso total).
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["*"],
    "admin_tenant": [
        "patients:read", "patients:write",
        "events:read", "events:write",
        "reports:read",
        "caregivers:read", "caregivers:write",
        "teleconsulta:read", "teleconsulta:create",
        "medications:read", "medications:write",
        "alerts:read", "alerts:resolve",
        "users:read", "users:write",
        "profiles:read", "profiles:write",
        "tenant:read", "tenant:write",
        "audit:read",
    ],
    "medico": [
        "patients:read", "patients:write",
        "events:read", "events:write",
        "reports:read",
        "teleconsulta:read", "teleconsulta:create", "teleconsulta:sign",
        "medications:read", "medications:write", "medications:prescribe",
        "alerts:read", "alerts:resolve",
        "soap:read", "soap:write",
    ],
    "enfermeiro": [
        "patients:read",
        "events:read", "events:write",
        "reports:read",
        "medications:read", "medications:confirm",
        "alerts:read", "alerts:resolve",
        "vital_signs:read", "vital_signs:write",
        "teleconsulta:read",
    ],
    "cuidador_pro": [
        "patients:read",
        "reports:read", "reports:write",
        "medications:read", "medications:confirm",
        "events:read",
    ],
    "familia": [
        "patients:read:own",
        "events:read:own",
        "reports:read:own",
        "medications:read:own",
        "teleconsulta:read:own",
    ],
    "parceiro": [
        "patients:read:scoped",   # só dentro de allowed_patient_ids
        "events:read:scoped",
        "reports:read:scoped",
        "dashboard:read:partner",
    ],
}


def resolve_permissions(
    user: dict,
    profile_permissions: list[str] | None = None,
) -> list[str]:
    """Calcula a lista efetiva de permissões para um usuário.

    Cadeia: explicit user.permissions > profile.permissions > ROLE_PERMISSIONS[role].
    """
    explicit = user.get("permissions") or []
    if isinstance(explicit, list) and explicit:
        return explicit
    if profile_permissions:
        return list(profile_permissions)
    role = (user.get("role") or "").lower()
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(permissions: list[str], required: str) -> bool:
    """Verifica se a lista contém a permission ou wildcard."""
    if not permissions:
        return False
    if "*" in permissions:
        return True
    if required in permissions:
        return True
    # Suporta wildcards parciais: "patients:*" cobre "patients:read", "patients:write".
    if ":" in required:
        resource, _ = required.split(":", 1)
        if f"{resource}:*" in permissions:
            return True
    return False


def has_role(user_payload: dict, *roles: str) -> bool:
    """user_payload aqui é o JWT decodificado (ou g.user)."""
    return (user_payload or {}).get("role") in roles
