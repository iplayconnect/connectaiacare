"""Test sintético do fluxo WhatsApp pra perfil IDENTIFICADO (cuidador_pro).

Cria caregiver+patient sintéticos NO TENANT REAL `connectaiacare_demo`
(que é onde o webhook do Evolution `Connectaiacare` resolve), dispara
webhooks simulados via /webhook/whatsapp, observa:

  1. identity_resolver achou o phone como caregiver
  2. factory.get_agent_for retornou passthrough (não commercial)
  3. PassthroughSofiaAgent delegou pro pipeline legado
  4. pipeline.handle_webhook processou (cria session legado, message)
  5. Sofia respondeu via Evolution outbound (sandbox phone fake — não chega)

Cleanup: DELETE caregiver + patient + assignments + sessions + messages
ao final.

Usa phone fake (5551999000888) que NÃO existe no WhatsApp real, então
mesmo Evolution mandando, ninguém recebe nada. Só queremos validar
o pipeline interno até o ponto da resposta.

Pré-requisitos:
  - api + workers em prod healthy
  - sofia-service inbound-worker consumindo sofia:inbound

Uso:
  scp scripts/test_whatsapp_identified_flow.py root@VPS:/tmp/
  ssh VPS 'docker cp /tmp/test_whatsapp_identified_flow.py \\
       connectaiacare-api:/tmp/ && docker exec connectaiacare-api \\
       python /tmp/test_whatsapp_identified_flow.py'
"""
from __future__ import annotations

import json
import sys
import time
import uuid

sys.path.insert(0, "/app")

from src.services.postgres import get_postgres


# Tenant real onde o Evolution Connectaiacare resolve webhooks
TEST_TENANT = "connectaiacare_demo"
TEST_PHONE = "5551999000888"   # phone fake — NÃO existe no WhatsApp real
TEST_PUSH_NAME = "TestSyntheticCaregiver"


# ─── Cenários WhatsApp pra cuidador_pro identificado ─────────────────

SCENARIOS = [
    {
        "name": "1_relato_rotina",
        "text": "Bom dia! Dona Maria acordou bem hoje, tomou o café da manhã, conversou comigo sobre os filhos. PA medi agora: 13 por 8.",
        "expected": [
            "agent=passthrough (perfil=cuidador_pro)",
            "pipeline legado registra report ou conversation message",
            "sem flags Beers (sem menção a med específico)",
        ],
    },
    {
        "name": "2_med_existing_routine",
        "text": "Acabei de dar a losartana 50mg e a metformina dela. Tudo certo até agora.",
        "expected": [
            "drug_safety_service detecta losartana + metformina (cadastradas)",
            "sem alerta (uso normal documentado)",
            "active_context registra meds ativas",
        ],
    },
    {
        "name": "3_med_beers_alta_severidade",
        "text": "A médica receitou diazepam pra ela dormir melhor. Posso começar essa noite?",
        "expected": [
            "evaluate_prescription detecta Beers avoid_in_elderly pra Diazepam",
            "severity=warning_strong",
            "Sofia DEVE alertar cuidador + sugerir alternativa OU escalar humano",
        ],
    },
    {
        "name": "4_med_interacao_risco",
        "text": "Vou dar ibuprofeno pra dor nas costas dela. Pode ser?",
        "expected": [
            "drug_safety detecta interação Losartana + Ibuprofeno (paciente já em IECA)",
            "triple whammy renal alert",
            "Sofia alerta + sugere paracetamol como alternativa",
        ],
    },
]


def cleanup_orphans():
    """Remove caregivers/patients órfãos do test (rodadas anteriores que falharam)."""
    db = get_postgres()
    try:
        rows = db.fetch_all(
            "SELECT id FROM aia_health_caregivers WHERE phone = %s AND tenant_id = %s",
            (TEST_PHONE, TEST_TENANT),
        )
        for r in rows:
            db.execute("DELETE FROM aia_health_caregiver_patient_assignments WHERE caregiver_id = %s", (r["id"],))
            db.execute("DELETE FROM aia_health_caregivers WHERE id = %s", (r["id"],))
        # Patients órfãos do test (sem caregiver agora)
        rows = db.fetch_all(
            "SELECT id FROM aia_health_patients WHERE tenant_id = %s AND nickname = %s",
            (TEST_TENANT, "Vó Teste"),
        )
        for r in rows:
            db.execute("DELETE FROM aia_health_patients WHERE id = %s", (r["id"],))
        if rows:
            print(f"  ✓ orphans cleaned ({len(rows)} patient + caregivers)")
    except Exception as e:
        print(f"  ⚠ orphan cleanup: {str(e)[:120]}")


