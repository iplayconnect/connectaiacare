"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PhoneOutgoing,
  Loader2,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  X,
  Search,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  api,
  type ProactiveDecisionRow,
  type ProactiveDecision,
  ApiError,
} from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/proactive-caller — Log de decisões do worker que liga
// dinamicamente baseado em risk + adesão + eventos abertos.
// Permissão: super_admin, admin_tenant, medico, enfermeiro.
// ═══════════════════════════════════════════════════════════════════

const REFRESH_MS = 60_000;

const DECISION_LABELS: Record<ProactiveDecision, string> = {
  will_call: "Ligou",
  skip_disabled: "Desabilitado",
  skip_dnd: "DND",
  skip_outside_window: "Fora da janela",
  skip_too_soon: "Cedo demais",
  skip_low_score: "Score baixo",
  skip_no_phone: "Sem telefone",
  skip_no_scenario: "Sem cenário",
  skip_circuit_open: "Circuit aberto",
  failed_dispatch: "Falhou",
};

const DECISION_BADGE: Record<ProactiveDecision, string> = {
  will_call: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  failed_dispatch: "bg-red-500/20 text-red-300 border-red-500/40",
  skip_circuit_open: "bg-red-500/15 text-red-300 border-red-500/30",
  skip_too_soon: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  skip_outside_window: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  skip_dnd: "bg-violet-500/15 text-violet-200 border-violet-500/30",
  skip_disabled: "bg-white/5 text-muted-foreground border-white/10",
  skip_low_score: "bg-white/5 text-muted-foreground border-white/10",
  skip_no_phone: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  skip_no_scenario: "bg-orange-500/15 text-orange-300 border-orange-500/30",
};

