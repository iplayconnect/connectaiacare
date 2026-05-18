"use client";

/**
 * Health Dashboard do plantão técnico — métricas agregadas que
 * respondem 3 perguntas críticas:
 *
 *   1. "Algum contato está morto?" → contacts_stale_30d + sem atividade
 *   2. "Conseguimos responder no SLA?" → SLA 7d (claim < 5min)
 *   3. "A carga está bem distribuída?" → ranking por contato
 *
 * Consome /api/admin/tenants/<tid>/escalation-contacts/health.
 *
 * Aparece como tab "Saúde do Plantão" na página de contatos.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  Phone,
  RefreshCw,
  TrendingUp,
  Users,
} from "lucide-react";

import {
  ESCALATION_ROLE_LABEL,
  formatPhoneBR,
  relativeTimeBR,
  tenantEscalationApi,
  type EscalationHealthResponse,
} from "@/lib/api-tenant-escalation";

export function EscalationHealthDashboard({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<EscalationHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setError(null);
    try {
      const res = await tenantEscalationApi.health(tenantId);
      setData(res);
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : "Erro carregando");
    } finally {
      if (silent) setRefreshing(false);
      else setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando…
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention">
        {error || "Sem dados."}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={() => load(true)}
          disabled={refreshing}
          className="text-[11px] px-2 py-1.5 rounded border border-white/[0.08] hover:bg-white/[0.04] disabled:opacity-40 flex items-center gap-1"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} /> Atualizar
        </button>
      </div>

      {/* SLA Hero — métrica principal */}
      <SLACard sla={data.sla_7d} />

      {/* Stats agregadas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Contatos ativos"
          value={data.summary.active_contacts}
          icon={Users}
          accent="text-accent-cyan"
        />
        <Stat
          label="Recebem P1"
          value={data.summary.p1_subscribers}
          icon={Phone}
          accent="text-classification-critical"
        />
        <Stat
          label="P1s enviados (total)"
          value={data.summary.total_p1_pushed}
          icon={TrendingUp}
          accent="text-foreground"
        />
        <Stat
          label="Sem atividade > 30d"
          value={data.summary.contacts_never_received + data.summary.contacts_stale_30d}
          icon={AlertTriangle}
          accent={
            data.summary.contacts_never_received + data.summary.contacts_stale_30d > 0
              ? "text-classification-attention"
              : "text-classification-routine"
          }
        />
      </div>

      {/* Volume diário 7d */}
      <VolumeChart data={data.p1_volume_7d} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Ranking por contato */}
        <RankingByContact contacts={data.by_contact} />
        {/* Stale alerta */}
        <StaleAlert contacts={data.stale_contacts} />
      </div>
    </div>
  );
}

// ─── Componentes internos ──────────────────────────────────────────

function Stat({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Icon className={`h-3 w-3 ${accent}`} />
        {label}
      </div>
      <div className={`text-2xl font-bold tabular mt-1 ${accent}`}>{value}</div>
    </div>
  );
}

function SLACard({ sla }: { sla: EscalationHealthResponse["sla_7d"] }) {
  const slaColor =
    sla.sla_pct === null
      ? "border-white/[0.06] bg-white/[0.02] text-muted-foreground"
      : sla.sla_pct >= 95
      ? "border-classification-routine/40 bg-classification-routine/10 text-classification-routine"
      : sla.sla_pct >= 75
      ? "border-classification-attention/40 bg-classification-attention/10 text-classification-attention"
      : "border-classification-critical/40 bg-classification-critical/10 text-classification-critical";

  return (
    <div className={`rounded-xl border p-5 ${slaColor}`}>
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] opacity-80">
            SLA P1 últimos 7 dias
          </div>
          <div className="text-3xl font-bold tabular mt-1">
            {sla.sla_pct === null ? "—" : `${sla.sla_pct}%`}
            {sla.sla_pct !== null && (
              <span className="text-sm font-normal opacity-70 ml-2">
                reivindicados em &lt; 5min
              </span>
            )}
          </div>
          <div className="text-[11px] opacity-80 mt-1">
            {sla.total_p1} P1{sla.total_p1 !== 1 ? "s" : ""} criados ·{" "}
            {sla.claimed_under_sla} dentro do SLA
            {sla.avg_claim_seconds !== null && (
              <>
                {" "}
                · tempo médio de claim: <b>{formatDuration(sla.avg_claim_seconds)}</b>
              </>
            )}
          </div>
        </div>
        {sla.sla_pct !== null && (
          sla.sla_pct >= 95 ? (
            <CheckCircle2 className="h-10 w-10 opacity-80" />
          ) : (
            <AlertTriangle className="h-10 w-10 opacity-80" />
          )
        )}
      </div>
    </div>
  );
}

