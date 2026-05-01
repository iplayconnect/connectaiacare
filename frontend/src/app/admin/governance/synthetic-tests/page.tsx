"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Loader2,
  Play,
  RefreshCw,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/utils";

interface SyntheticRun {
  id: string;
  ran_at: string;
  corpus_name: string;
  corpus_size: number;
  mode: "tier1" | "cascade";
  accuracy: string;
  f1_macro: string;
  threshold_pass: boolean;
  errors_count: number;
  elapsed_seconds: string;
  cascade_stats?: { tier1_only: number; tier2_triggered: number; tier3_triggered: number };
  notes?: string | null;
}

const REFRESH_MS = 30_000;

export default function SyntheticTestsPage() {
  const { user } = useAuth();
  const [runs, setRuns] = useState<SyntheticRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [selectedMode, setSelectedMode] = useState<"tier1" | "cascade">("tier1");
  const [selectedCorpus, setSelectedCorpus] = useState("event_type_seed");
  const [error, setError] = useState<string | null>(null);

  const allowed = hasRole(user, "super_admin", "admin_tenant");

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.request<{ status: string; runs: SyntheticRun[] }>(
        "/api/admin/synthetic-tests/history?limit=30",
      );
      setRuns(res.runs || []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro carregando runs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [allowed, load]);

  const runNow = async () => {
    setRunning(true);
    try {
      await api.request("/api/admin/synthetic-tests/run", {
        method: "POST",
        body: JSON.stringify({
          corpus_name: selectedCorpus,
          mode: selectedMode,
        }),
      });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erro ao rodar");
    } finally {
      setRunning(false);
    }
  };

  const last = runs[0];
  const trend = useMemo(() => {
    if (runs.length < 2) return null;
    const cur = parseFloat(runs[0].f1_macro);
    const prev = parseFloat(runs[1].f1_macro);
    return cur - prev;
  }, [runs]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Sem permissão para acessar testes sintéticos.
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 text-accent-cyan" />
            Testes Sintéticos — Classificação
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Avaliação automatizada do classificador event_type. Rodamos
            corpus rotulado por humano contra o pipeline real (T1 ou cascade)
            e medimos F1 macro, accuracy e erros por classe.
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

      {/* Cards de status */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <StatCard
          label="Último F1 macro"
          value={last ? formatNumber(last.f1_macro) : "—"}
          color={last?.threshold_pass ? "good" : "bad"}
          subtitle={
            trend !== null
              ? `${trend >= 0 ? "+" : ""}${trend.toFixed(3)} vs anterior`
              : "primeiro run"
          }
        />
        <StatCard
          label="Accuracy"
          value={last ? `${(parseFloat(last.accuracy) * 100).toFixed(1)}%` : "—"}
        />
        <StatCard
          label="Total runs"
          value={runs.length.toString()}
        />
        <StatCard
          label="Último corpus"
          value={last ? `${last.corpus_size} itens` : "—"}
          subtitle={last?.corpus_name}
        />
      </div>

      {/* Disparar novo run */}
      <div className="rounded-xl border border-white/10 p-4 bg-white/[0.02]">
        <h2 className="text-sm font-semibold mb-3">Rodar novo teste</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Corpus</label>
            <select
              value={selectedCorpus}
              onChange={(e) => setSelectedCorpus(e.target.value)}
              className="bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
            >
              <option value="event_type_seed">event_type_seed (24)</option>
              <option value="event_type_full">event_type_full (240)</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Modo</label>
            <select
              value={selectedMode}
              onChange={(e) => setSelectedMode(e.target.value as "tier1" | "cascade")}
              className="bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
            >
              <option value="tier1">Tier 1 (extract_entities)</option>
              <option value="cascade">Cascade (T1+T2+T3)</option>
            </select>
          </div>
          <button
            onClick={runNow}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2 rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
          >
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {running ? "Rodando..." : "Rodar agora"}
          </button>
        </div>
      </div>

      {/* Histórico */}
      <div className="rounded-xl border border-white/10 overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <TrendingUp className="h-4 w-4" /> Histórico ({runs.length})
          </h2>
        </div>
        {loading ? (
          <div className="p-8 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">
            Nenhum run ainda. Clique em "Rodar agora" pra começar.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Quando</th>
                <th className="text-left px-3 py-2 font-medium">Corpus</th>
                <th className="text-left px-3 py-2 font-medium">Modo</th>
                <th className="text-right px-3 py-2 font-medium">F1</th>
                <th className="text-right px-3 py-2 font-medium">Acc</th>
                <th className="text-right px-3 py-2 font-medium">Erros</th>
                <th className="text-right px-3 py-2 font-medium">Tempo</th>
                <th className="text-center px-3 py-2 font-medium">Status</th>
                <th className="text-left px-3 py-2 font-medium">Cascade</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-white/[0.04] hover:bg-white/[0.015]">
                  <td className="px-4 py-2 text-xs">{formatDateTime(r.ran_at)}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.corpus_name} <span className="text-muted-foreground">({r.corpus_size})</span>
                  </td>
                  <td className="px-3 py-2 text-xs">{r.mode}</td>
                  <td className="px-3 py-2 text-right font-mono">{formatNumber(r.f1_macro)}</td>
                  <td className="px-3 py-2 text-right font-mono">{formatNumber((parseFloat(r.accuracy) * 100).toFixed(1))}%</td>
                  <td className="px-3 py-2 text-right font-mono">{r.errors_count}</td>
                  <td className="px-3 py-2 text-right text-xs">{r.elapsed_seconds}s</td>
                  <td className="px-3 py-2 text-center">
                    {r.threshold_pass ? (
                      <CheckCircle2 className="h-4 w-4 text-classification-routine inline" />
                    ) : (
                      <XCircle className="h-4 w-4 text-classification-urgent inline" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {r.cascade_stats
                      ? `T1:${r.cascade_stats.tier1_only} T2:${r.cascade_stats.tier2_triggered} T3:${r.cascade_stats.tier3_triggered}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

function StatCard({
  label, value, subtitle, color,
}: {
  label: string;
  value: string;
  subtitle?: string | null;
  color?: "good" | "bad";
}) {
  const valueColor =
    color === "good"
      ? "text-classification-routine"
      : color === "bad"
      ? "text-classification-urgent"
      : "text-foreground";
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</div>
      {subtitle && (
        <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div>
      )}
    </div>
  );
}
