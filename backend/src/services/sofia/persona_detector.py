"""Sofia Persona Detector

Determina a persona de uma mensagem. Duas portas de entrada:

  • App autenticado: JWT já decodificado (g.user). Mapeia role direto.
  • WhatsApp webhook: phone E.164. Procura em users → caregivers →
    patients (responsible.phone) → fallback paciente_b2c se houver
    subscription_active. Senão, anonymous.

Personas devolvidas (mesma lista do CHECK em sofia_sessions):
    cuidador_pro, familia, medico, enfermeiro, admin_tenant,
    super_admin, paciente_b2c, parceiro, anonymous

Uso típico em handlers:
    persona_ctx = persona_detector.from_jwt(jwt_payload)
    persona_ctx = persona_detector.from_phone(phone)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


VALID_PERSONAS = {
    "cuidador_pro", "familia", "medico", "enfermeiro",
    "admin_tenant", "super_admin", "paciente_b2c", "parceiro",
    "anonymous",
}


@dataclass
class PersonaContext:
    """Resultado da detecção. None em campos quando não aplicável.

    Tudo que o orchestrator precisa pra montar prompt + RBAC + scope.
    """
    persona: str
    tenant_id: str = "connectaiacare_demo"
    user_id: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    permissions: list[str] = field(default_factory=list)
    # Vínculos (populados conforme persona)
    caregiver_id: str | None = None
    patient_id: str | None = None
    allowed_patient_ids: list[str] = field(default_factory=list)
    partner_org: str | None = None
    plan_sku: str | None = None
    subscription_active: bool = False

    @property
    def is_operator(self) -> bool:
        """Operadores estão sujeitos a time window (medico, enfermeiro,
        admin). Pacientes/familiares/parceiros não."""
        return self.persona in {
            "medico", "enfermeiro", "admin_tenant", "super_admin",
        }

    @property
    def consumes_quota(self) -> bool:
        """Quem consome cota de tokens (B2C com plano)."""
        return self.persona in {"paciente_b2c", "familia"} and bool(self.plan_sku)


def from_jwt(jwt_payload: dict) -> PersonaContext:
    """Resolve a partir de g.user (JWT já validado)."""
    if not jwt_payload:
        return PersonaContext(persona="anonymous")

    role = (jwt_payload.get("role") or "").lower()
    persona = role if role in VALID_PERSONAS else "anonymous"

    # Carrega plan_sku/subscription via DB (não vem no JWT pra evitar staleness)
    user_id = jwt_payload.get("sub")
    plan_sku: str | None = None
    sub_active = False
    if user_id:
        row = get_postgres().fetch_one(
            "SELECT plan_sku, subscription_active "
            "FROM aia_health_users WHERE id = %s",
            (user_id,),
        )
        if row:
            plan_sku = row.get("plan_sku")
            sub_active = bool(row.get("subscription_active"))

    return PersonaContext(
        persona=persona,
        tenant_id=jwt_payload.get("tenant_id") or "connectaiacare_demo",
        user_id=str(user_id) if user_id else None,
        full_name=jwt_payload.get("name"),
        email=jwt_payload.get("email"),
        role=role or None,
        permissions=list(jwt_payload.get("permissions") or []),
        caregiver_id=jwt_payload.get("caregiver_id"),
        patient_id=jwt_payload.get("patient_id"),
        allowed_patient_ids=list(jwt_payload.get("allowed_patient_ids") or []),
        partner_org=jwt_payload.get("partner_org"),
        plan_sku=plan_sku,
        subscription_active=sub_active,
    )


def from_phone(phone: str, tenant_id: str = "connectaiacare_demo") -> PersonaContext:
    """Resolve persona a partir de telefone E.164 (WhatsApp).

    Prioridade:
      1. user_id em aia_health_users.phone (qualquer role)
      2. caregiver em aia_health_caregivers.phone
      3. patient.responsible.phone (paciente cadastrado, familiar respondeu)
      4. fallback paciente_b2c se subscription_active=true em qualquer user
      5. anonymous
    """
    if not phone:
        return PersonaContext(persona="anonymous", tenant_id=tenant_id)

    pg = get_postgres()
    digits = "".join(c for c in phone if c.isdigit())

    # 1. user direto
    user_row = pg.fetch_one(
        """
        SELECT id, tenant_id, full_name, email, role, permissions, profile_id,
               caregiver_id, patient_id, allowed_patient_ids, partner_org,
               plan_sku, subscription_active
        FROM aia_health_users
        WHERE regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = %s
          AND active = TRUE
        ORDER BY CASE role
            WHEN 'super_admin' THEN 0 WHEN 'admin_tenant' THEN 1
            WHEN 'medico' THEN 2 WHEN 'enfermeiro' THEN 3
            ELSE 4 END
        LIMIT 1
        """,
        (digits,),
    )
    if user_row:
        return PersonaContext(
            persona=user_row["role"],
            tenant_id=user_row["tenant_id"],
            user_id=str(user_row["id"]),
            full_name=user_row.get("full_name"),
            email=user_row.get("email"),
            phone=digits,
            role=user_row.get("role"),
            permissions=list(user_row.get("permissions") or []),
            caregiver_id=str(user_row["caregiver_id"]) if user_row.get("caregiver_id") else None,
            patient_id=str(user_row["patient_id"]) if user_row.get("patient_id") else None,
            allowed_patient_ids=list(user_row.get("allowed_patient_ids") or []),
            partner_org=user_row.get("partner_org"),
            plan_sku=user_row.get("plan_sku"),
            subscription_active=bool(user_row.get("subscription_active")),
        )

    # 2. caregiver standalone (cuidador sem login web ainda)
    cg = pg.fetch_one(
        """
        SELECT id, tenant_id, full_name, phone
        FROM aia_health_caregivers
        WHERE regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = %s
          AND active = TRUE
        LIMIT 1
        """,
        (digits,),
    )
    if cg:
        return PersonaContext(
            persona="cuidador_pro",
            tenant_id=cg["tenant_id"],
            full_name=cg.get("full_name"),
            phone=digits,
            caregiver_id=str(cg["id"]),
        )

    # 3. familiar via responsible.phone do paciente
    fam = pg.fetch_one(
        """
        SELECT id, tenant_id, full_name, responsible
        FROM aia_health_patients
        WHERE responsible->>'phone' IS NOT NULL
          AND regexp_replace(responsible->>'phone', '[^0-9]', '', 'g') = %s
          AND active = TRUE
        LIMIT 1
        """,
        (digits,),
    )
    if fam:
        return PersonaContext(
            persona="familia",
            tenant_id=fam["tenant_id"],
            full_name=(fam.get("responsible") or {}).get("name"),
            phone=digits,
            patient_id=str(fam["id"]),
        )

    # 4/5. desconhecido
    logger.info("persona_unknown_phone", phone_digits=digits, tenant_id=tenant_id)
    return PersonaContext(persona="anonymous", tenant_id=tenant_id, phone=digits)
