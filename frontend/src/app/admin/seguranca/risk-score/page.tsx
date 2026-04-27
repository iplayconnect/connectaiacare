"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  GitCompareArrows,
  Sparkles,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api, type PatientRiskRow, type PatientBaseline, ApiError } from "@/lib/api";

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
  const [recomputingBaselines, setRecomputingBaselines] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeRow, setActiveRow] = useState<PatientRiskRow | null>(null);
  const [byLevel, setByLevel] = useState<{
    low: number;
    moderate: number;
    high: number;
    critical: number;
  } | null>(null);
  const [showCombined, setShowCombined] = useState(true);

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

  async function recomputeAllBaselines() {
    if (
      !confirm(
        "Recomputar baseline individual de todos os pacientes? " +
          "Lê 60d de histórico por paciente. Demora ~1min.",
      )
    )
      return;
    setRecomputingBaselines(true);
    try {
      const r = await api.riskBaselineRecomputeAll();
      alert(
        `Baselines computados: ${r.processed} pacientes, ${r.with_sufficient_data} com dados suficientes (≥4 semanas).`,
      );
      // Após baseline, recompute scores pra atualizar deviation_score
      await api.riskScoreRecomputeAll();
      await load();
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    } finally {
      setRecomputingBaselines(false);
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

  function effectiveLevel(row: PatientRiskRow): Level {
    if (showCombined && row.has_baseline && row.combined_level) {
      return row.combined_level as Level;
    }
    return row.level as Level;
  }
  function effectiveScore(row: PatientRiskRow): number {
    if (showCombined && row.has_baseline && row.combined_score != null) {
      return row.combined_score;
    }
    return row.score;
  }

  const counts = {
    critical: items.filter((i) => effectiveLevel(i) === "critical").length,
    high: items.filter((i) => effectiveLevel(i) === "high").length,
    moderate: items.filter((i) => effectiveLevel(i) === "moderate").length,
    low: items.filter((i) => effectiveLevel(i) === "low").length,
  };

  // Re-sort se modo combinado mudou — sem re-fetch
  const displayedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const la = LEVEL_ORDER[effectiveLevel(a)];
      const lb = LEVEL_ORDER[effectiveLevel(b)];
      if (la !== lb) return la - lb;
      return effectiveScore(b) - effectiveScore(a);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, showCombined]);

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
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
          {canRecompute && (
            <>
              <button
                onClick={recomputeAllBaselines}
                disabled={recomputingBaselines}
                title="Recomputa o baseline individual (last 60d) de cada paciente. Roda em ~1min."
                className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-violet-500/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
              >
                {recomputingBaselines ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <GitCompareArrows className="h-4 w-4" />
                )}
                Recomputar baselines
              </button>
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
                Recalcular scores
              </button>
            </>
          )}
        </div>
      </header>

      <div className="mb-4 flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Modo:</span>
        <button
          onClick={() => setShowCombined(false)}
          className={`px-2.5 py-1 rounded border ${
            !showCombined
              ? "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan"
              : "border-white/10 text-muted-foreground hover:bg-white/5"
          }`}
        >
          Score absoluto (Fase 1)
        </button>
        <button
          onClick={() => setShowCombined(true)}
          className={`px-2.5 py-1 rounded border flex items-center gap-1 ${
            showCombined
              ? "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan"
              : "border-white/10 text-muted-foreground hover:bg-white/5"
          }`}
        >
          <Sparkles className="h-3 w-3" />
          Score combinado (com baseline individual)
        </button>
      </div>

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
                <th className="text-left px-3 py-2.5 font-medium">Desvio</th>
                <th className="text-left px-3 py-2.5 font-medium">Tend.</th>
                <th className="text-right px-3 py-2.5 font-medium">Queixas 7d</th>
                <th className="text-right px-3 py-2.5 font-medium">Adesão</th>
                <th className="text-right px-3 py-2.5 font-medium">Urg. 7d</th>
                <th className="text-right px-4 py-2.5 font-medium">Calc.</th>
              </tr>
            </thead>
            <tbody>
              {displayedItems.map((row) => {
                const lvl = effectiveLevel(row);
                const sc = effectiveScore(row);
                const isCombined =
                  showCombined && row.has_baseline && row.combined_score != null;
                return (
                  <tr
                    key={row.patient_id}
                    onClick={() => setActiveRow(row)}
                    className="border-t border-white/5 hover:bg-white/[0.03] cursor-pointer"
                  >
                    <td className="px-4 py-3 font-medium">
                      {row.patient_name || row.patient_id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-3">
                      <ScoreBar score={sc} level={lvl} combined={isCombined} />
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${LEVEL_BADGE[lvl]}`}
                      >
                        {LEVEL_LABELS[lvl]}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <DeviationCell row={row} />
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
                );
              })}
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

function ScoreBar({
  score,
  level,
  combined,
}: {
  score: number;
  level: Level;
  combined?: boolean;
}) {
  const colors: Record<Level, string> = {
    critical: "bg-red-500",
    high: "bg-orange-500",
    moderate: "bg-amber-500",
    low: "bg-emerald-500",
  };
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 rounded-full bg-white/10 overflow-hidden relative">
        <div
          className={`h-full ${colors[level]}`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <span
        className={`font-mono text-xs tabular-nums w-7 text-right ${combined ? "text-violet-300" : ""}`}
        title={combined ? "Score combinado (Fase 1 + baseline individual)" : "Score Fase 1 (threshold absoluto)"}
      >
        {score}
        {combined ? "✦" : ""}
      </span>
    </div>
  );
}

function DeviationCell({ row }: { row: PatientRiskRow }) {
  if (!row.has_baseline) {
    return (
      <span className="text-[11px] text-muted-foreground italic">
        sem baseline
      </span>
    );
  }
  const zs = [
    { label: "queixas", z: row.baseline_complaints_z, dir: "up" as const },
    { label: "urg.", z: row.baseline_urgent_z, dir: "up" as const },
    { label: "adesão", z: row.baseline_adherence_z, dir: "down" as const },
  ];
  const flags = zs.filter((s) => {
    if (s.z == null) return false;
    return s.dir === "up" ? s.z >= 1 : s.z <= -1;
  });
  if (flags.length === 0) {
    return (
      <span className="px-2 py-0.5 text-[11px] uppercase rounded bg-emerald-500/10 text-emerald-300/80 border border-emerald-500/20">
        Estável
      </span>
    );
  }
  const isStrong = flags.some((s) => {
    if (s.z == null) return false;
    return Math.abs(s.z) >= 2;
  });
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {flags.map((s) => (
        <span
          key={s.label}
          className={`px-1.5 py-0.5 text-[10px] uppercase font-mono rounded border ${
            Math.abs(s.z!) >= 2
              ? "bg-red-500/15 text-red-300 border-red-500/30"
              : "bg-amber-500/10 text-amber-200 border-amber-500/20"
          }`}
          title={`${s.label}: z=${s.z?.toFixed(1)} (${s.dir === "up" ? "subindo" : "caindo"})`}
        >
          {s.label} {s.dir === "up" ? "↑" : "↓"}
          {Math.abs(s.z!).toFixed(1)}σ
        </span>
      ))}
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
  const [baseline, setBaseline] = useState<PatientBaseline | null>(null);
  const [baselineLoading, setBaselineLoading] = useState(false);
  const [baselineComputing, setBaselineComputing] = useState(false);

  useEffect(() => {
    setBaselineLoading(true);
    api
      .riskBaselineGet(row.patient_id)
      .then((r) => {
        if (r.has_baseline && r.baseline) setBaseline(r.baseline);
        else setBaseline(null);
      })
      .catch(() => {})
      .finally(() => setBaselineLoading(false));
  }, [row.patient_id]);

  async function recomputeBaseline() {
    setBaselineComputing(true);
    try {
      await api.riskBaselineCompute(row.patient_id, 60);
      const r = await api.riskBaselineGet(row.patient_id);
      if (r.has_baseline && r.baseline) setBaseline(r.baseline);
      // Reroda score pra atualizar deviation
      await api.riskScoreCompute(row.patient_id);
      alert(
        "Baseline computado. Feche e abra o drawer pra ver os desvios atualizados.",
      );
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    } finally {
      setBaselineComputing(false);
    }
  }

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
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${LEVEL_BADGE[row.level as Level]}`}
              >
                Fase 1: {LEVEL_LABELS[row.level as Level]} · {row.score}
              </span>
              {row.has_baseline && row.combined_score != null && (
                <span
                  className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${LEVEL_BADGE[row.combined_level as Level]}`}
                >
                  Combinado: {LEVEL_LABELS[row.combined_level as Level]} ·{" "}
                  {row.combined_score}
                </span>
              )}
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
              Sinais determinísticos (últimos 7d)
            </div>
            <div className="grid grid-cols-3 gap-3">
              <SignalBox
                icon={<HeartPulse className="h-4 w-4" />}
                label="Queixas"
                value={String(row.complaints_7d)}
                z={row.baseline_complaints_z}
                zDir="up"
              />
              <SignalBox
                icon={<Pill className="h-4 w-4" />}
                label="Adesão"
                value={
                  row.adherence_pct === null
                    ? "—"
                    : `${Math.round(row.adherence_pct)}%`
                }
                z={row.baseline_adherence_z}
                zDir="down"
              />
              <SignalBox
                icon={<AlertTriangle className="h-4 w-4" />}
                label="Urgentes"
                value={String(row.urgent_events_7d)}
                z={row.baseline_urgent_z}
                zDir="up"
              />
            </div>
          </div>

          {/* Baseline panel — Fase 2 */}
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-2">
              <GitCompareArrows className="h-3.5 w-3.5" />
              Baseline individual (Fase 2)
            </div>
            {baselineLoading ? (
              <div className="text-xs text-muted-foreground p-3">
                Carregando…
              </div>
            ) : !baseline ? (
              <div className="p-3 rounded-lg border border-dashed border-white/10 text-sm text-muted-foreground">
                Sem baseline computado.{" "}
                {row.has_baseline
                  ? "Estado inconsistente — reprocessa abaixo."
                  : "Clique em \"Computar baseline\" pra gerar a partir do histórico."}
              </div>
            ) : !baseline.has_sufficient_data ? (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm">
                <div className="text-amber-200 font-medium">
                  Dados insuficientes
                </div>
                <div className="text-xs text-amber-200/70 mt-1">
                  {baseline.insufficient_reason ||
                    "Precisa pelo menos 4 semanas de dados pra computar baseline."}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                <BaselineBox
                  label="Queixas/sem"
                  median={baseline.complaints_median}
                  mad={baseline.complaints_mad}
                  history={baseline.complaints_history}
                />
                <BaselineBox
                  label="Adesão/sem"
                  median={baseline.adherence_median}
                  mad={baseline.adherence_mad}
                  history={baseline.adherence_history}
                  suffix="%"
                />
                <BaselineBox
                  label="Urgentes/sem"
                  median={baseline.urgent_median}
                  mad={baseline.urgent_mad}
                  history={baseline.urgent_history}
                />
              </div>
            )}
            {baseline && baseline.has_sufficient_data && (
              <div className="text-[11px] text-muted-foreground mt-2">
                {baseline.weeks_observed} semanas observadas · janela{" "}
                {baseline.period_days}d · atualizado{" "}
                {formatRelative(baseline.last_computed_at)}
              </div>
            )}
          </div>

          {breakdown && Object.keys(breakdown).length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground uppercase tracking-wide hover:text-foreground">
                Breakdown JSON completo
              </summary>
              <pre className="mt-2 font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap max-h-72 overflow-y-auto">
                {JSON.stringify(breakdown, null, 2)}
              </pre>
            </details>
          )}

          <div className="text-xs text-muted-foreground">
            Último cálculo: {new Date(row.computed_at).toLocaleString("pt-BR")}
            {row.trend && <> · Tendência: {row.trend}</>}
          </div>
        </div>

        <div className="sticky bottom-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-4 flex justify-end gap-2 flex-wrap">
          <button
            onClick={recomputeBaseline}
            disabled={baselineComputing}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md border border-violet-500/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20 disabled:opacity-50"
          >
            {baselineComputing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GitCompareArrows className="h-4 w-4" />
            )}
            Computar baseline
          </button>
          <button
            onClick={onRecompute}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90"
          >
            <PlayCircle className="h-4 w-4" />
            Recalcular score
          </button>
        </div>
      </div>
    </div>
  );
}

function BaselineBox({
  label,
  median,
  mad,
  history,
  suffix = "",
}: {
  label: string;
  median: number | null;
  mad: number | null;
  history: number[];
  suffix?: string;
}) {
  const max = Math.max(1, ...(history || []).map((v) => v || 0));
  return (
    <div className="p-3 rounded-lg bg-violet-500/[0.04] border border-violet-500/15">
      <div className="text-[11px] uppercase text-muted-foreground mb-1">
        {label}
      </div>
      <div className="text-base font-semibold tabular-nums">
        {median !== null ? `${Math.round(Number(median) * 10) / 10}${suffix}` : "—"}
        <span className="text-xs text-muted-foreground ml-1">
          ±{mad !== null ? `${Math.round(Number(mad) * 10) / 10}${suffix}` : "—"}
        </span>
      </div>
      <div className="flex items-end gap-px h-6 mt-1">
        {(history || []).slice(-10).map((v, i) => (
          <div
            key={i}
            className="flex-1 bg-violet-400/40 rounded-sm min-w-[2px]"
            style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
            title={`${v}${suffix}`}
          />
        ))}
      </div>
    </div>
  );
}

function SignalBox({
  icon,
  label,
  value,
  z,
  zDir = "up",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  z?: number | null;
  zDir?: "up" | "down";
}) {
  const isAbnormal =
    z != null && (zDir === "up" ? z >= 1 : z <= -1);
  return (
    <div
      className={`p-3 rounded-lg border ${
        isAbnormal && Math.abs(z!) >= 2
          ? "bg-red-500/10 border-red-500/30"
          : isAbnormal
            ? "bg-amber-500/10 border-amber-500/25"
            : "bg-white/[0.03] border-white/5"
      }`}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
        {icon}
        {label}
      </div>
      <div className="text-xl font-semibold tabular-nums">{value}</div>
      {z != null && (
        <div
          className={`text-[11px] mt-0.5 ${
            isAbnormal && Math.abs(z) >= 2
              ? "text-red-300"
              : isAbnormal
                ? "text-amber-200"
                : "text-muted-foreground"
          }`}
          title={`Z-score robusto vs baseline individual: ${z.toFixed(2)}`}
        >
          {z >= 0 ? "↑" : "↓"} {Math.abs(z).toFixed(1)}σ vs baseline
        </div>
      )}
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
