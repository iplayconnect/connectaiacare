"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Loader2,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  Minus,
  AlertTriangle,
  Pill,
  HeartPulse,
  X,
  PlayCircle,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api, type PatientRiskRow, ApiError } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/seguranca/risk-score — Dashboard de risco por paciente.
// Score 0-100 baseado em 3 sinais determinísticos (queixas 7d,
// adesão %, eventos urgent/critical 7d). Sem ML/LLM.
// Permissão: super_admin, admin_tenant, medico, enfermeiro.
// ═══════════════════════════════════════════════════════════════════

const LEVEL_ORDER = { critical: 0, high: 1, moderate: 2, low: 3 } as const;
type Level = keyof typeof LEVEL_ORDER;

const LEVEL_BADGE: Record<Level, string> = {
  critical: "bg-red-500/20 text-red-300 border-red-500/40",
  high: "bg-orange-500/20 text-orange-300 border-orange-500/40",
  moderate: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  low: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

const LEVEL_LABELS: Record<Level, string> = {
  critical: "Crítico",
  high: "Alto",
  moderate: "Moderado",
  low: "Baixo",
};

export default function RiskScorePage() {
  const { user } = useAuth();
  const [items, setItems] = useState<PatientRiskRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeRow, setActiveRow] = useState<PatientRiskRow | null>(null);
  const [byLevel, setByLevel] = useState<{
    low: number;
    moderate: number;
    high: number;
    critical: number;
  } | null>(null);

  const allowed = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
  );
  const canRecompute = hasRole(user, "super_admin");

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await api.riskScoreHigh(100);
      const sorted = [...r.items].sort((a, b) => {
        const lo =
          LEVEL_ORDER[a.level as Level] - LEVEL_ORDER[b.level as Level];
        if (lo !== 0) return lo;
        return b.score - a.score;
      });
      setItems(sorted);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Erro carregando";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
  }, [allowed, load]);

  async function recomputeAll() {
    if (!confirm("Recalcular score de TODOS os pacientes ativos? Demora ~30s.")) return;
    setRecomputing(true);
    try {
      const r = await api.riskScoreRecomputeAll();
      setByLevel(r.by_level);
      await load();
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    } finally {
      setRecomputing(false);
    }
  }

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm text-muted-foreground">
          Sem permissão para visualizar Risk Score.
        </p>
      </div>
    );
  }

  const counts = {
    critical: items.filter((i) => i.level === "critical").length,
    high: items.filter((i) => i.level === "high").length,
    moderate: items.filter((i) => i.level === "moderate").length,
    low: items.filter((i) => i.level === "low").length,
  };

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 text-accent-cyan" />
            Risk Score Pacientes
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Score 0-100 calculado a partir de 3 sinais determinísticos: queixas
            (7d), adesão à medicação, eventos urgent/critical (7d). Sem IA — só
            regra. Suporte clínico, não decisão.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
          {canRecompute && (
            <button
              onClick={recomputeAll}
              disabled={recomputing}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90 disabled:opacity-50"
            >
              {recomputing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PlayCircle className="h-4 w-4" />
              )}
              Recalcular todos
            </button>
          )}
        </div>
      </header>

      {byLevel && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-200">
          Recálculo concluído: {byLevel.critical} crítico, {byLevel.high} alto,{" "}
          {byLevel.moderate} moderado, {byLevel.low} baixo.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <LevelCard level="critical" count={counts.critical} />
        <LevelCard level="high" count={counts.high} />
        <LevelCard level="moderate" count={counts.moderate} />
        <LevelCard level="low" count={counts.low} />
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
      ) : items.length === 0 ? (
        <div className="text-center p-16 text-muted-foreground border border-dashed border-white/10 rounded-lg">
          <p className="text-sm">Nenhum score calculado ainda.</p>
          {canRecompute && (
            <p className="text-xs mt-1">
              Use &quot;Recalcular todos&quot; para gerar a primeira leva.
            </p>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-xs uppercase text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Paciente</th>
                <th className="text-left px-3 py-2.5 font-medium">Score</th>
                <th className="text-left px-3 py-2.5 font-medium">Nível</th>
                <th className="text-left px-3 py-2.5 font-medium">Tend.</th>
                <th className="text-right px-3 py-2.5 font-medium">Queixas 7d</th>
                <th className="text-right px-3 py-2.5 font-medium">Adesão</th>
                <th className="text-right px-3 py-2.5 font-medium">Urg. 7d</th>
                <th className="text-right px-4 py-2.5 font-medium">Calc.</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.patient_id}
                  onClick={() => setActiveRow(row)}
                  className="border-t border-white/5 hover:bg-white/[0.03] cursor-pointer"
                >
                  <td className="px-4 py-3 font-medium">
                    {row.patient_name || row.patient_id.slice(0, 8)}
                  </td>
                  <td className="px-3 py-3">
                    <ScoreBar score={row.score} level={row.level as Level} />
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${LEVEL_BADGE[row.level as Level]}`}
                    >
                      {LEVEL_LABELS[row.level as Level]}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <TrendIcon trend={row.trend} />
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {row.complaints_7d}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {row.adherence_pct === null
                      ? "—"
                      : `${Math.round(row.adherence_pct)}%`}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {row.urgent_events_7d}
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-muted-foreground">
                    {formatRelative(row.computed_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeRow && (
        <BreakdownDrawer
          row={activeRow}
          onClose={() => setActiveRow(null)}
          onRecompute={async () => {
            try {
              const r = await api.riskScoreCompute(activeRow.patient_id);
              alert(
                `Recalculado: score ${r.score} (${r.level}). Atualize a lista.`,
              );
              setActiveRow(null);
              await load();
            } catch (e) {
              alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
            }
          }}
        />
      )}
    </div>
  );
}

function LevelCard({ level, count }: { level: Level; count: number }) {
  return (
    <div
      className={`p-3 rounded-lg border ${
        count > 0 && (level === "critical" || level === "high")
          ? `${LEVEL_BADGE[level]}`
          : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
        {LEVEL_LABELS[level]}
      </div>
      <div className="text-2xl font-bold">{count}</div>
    </div>
  );
}

function ScoreBar({ score, level }: { score: number; level: Level }) {
  const colors: Record<Level, string> = {
    critical: "bg-red-500",
    high: "bg-orange-500",
    moderate: "bg-amber-500",
    low: "bg-emerald-500",
  };
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 rounded-full bg-white/10 overflow-hidden">
        <div
          className={`h-full ${colors[level]}`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums w-7 text-right">
        {score}
      </span>
    </div>
  );
}

function TrendIcon({ trend }: { trend: string | null }) {
  if (trend === "worsening")
    return <TrendingUp className="h-4 w-4 text-red-400" />;
  if (trend === "improving")
    return <TrendingDown className="h-4 w-4 text-emerald-400" />;
  return <Minus className="h-4 w-4 text-muted-foreground" />;
}

function BreakdownDrawer({
  row,
  onClose,
  onRecompute,
}: {
  row: PatientRiskRow;
  onClose: () => void;
  onRecompute: () => void;
}) {
  const breakdown = row.breakdown as Record<string, unknown>;

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
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${LEVEL_BADGE[row.level as Level]}`}
              >
                {LEVEL_LABELS[row.level as Level]} · score {row.score}
              </span>
            </div>
            <h2 className="text-lg font-semibold">
              {row.patient_name || row.patient_id.slice(0, 8)}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
              Sinais determinísticos
            </div>
            <div className="grid grid-cols-3 gap-3">
              <SignalBox
                icon={<HeartPulse className="h-4 w-4" />}
                label="Queixas 7d"
                value={String(row.complaints_7d)}
              />
              <SignalBox
                icon={<Pill className="h-4 w-4" />}
                label="Adesão"
                value={
                  row.adherence_pct === null
                    ? "—"
                    : `${Math.round(row.adherence_pct)}%`
                }
              />
              <SignalBox
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Urgentes 7d"
                value={String(row.urgent_events_7d)}
              />
            </div>
          </div>

          {breakdown && Object.keys(breakdown).length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
                Breakdown da regra
              </div>
              <pre className="text-xs font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(breakdown, null, 2)}
              </pre>
            </div>
          )}

          <div className="text-xs text-muted-foreground">
            Último cálculo: {new Date(row.computed_at).toLocaleString("pt-BR")}
            {row.trend && <> · Tendência: {row.trend}</>}
          </div>
        </div>

        <div className="sticky bottom-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-4 flex justify-end">
          <button
            onClick={onRecompute}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90"
          >
            <PlayCircle className="h-4 w-4" />
            Recalcular este paciente
          </button>
        </div>
      </div>
    </div>
  );
}

function SignalBox({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="p-3 rounded-lg bg-white/[0.03] border border-white/5">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
        {icon}
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}
