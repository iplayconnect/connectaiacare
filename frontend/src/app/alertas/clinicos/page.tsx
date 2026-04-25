"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Pill,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";

import { api, type ClinicalAlertRow } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /alertas/clinicos — alertas do motor de cruzamentos (dose validator,
// interações, contraindicações, etc.). Diferente de /alertas (que é
// triagem de care_events / relatos).
// ═══════════════════════════════════════════════════════════════════

type LevelFilter = "all" | "critical" | "high" | "medium" | "low";
type StatusFilter = "active" | "open" | "acknowledged" | "resolved" | "all";

const LEVEL_META: Record<
  string,
  { label: string; bg: string; text: string; ring: string }
> = {
  critical: {
    label: "Crítico",
    bg: "bg-red-500/15",
    text: "text-red-400",
    ring: "ring-red-500/30",
  },
  high: {
    label: "Alto",
    bg: "bg-orange-500/15",
    text: "text-orange-400",
    ring: "ring-orange-500/30",
  },
  medium: {
    label: "Médio",
    bg: "bg-amber-500/15",
    text: "text-amber-400",
    ring: "ring-amber-500/30",
  },
  low: {
    label: "Baixo",
    bg: "bg-sky-500/15",
    text: "text-sky-400",
    ring: "ring-sky-500/30",
  },
};

export default function AlertasClinicosPage() {
  const [items, setItems] = useState<ClinicalAlertRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<LevelFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("active");
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listClinicalAlerts({
        level: level === "all" ? undefined : level,
        status,
        limit: 200,
      });
      setItems(res.alerts);
    } catch (e: any) {
      setError(e?.message || "Erro ao carregar alertas");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, status]);

  const counts = useMemo(() => {
    const acc = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const a of items) {
      if (a.level in acc) acc[a.level as keyof typeof acc] += 1;
    }
    return acc;
  }, [items]);

  async function handleAck(a: ClinicalAlertRow) {
    setBusy(a.id);
    try {
      await api.acknowledgeClinicalAlert(a.id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function handleResolve(a: ClinicalAlertRow) {
    setBusy(a.id);
    try {
      await api.resolveClinicalAlert(a.id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldAlert className="h-6 w-6 text-accent-cyan" />
            Alertas Clínicos
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Cruzamentos automáticos do motor de validação (doses, interações,
            contraindicações, ajustes renais/hepáticos).
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/[0.04]"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Atualizar
        </button>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {(["critical", "high", "medium", "low"] as const).map((l) => {
          const m = LEVEL_META[l];
          return (
            <button
              key={l}
              onClick={() => setLevel(level === l ? "all" : l)}
              className={`p-4 rounded-xl border text-left transition-all ${
                level === l
                  ? `${m.bg} ${m.ring} ring-1 border-transparent`
                  : "border-white/[0.06] hover:border-white/15"
              }`}
            >
              <div className={`text-xs uppercase tracking-wider ${m.text}`}>
                {m.label}
              </div>
              <div className="text-2xl font-bold mt-1 tabular">
                {counts[l]}
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-xs text-muted-foreground">Status:</span>
        {(
          [
            ["active", "Ativos"],
            ["open", "Abertos"],
            ["acknowledged", "Reconhecidos"],
            ["resolved", "Resolvidos"],
            ["all", "Todos"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setStatus(k)}
            className={`px-3 py-1 text-xs rounded-md border transition ${
              status === k
                ? "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/30"
                : "border-white/10 text-muted-foreground hover:text-foreground hover:bg-white/[0.03]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando…
        </div>
      ) : items.length === 0 ? (
        <div className="p-12 rounded-xl border border-white/[0.06] text-center text-muted-foreground">
          <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-emerald-500/60" />
          Nenhum alerta clínico
          {level !== "all" ? ` ${LEVEL_META[level]?.label.toLowerCase()}` : ""}
          {status !== "all" ? ` (${status})` : ""}.
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((a) => (
            <ClinicalAlertCard
              key={a.id}
              alert={a}
              busy={busy === a.id}
              onAck={() => handleAck(a)}
              onResolve={() => handleResolve(a)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ClinicalAlertCard({
  alert,
  busy,
  onAck,
  onResolve,
}: {
  alert: ClinicalAlertRow;
  busy: boolean;
  onAck: () => void;
  onResolve: () => void;
}) {
  const m = LEVEL_META[alert.level] || LEVEL_META.low;
  const issues = alert.validation?.issues || [];
  const medName = alert.validation?.medication_name as string | undefined;
  const dose = alert.validation?.dose as string | undefined;
  const created = alert.created_at
    ? new Date(alert.created_at).toLocaleString("pt-BR")
    : null;

  return (
    <li className={`p-4 rounded-xl border ${m.ring} ring-1 border-transparent ${m.bg}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className={`h-5 w-5 flex-shrink-0 mt-0.5 ${m.text}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${m.text} ${m.bg}`}
                >
                  {m.label}
                </span>
                {alert.kinds.map((k) => (
                  <span
                    key={k}
                    className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-white/[0.06] text-muted-foreground"
                  >
                    {k}
                  </span>
                ))}
                {alert.status === "acknowledged" && (
                  <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400">
                    Reconhecido
                  </span>
                )}
                {alert.status === "resolved" && (
                  <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
                    Resolvido
                  </span>
                )}
              </div>
              <h3 className="font-semibold mt-1.5">{alert.title}</h3>
              {alert.description && (
                <p className="text-sm text-muted-foreground mt-0.5">
                  {alert.description}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-1 text-right">
              {created && (
                <span className="text-[11px] text-muted-foreground tabular">
                  {created}
                </span>
              )}
            </div>
          </div>

          {(alert.patient_name || medName) && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-xs text-muted-foreground">
              {alert.patient_name && (
                <span>
                  <span className="opacity-60">Paciente:</span>{" "}
                  <span className="text-foreground">
                    {alert.patient_nickname || alert.patient_name}
                  </span>
                  {alert.patient_unit && ` · ${alert.patient_unit}`}
                  {alert.patient_room && ` · Quarto ${alert.patient_room}`}
                </span>
              )}
              {medName && (
                <span className="flex items-center gap-1">
                  <Pill className="h-3 w-3" />
                  <span className="text-foreground">{medName}</span>
                  {dose && <span className="opacity-60">· {dose}</span>}
                </span>
              )}
            </div>
          )}

          {issues.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {issues.map((iss, idx) => (
                <li
                  key={idx}
                  className="text-xs px-3 py-2 rounded-md bg-white/[0.03] border border-white/[0.04]"
                >
                  <div className="flex items-start gap-2">
                    <span className="font-mono text-[10px] uppercase opacity-60 mt-0.5">
                      {iss.code}
                    </span>
                    <span className="flex-1">{iss.message}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {alert.recommended_actions.length > 0 && (
            <div className="mt-3 text-xs">
              <div className="opacity-60 mb-1">Ações recomendadas:</div>
              <ul className="list-disc list-inside space-y-0.5">
                {alert.recommended_actions.map((act, i) => (
                  <li key={i}>{act}</li>
                ))}
              </ul>
            </div>
          )}

          {alert.status !== "resolved" && (
            <div className="mt-4 flex gap-2">
              {alert.status === "open" && (
                <button
                  disabled={busy}
                  onClick={onAck}
                  className="text-xs px-3 py-1.5 rounded-md bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 border border-amber-500/30 disabled:opacity-50"
                >
                  {busy ? "..." : "Reconhecer"}
                </button>
              )}
              <button
                disabled={busy}
                onClick={onResolve}
                className="text-xs px-3 py-1.5 rounded-md bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 border border-emerald-500/30 disabled:opacity-50 flex items-center gap-1"
              >
                {busy ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3 w-3" />
                )}
                Resolver
              </button>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