def setup_test_data() -> tuple[str, str]:
    """Cria caregiver + patient + assignment sintéticos no tenant real."""
    cleanup_orphans()
    db = get_postgres()
    cg_id = str(uuid.uuid4())
    pt_id = str(uuid.uuid4())

    # 1. Caregiver
    db.execute(
        """INSERT INTO aia_health_caregivers (
              id, tenant_id, full_name, phone, phone_type, external_id, active
           ) VALUES (%s, %s, %s, %s, 'personal', %s, TRUE)""",
        (cg_id, TEST_TENANT, "Cuidador Sintético Test",
         TEST_PHONE, f"test_{cg_id[:8]}"),
    )

    # 2. Patient com perfil clínico que vai disparar drug_safety checks
    # (idoso 82a com hipertensão + diabetes + IECA + metformina já em uso)
    conditions_json = json.dumps([
        {"code": "I10", "description": "Hipertensão arterial", "severity": "moderada"},
        {"code": "E11", "description": "Diabetes mellitus tipo 2", "severity": "controlada"},
        {"code": "F03", "description": "Demência leve", "severity": "leve"},
    ])
    medications_json = json.dumps([
        {"name": "Losartana 50mg", "schedule": "08:00, 20:00", "dose": "1 comp"},
        {"name": "Metformina 850mg", "schedule": "08:00, 12:00", "dose": "1 comp"},
    ])
    allergies_json = json.dumps([])
    responsible_json = json.dumps({
        "name": "Cuidador Sintético", "relationship": "cuidador",
        "phone": TEST_PHONE,
    })

    db.execute(
        """INSERT INTO aia_health_patients (
              id, tenant_id, full_name, nickname, birth_date, gender,
              care_level, conditions, medications, allergies, responsible,
              active, serum_creatinine_mg_dl
           ) VALUES (%s, %s, %s, %s, %s, %s, %s,
                     %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                     TRUE, 1.4)""",
        (pt_id, TEST_TENANT, "Paciente Sintético Teste", "Vó Teste",
         "1942-01-01", "F", "semi-dependente",
         conditions_json, medications_json, allergies_json, responsible_json),
    )

    # 3. Assignment caregiver↔patient (campos required: id, tenant_id,
    # relationship, is_primary, active)
    asg_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO aia_health_caregiver_patient_assignments (
              id, tenant_id, caregiver_id, patient_id,
              relationship, is_primary, active
           ) VALUES (%s, %s, %s, %s, 'professional', TRUE, TRUE)""",
        (asg_id, TEST_TENANT, cg_id, pt_id),
    )

    return cg_id, pt_id


def cleanup_test_data(cg_id: str, pt_id: str):
    """Remove caregiver + patient + assignments + sessions + messages."""
    db = get_postgres()
    # Conversation messages do phone (legado e novo)
    try:
        db.execute(
            "DELETE FROM aia_health_conversation_messages WHERE subject_phone = %s AND tenant_id = %s",
            (TEST_PHONE, TEST_TENANT),
        )
    except Exception as e:
        print(f"  ⚠ msg cleanup: {str(e)[:80]}")
    # Legacy sessions
    try:
        db.execute(
            "DELETE FROM aia_health_legacy_conversation_sessions WHERE phone = %s AND tenant_id = %s",
            (TEST_PHONE, TEST_TENANT),
        )
    except Exception as e:
        print(f"  ⚠ legacy sess cleanup: {str(e)[:80]}")
    # Sofia sessions (caso commercial agent tenha criado)
    try:
        db.execute(
            "DELETE FROM aia_health_sofia_sessions WHERE phone = %s",
            (TEST_PHONE,),
        )
    except Exception:
        pass
    # Reports do paciente
    try:
        db.execute(
            "DELETE FROM aia_health_reports WHERE patient_id = %s", (pt_id,),
        )
    except Exception:
        pass
    # Schedules
    try:
        db.execute(
            "DELETE FROM aia_health_medication_schedules WHERE patient_id = %s",
            (pt_id,),
        )
    except Exception:
        pass
    # Assignments (CASCADE pega o resto se houver)
    try:
        db.execute(
            "DELETE FROM aia_health_caregiver_patient_assignments WHERE caregiver_id = %s",
            (cg_id,),
        )
    except Exception:
        pass
    # Caregiver e patient
    db.execute(
        "DELETE FROM aia_health_caregivers WHERE id = %s", (cg_id,),
    )
    db.execute(
        "DELETE FROM aia_health_patients WHERE id = %s", (pt_id,),
    )
    print("  ✓ test data cleaned (caregiver + patient + assignments + sessions + msgs)")


def verify_identity_resolution() -> dict:
    """Confirma que identity_resolver acha o phone como caregiver."""
    from src.services.identity_resolver import get_identity_resolver
    resolver = get_identity_resolver()
    # Invalida cache primeiro pra garantir resolve fresh
    resolver.invalidate(TEST_PHONE)
    identity = resolver.resolve(TEST_PHONE, tenant_id=TEST_TENANT, use_cache=False)
    p = identity.primary
    return {
        "phone": identity.phone,
        "is_anonymous": identity.is_anonymous,
        "primary_profile": p.profile if p else None,
        "primary_source": p.source if p else None,
        "primary_caregiver_id": p.caregiver_id if p else None,
        "primary_confidence": p.confidence if p else None,
        "matches_count": len(identity.matches),
        "matches_profiles": [m.profile for m in identity.matches],
    }


def simulate_webhook(text: str, msg_id: str) -> str:
    """POST direto pra api/webhook/whatsapp simulando Evolution payload.

    Retorna trace_id pro filtragem de logs.
    """
    import urllib.request
    payload = {
        "event": "messages.upsert",
        "instance": "Connectaiacare",
        "data": {
            "key": {
                "remoteJid": f"{TEST_PHONE}@s.whatsapp.net",
                "fromMe": False,
                "id": msg_id,
            },
            "message": {"conversation": text},
            "messageTimestamp": int(time.time()),
            "pushName": TEST_PUSH_NAME,
        },
    }
    req = urllib.request.Request(
        "http://api:5055/webhook/whatsapp",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            return body.get("trace_id", "")
    except Exception as e:
        print(f"  ⚠ webhook failed: {str(e)[:120]}")
        return ""


def inspect_state_for_phone() -> dict:
    """Snapshot do que o pipeline persistiu pra esse phone."""
    db = get_postgres()
    out: dict = {}

    legacy_sess = db.fetch_one(
        """SELECT id, state, context, expires_at, created_at
           FROM aia_health_legacy_conversation_sessions
           WHERE phone = %s AND tenant_id = %s
           ORDER BY created_at DESC LIMIT 1""",
        (TEST_PHONE, TEST_TENANT),
    )
    out["legacy_session"] = dict(legacy_sess) if legacy_sess else None

    sofia_sess = db.fetch_one(
        """SELECT id, caregiver_id, patient_id, channel, started_at
           FROM aia_health_sofia_sessions
           WHERE phone = %s
           ORDER BY started_at DESC LIMIT 1""",
        (TEST_PHONE,),
    )
    out["sofia_session"] = dict(sofia_sess) if sofia_sess else None

    msg_count_row = db.fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_conversation_messages
           WHERE subject_phone = %s AND tenant_id = %s""",
        (TEST_PHONE, TEST_TENANT),
    )
    out["conversation_messages_count"] = (msg_count_row or {}).get("n", 0)

    last_msgs = db.fetch_all(
        """SELECT direction, role, message_format,
                  LEFT(content, 100) AS content_preview,
                  processing_agent, received_at
           FROM aia_health_conversation_messages
           WHERE subject_phone = %s AND tenant_id = %s
           ORDER BY received_at DESC LIMIT 6""",
        (TEST_PHONE, TEST_TENANT),
    )
    out["last_messages"] = [dict(r) for r in (last_msgs or [])]

    return out