export default function ProactiveCallerPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<ProactiveDecisionRow[]>([]);
  const [stats, setStats] = useState<{
    total: number;
    will_call: number;
    failed: number;
    skipped: number;
    avg_score_called: number | null;
    avg_score_skipped: number | null;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterDecision, setFilterDecision] = useState<
    ProactiveDecision | "all"
  >("all");
  const [search, setSearch] = useState("");
  const [activeRow, setActiveRow] = useState<ProactiveDecisionRow | null>(null);

  const allowed = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [decRes, statsRes] = await Promise.all([
        api.proactiveCallerListDecisions({
          decision: filterDecision === "all" ? undefined : filterDecision,
          limit: 200,
        }),
        api.proactiveCallerStats().catch(() => null),
      ]);
      setItems(decRes.items);
      if (statsRes) setStats(statsRes.stats);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro carregando");
    } finally {
      setLoading(false);
    }
  }, [filterDecision]);

  useEffect(() => {
    if (!allowed) return;
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [allowed, load]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const s = search.toLowerCase();
    return items.filter((i) =>
      [i.patient_name, i.patient_nickname, i.error]
        .filter(Boolean)
        .some((v) => (v as string).toLowerCase().includes(s)),
    );
  }, [items, search]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm text-muted-foreground">
          Sem permissão pra ver o log do Proactive Caller.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <PhoneOutgoing className="h-6 w-6 text-accent-cyan" />
            Proactive Caller
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Sofia decide DINAMICAMENTE quando ligar baseado em risk score,
            adesão, eventos abertos e janela horária. Toda decisão (ligou ou
            pulou) fica registrada aqui — auditável e calibrável.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
        >
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </header>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <StatCard label="Total 24h" value={stats.total} />
          <StatCard
            label="Ligações disparadas"
            value={stats.will_call}
            highlight={stats.will_call > 0}
          />
          <StatCard
            label="Falharam"
            value={stats.failed}
            danger={stats.failed > 0}
          />
          <StatCard label="Skipped" value={stats.skipped} />
          <StatCard
            label="Avg score (ligou)"
            value={stats.avg_score_called ?? "—"}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          value={filterDecision}
          onChange={(e) =>
            setFilterDecision(e.target.value as ProactiveDecision | "all")
          }
          className="px-3 py-1.5 text-sm rounded-md bg-black/30 border border-white/10"
        >
          <option value="all">Todas as decisões</option>
          <option value="will_call">Apenas: ligou</option>
          <option value="failed_dispatch">Apenas: falhou</option>
          <option value="skip_too_soon">Apenas: cedo demais</option>
          <option value="skip_outside_window">Apenas: fora janela</option>
          <option value="skip_low_score">Apenas: score baixo</option>
          <option value="skip_dnd">Apenas: DND</option>
          <option value="skip_circuit_open">Apenas: circuit aberto</option>
        </select>
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Filtrar por paciente ou erro…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm rounded-md bg-black/30 border border-white/10"
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando…
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center p-16 text-muted-foreground border border-dashed border-white/10 rounded-lg">
          <p className="text-sm">Nenhuma decisão registrada para o filtro.</p>
          <p className="text-xs mt-1">
            O worker registra decisão de skip apenas quando score ≥ 25 (evita
            inflar a tabela).
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-xs uppercase text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Quando</th>
                <th className="text-left px-3 py-2.5 font-medium">Paciente</th>
                <th className="text-left px-3 py-2.5 font-medium">Decisão</th>
                <th className="text-right px-3 py-2.5 font-medium">Score</th>
                <th className="text-left px-3 py-2.5 font-medium">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => setActiveRow(row)}
                  className="border-t border-white/5 hover:bg-white/[0.03] cursor-pointer"
                >
                  <td className="px-4 py-3 text-xs text-muted-foreground tabular-nums">
                    {formatRelative(row.evaluated_at)}
                  </td>
                  <td className="px-3 py-3">
                    {row.patient_name ||
                      row.patient_nickname ||
                      row.patient_id.slice(0, 8)}
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${DECISION_BADGE[row.decision]}`}
                    >
                      {DECISION_LABELS[row.decision]}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {row.trigger_score}
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground truncate max-w-[400px]">
                    {row.error
                      ? `⚠ ${row.error}`
                      : row.call_id
                        ? `call_id: ${row.call_id.slice(0, 12)}…`
                        : summarizeBreakdown(row.breakdown)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeRow && (
        <DecisionDrawer
          row={activeRow}
          onClose={() => setActiveRow(null)}
        />
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  highlight,
  danger,
}: {
  label: string;
  value: number | string;
  highlight?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      className={`p-3 rounded-lg border ${
        danger
          ? "border-red-500/40 bg-red-500/5"
          : highlight
            ? "border-emerald-500/40 bg-emerald-500/5"
            : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div
        className={`text-2xl font-bold ${
          danger
            ? "text-red-300"
            : highlight
              ? "text-emerald-300"
              : "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function DecisionDrawer({
  row,
  onClose,
}: {
  row: ProactiveDecisionRow;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-2xl max-h-[90vh] overflow-y-auto rounded-t-xl sm:rounded-xl bg-slate-900 border border-white/10 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-white/10 p-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${DECISION_BADGE[row.decision]}`}
              >
                {DECISION_LABELS[row.decision]}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                score {row.trigger_score}
              </span>
            </div>
            <h2 className="text-lg font-semibold">
              {row.patient_name || row.patient_nickname || row.patient_id.slice(0, 8)}
            </h2>
            <div className="text-xs text-muted-foreground mt-1">
              {new Date(row.evaluated_at).toLocaleString("pt-BR")}
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {row.call_id && (
            <Field label="Call ID">
              <span className="font-mono text-xs">{row.call_id}</span>
            </Field>
          )}
          {row.error && (
            <Field label="Erro">
              <p className="text-sm text-red-300 whitespace-pre-wrap">
                {row.error}
              </p>
            </Field>
          )}
          {row.notes && (
            <Field label="Notas">
              <p className="text-sm whitespace-pre-wrap">{row.notes}</p>
            </Field>
          )}
          {row.breakdown && Object.keys(row.breakdown).length > 0 && (
            <Field label="Breakdown da decisão">
              <pre className="text-xs font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
                {JSON.stringify(row.breakdown, null, 2)}
              </pre>
            </Field>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

function summarizeBreakdown(b: Record<string, unknown>): string {
  if (!b || typeof b !== "object") return "";
  const signals = (b as { signals?: Record<string, unknown> }).signals;
  if (signals && typeof signals === "object") {
    const parts: string[] = [];
    const lvl = signals.risk_level;
    if (lvl) parts.push(`risk: ${lvl}`);
    const md = signals.missed_doses_24h;
    if (typeof md === "number" && md > 0) parts.push(`${md} dose(s) perdida(s)`);
    const oe = signals.open_urgent_events;
    if (typeof oe === "number" && oe > 0) parts.push(`${oe} evento(s) urgente(s)`);
    if (parts.length) return parts.join(" · ");
  }
  return "";
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h${min % 60 ? `${min % 60}min` : ""}`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}
