"""Smoke E2E dos 9 fluxos críticos pré-piloto.

Valida que cada fluxo crítico está funcional em produção, sem
modificar dados (read-only). Não substitui testes manuais com
usuário real, mas detecta regressões catastróficas rápido.

Uso:
    docker exec -w /app connectaiacare-api python3 scripts/smoke_e2e.py

Saída: relatório markdown com ✅/❌ por fluxo + detalhes.
Exit code 1 se algum fluxo crítico falhar.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.postgres import get_postgres


# ────────────────────────── Helpers ──────────────────────────

class Flow:
    def __init__(self, num: int, name: str):
        self.num = num
        self.name = name
        self.checks: list[tuple[bool, str, str]] = []  # (ok, label, detail)

    def assert_(self, ok: bool, label: str, detail: str = ""):
        self.checks.append((ok, label, detail))

    def passed(self) -> bool:
        return all(c[0] for c in self.checks)

    def render(self) -> str:
        out = [f"\n## Fluxo {self.num}: {self.name} — "
               f"{'✅' if self.passed() else '❌'}"]
        for ok, label, detail in self.checks:
            mark = "✓" if ok else "✗"
            out.append(f"  {mark} {label}{(' — ' + detail) if detail else ''}")
        return "\n".join(out)


def db_count(sql: str, params=()) -> int:
    row = get_postgres().fetch_one(f"SELECT COUNT(*) AS n FROM ({sql}) sub", params)
    return int(row.get("n", 0)) if row else 0


def db_exists(sql: str, params=()) -> bool:
    return get_postgres().fetch_one(sql + " LIMIT 1", params) is not None


# ────────────────────────── Fluxos ──────────────────────────

def f1_login_auth() -> Flow:
    f = Flow(1, "Login + reset senha + lock")
    db = get_postgres()
    f.assert_(
        db_exists("SELECT 1 FROM aia_health_users WHERE active = TRUE"),
        "Há usuários ativos",
    )
    f.assert_(
        db_count("SELECT * FROM aia_health_users WHERE locked_until > NOW()") <
            db_count("SELECT * FROM aia_health_users"),
        "Há usuários não-lockados (sistema operável)",
    )
    super_admins = db_count(
        "SELECT * FROM aia_health_users WHERE role = 'super_admin' AND active = TRUE"
    )
    f.assert_(super_admins >= 1, f"≥1 super_admin ativo ({super_admins})")
    f.assert_(
        db_exists(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'aia_health_password_reset_tokens'"
        ),
        "Tabela password_reset_tokens existe",
    )
    return f


def f2_patients_crud() -> Flow:
    f = Flow(2, "Cadastro paciente + edição")
    n = db_count("SELECT * FROM aia_health_patients WHERE active = TRUE")
    f.assert_(n > 0, f"Há pacientes ativos ({n})")
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_patients "
            "WHERE active = TRUE AND tecnosenior_patient_id IS NOT NULL"
        ),
        "≥1 paciente com mapeamento Tecnosenior (pra teste sync)",
    )
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_patients "
            "WHERE active = TRUE AND cpf IS NOT NULL AND cpf != ''"
        ),
        "≥1 paciente com CPF cadastrado",
    )
    return f


def f3_caregivers() -> Flow:
    f = Flow(3, "Cadastro cuidador + assignment paciente↔cuidador")
    n_cg = db_count(
        "SELECT * FROM aia_health_caregivers WHERE active = TRUE"
    )
    f.assert_(n_cg > 0, f"Há cuidadores ativos ({n_cg})")
    n_assign = db_count(
        "SELECT * FROM aia_health_caregiver_patient_assignments"
    )
    f.assert_(
        n_assign >= 0,  # tabela existe (count > 0 ideal mas não obrigatório)
        f"Tabela assignments operacional ({n_assign} vínculos)",
    )
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_caregivers "
            "WHERE active = TRUE AND tecnosenior_caretaker_id IS NOT NULL"
        ),
        "≥1 cuidador com mapeamento Tecnosenior",
    )
    return f


def f4_whatsapp_audio_pipeline() -> Flow:
    f = Flow(4, "WhatsApp áudio → transcript → care_event → multiclassificação")
    db = get_postgres()
    # Pipeline já produziu eventos recentes?
    n_events_24h = db_count(
        "SELECT * FROM aia_health_care_events "
        "WHERE created_at >= NOW() - INTERVAL '24 hours'"
    )
    f.assert_(
        n_events_24h >= 0,  # zero é ok se não houve áudios
        f"Care_events 24h: {n_events_24h}",
    )
    # Multiclassificação populada nos eventos recentes?
    typed_24h = db_count(
        "SELECT * FROM aia_health_care_events "
        "WHERE created_at >= NOW() - INTERVAL '7 days' "
        "AND event_type IS NOT NULL"
    )
    f.assert_(
        typed_24h > 0 or n_events_24h == 0,
        f"event_type populado em eventos recentes ({typed_24h}/7d)",
    )
    # Cascade audit registra runs?
    cascade_runs = db_count(
        "SELECT * FROM aia_health_classification_cascade "
        "WHERE created_at >= NOW() - INTERVAL '7 days'"
    )
    f.assert_(
        cascade_runs >= 0,
        f"Cascade audit operacional ({cascade_runs} runs/7d)",
    )
    # Reports recentes c/ transcript vazio EXCLUINDO áudios curtos
    # (<5s) que são caso edge legítimo: cuidador grava sem falar,
    # Deepgram retorna vazio, pipeline pede regravar — comportamento
    # correto, não vira care_event.
    bad_reports = db_count(
        "SELECT * FROM aia_health_reports "
        "WHERE created_at >= NOW() - INTERVAL '7 days' "
        "AND (transcription IS NULL OR transcription = '') "
        "AND COALESCE(audio_duration_seconds, 0) >= 5"
    )
    f.assert_(
        bad_reports == 0,
        f"Reports c/ transcript vazio em áudio ≥5s (real bug): {bad_reports}",
    )
    return f


def f5_sofia_outbound_infra() -> Flow:
    f = Flow(5, "Sofia outbound (infra)")
    db = get_postgres()
    scenarios = db_count(
        "SELECT * FROM aia_health_call_scenarios "
        "WHERE active = TRUE AND direction = 'outbound'"
    )
    f.assert_(scenarios >= 1, f"≥1 scenario outbound ativo ({scenarios})")
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_call_scenarios "
            "WHERE code = 'cuidador_retorno_relato' AND active = TRUE"
        ),
        "Scenario cuidador_retorno_relato (validado em demo) existe",
    )
    return f


def f6_alerts_escalation() -> Flow:
    f = Flow(6, "Alerta crítico → escalação")
    db = get_postgres()
    f.assert_(
        db_exists(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'aia_health_alerts'"
        ),
        "Tabela alerts existe",
    )
    f.assert_(
        db_exists(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'aia_health_escalation_log'"
        ),
        "Tabela escalation_log existe",
    )
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_tenant_config "
            "WHERE escalation_policy IS NOT NULL"
        ),
        "Política de escalação configurada por tenant",
    )
    # Coluna correta é "level" não "classification"
    crit_alerts_7d = db_count(
        "SELECT * FROM aia_health_alerts "
        "WHERE level = 'critico' "
        "AND created_at >= NOW() - INTERVAL '7 days'"
    )
    f.assert_(
        crit_alerts_7d >= 0,
        f"Alertas critical 7d: {crit_alerts_7d}",
    )
    return f


def f7_medication() -> Flow:
    f = Flow(7, "Medicação: schedule + check-in + adherence")
    db = get_postgres()
    schedules = db_count(
        "SELECT * FROM aia_health_medication_schedules WHERE active = TRUE"
    )
    f.assert_(schedules > 0, f"Há schedules ativos ({schedules})")
    # Coluna correta é "scheduled_at" (não scheduled_for)
    events_7d = db_count(
        "SELECT * FROM aia_health_medication_events "
        "WHERE scheduled_at >= NOW() - INTERVAL '7 days'"
    )
    f.assert_(events_7d > 0 or schedules == 0,
              f"Eventos materializados ({events_7d}/7d)")
    # Tracking de adherence pode ser via 'status' ou 'confirmed_at'
    f.assert_(
        db_exists(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'aia_health_medication_events' "
            "AND column_name IN ('confirmed_at', 'taken_at', 'status')"
        ),
        "Tracking de adherence (confirmed_at/taken_at/status) existe",
    )
    return f


def f8_admin_panel_data() -> Flow:
    f = Flow(8, "Painel médico/enfermagem (dados)")
    db = get_postgres()
    f.assert_(
        db_exists("SELECT 1 FROM aia_health_users WHERE role = 'medico'") or
        db_exists("SELECT 1 FROM aia_health_users WHERE role = 'enfermeiro'"),
        "Há usuários médico/enfermeiro cadastrados",
    )
    f.assert_(
        db_exists(
            "SELECT 1 FROM aia_health_users "
            "WHERE role IN ('medico','enfermeiro') AND active = TRUE"
        ),
        "≥1 médico/enfermeiro ativo",
    )
    return f


def f9_tecnosenior_sync() -> Flow:
    f = Flow(9, "Tecnosenior sync (one-off + streaming)")
    db = get_postgres()
    syncs = db_count(
        "SELECT * FROM aia_health_tecnosenior_sync"
    )
    f.assert_(syncs >= 1, f"≥1 sync registrado ({syncs})")
    closed = db_count(
        "SELECT * FROM aia_health_tecnosenior_sync "
        "WHERE tecnosenior_status = 'CLOSED'"
    )
    f.assert_(closed >= 1, f"≥1 CareNote CLOSED ({closed}) — sync funcionou")
    f.assert_(
        db_exists(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'aia_health_tecnosenior_addendums'"
        ),
        "Tabela addendums existe (streaming)",
    )
    errors = db_count(
        "SELECT * FROM aia_health_tecnosenior_sync "
        "WHERE sync_error IS NOT NULL"
    )
    f.assert_(
        errors == 0,
        f"Zero syncs com erro ({errors})",
    )
    return f


# ────────────────────────── Run ──────────────────────────

FLOWS = [
    f1_login_auth, f2_patients_crud, f3_caregivers,
    f4_whatsapp_audio_pipeline, f5_sofia_outbound_infra,
    f6_alerts_escalation, f7_medication, f8_admin_panel_data,
    f9_tecnosenior_sync,
]


def main():
    started = time.time()
    results = []
    for fn in FLOWS:
        try:
            results.append(fn())
        except Exception as exc:
            f = Flow(0, fn.__name__)
            f.assert_(False, "EXCEPTION", str(exc)[:200])
            results.append(f)

    elapsed = time.time() - started
    passed = sum(1 for r in results if r.passed())
    print(f"# Smoke E2E — {passed}/{len(results)} fluxos OK ({elapsed:.1f}s)")
    for r in results:
        print(r.render())

    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