def run():
    print("=" * 78)
    print("Test sintético — fluxo WhatsApp pra cuidador_pro IDENTIFICADO")
    print(f"Tenant: {TEST_TENANT}  Phone: {TEST_PHONE}")
    print("=" * 78)

    cg_id, pt_id = setup_test_data()
    print(f"\n  ✓ caregiver={cg_id[:8]} patient={pt_id[:8]}")

    try:
        # ── Validação 1: identity_resolver achou caregiver?
        ident = verify_identity_resolution()
        print(f"\n  identity_resolver:")
        for k, v in ident.items():
            print(f"    {k}: {v}")
        if ident["primary_profile"] != "cuidador_pro":
            print("    ⚠ ATENÇÃO: identity NÃO foi resolvido como cuidador_pro!")
            print(f"    primary_profile={ident['primary_profile']} — pipeline pode rotear pra familia/anonymous.")

        # ── Cenários WhatsApp
        for sc in SCENARIOS:
            print(f"\n>>> {sc['name']}")
            print(f"    text: {sc['text'][:80]}{'...' if len(sc['text']) > 80 else ''}")

            msg_id = f"WSPID_{sc['name']}_{int(time.time())}"
            trace_id = simulate_webhook(sc["text"], msg_id)
            if not trace_id:
                print("    ✗ webhook não respondeu — skip cenário")
                continue
            print(f"    trace_id={trace_id[:8]}")
            print("    expected:")
            for e in sc["expected"]:
                print(f"      • {e}")

            # Aguarda pipeline rodar (worker batch + LLM)
            time.sleep(8)

            state = inspect_state_for_phone()
            ls = state["legacy_session"]
            print(f"    legacy_session: "
                  f"{'state=' + ls['state'] if ls else 'None'}")
            print(f"    sofia_session: "
                  f"{('caregiver=' + str(state['sofia_session'].get('caregiver_id'))[:8] if state['sofia_session'] else 'None')}")
            print(f"    msgs_total={state['conversation_messages_count']}")
            for m in state["last_messages"][:3]:
                print(f"      [{m['direction']:8s}|{m['role']:10s}|"
                      f"{m.get('processing_agent') or '-':20s}] "
                      f"{m.get('content_preview') or '(empty)'}")

        print("\n" + "=" * 78)
        print("✅ Test rodou. Inspeção manual:")
        print(f"   docker logs --since 3m connectaiacare-sofia-inbound-worker-1 | "
              f"grep '{TEST_PHONE}'")
        print(f"   docker logs --since 3m connectaiacare-api 2>&1 | grep '{TEST_PHONE}'")
        print("=" * 78)

    finally:
        print("\n=== CLEANUP ===")
        cleanup_test_data(cg_id, pt_id)


if __name__ == "__main__":
    run()