function VolumeChart({ data }: { data: EscalationHealthResponse["p1_volume_7d"] }) {
  // Preenche dias faltantes nos últimos 7 (alguns dias podem não ter P1)
  const today = new Date();
  const days: { day: string; n: number; label: string }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    const match = data.find((x) => x.day === iso);
    days.push({
      day: iso,
      n: match?.n || 0,
      label: d.toLocaleDateString("pt-BR", { weekday: "short", day: "numeric" }),
    });
  }

  const maxN = Math.max(...days.map((d) => d.n), 1);
  const total = days.reduce((acc, d) => acc + d.n, 0);

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          Volume P1 últimos 7 dias
        </div>
        <div className="text-xs text-muted-foreground">
          Total: <span className="font-semibold text-foreground tabular">{total}</span>
        </div>
      </div>
      <div className="grid grid-cols-7 gap-1.5 items-end h-24">
        {days.map((d) => {
          const pct = (d.n / maxN) * 100;
          return (
            <div key={d.day} className="flex flex-col items-center justify-end gap-1">
              <div
                className={`w-full rounded-t transition ${
                  d.n > 0
                    ? "bg-accent-cyan/40 border-t-2 border-accent-cyan"
                    : "bg-white/[0.03]"
                }`}
                style={{ height: `${Math.max(pct, 2)}%` }}
                title={`${d.label}: ${d.n} P1${d.n !== 1 ? "s" : ""}`}
              />
              <div className="text-[9px] text-muted-foreground tabular">
                {d.n}
              </div>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-7 gap-1.5 mt-1">
        {days.map((d) => (
          <div
            key={d.day}
            className="text-[9px] text-muted-foreground/70 text-center uppercase"
          >
            {d.label.split(",")[0]}
          </div>
        ))}
      </div>
    </div>
  );
}

function RankingByContact({
  contacts,
}: {
  contacts: EscalationHealthResponse["by_contact"];
}) {
  if (contacts.length === 0) {
    return (
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
          <Users className="h-3 w-3" /> Carga por contato (7d)
        </div>
        <div className="text-xs text-muted-foreground italic">Nenhum contato ativo.</div>
      </div>
    );
  }
  const max = Math.max(...contacts.map((c) => c.total_p1_received), 1);
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1.5">
        <Users className="h-3 w-3" /> Ranking de carga (total acumulado)
      </div>
      <div className="space-y-2">
        {contacts.slice(0, 10).map((c) => {
          const pct = (c.total_p1_received / max) * 100;
          return (
            <div key={c.id} className="flex items-center gap-2 text-xs">
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{c.contact_name}</span>
                  <span className="font-mono tabular text-muted-foreground flex-shrink-0">
                    {c.total_p1_received}
                  </span>
                </div>
                <div className="h-1 rounded-full bg-white/[0.04] mt-1 overflow-hidden">
                  <div
                    className="h-full bg-accent-cyan/60 rounded-full transition"
                    style={{ width: `${Math.max(pct, 4)}%` }}
                  />
                </div>
                <div className="text-[10px] text-muted-foreground/70 mt-0.5">
                  {ESCALATION_ROLE_LABEL[c.role] || c.role}
                  {c.last_p1_received_at && (
                    <> · último {relativeTimeBR(c.last_p1_received_at)}</>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StaleAlert({
  contacts,
}: {
  contacts: EscalationHealthResponse["stale_contacts"];
}) {
  if (contacts.length === 0) {
    return (
      <div className="rounded-xl border border-classification-routine/20 bg-classification-routine/5 p-4">
        <div className="text-[10px] uppercase tracking-wider text-classification-routine mb-3 flex items-center gap-1.5">
          <CheckCircle2 className="h-3 w-3" /> Saúde dos contatos
        </div>
        <div className="text-xs text-classification-routine">
          ✓ Todos os contatos ativos receberam push nos últimos 30 dias.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-classification-attention/30 bg-classification-attention/5 p-4">
      <div className="text-[10px] uppercase tracking-wider text-classification-attention mb-3 flex items-center gap-1.5">
        <AlertTriangle className="h-3 w-3" /> Contatos sem atividade ({contacts.length})
      </div>
      <p className="text-[11px] text-muted-foreground mb-3">
        Esses plantonistas ativos não recebem P1 há mais de 30 dias.
        Pode ser número errado, WhatsApp bloqueado ou plantão vazio. Verifique.
      </p>
      <ul className="space-y-1">
        {contacts.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 text-xs">
            <div className="flex-1 min-w-0">
              <span className="font-medium truncate">{c.contact_name}</span>
              <span className="text-muted-foreground ml-1.5">
                · {ESCALATION_ROLE_LABEL[c.role] || c.role}
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground flex-shrink-0">
              {c.last_p1_received_at
                ? `há ${relativeTimeBR(c.last_p1_received_at)}`
                : "nunca"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Helpers ───────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const min = Math.round(seconds / 60);
  if (min < 60) return `${min}min`;
  const hr = Math.round(min / 60);
  return `${hr}h`;
}
