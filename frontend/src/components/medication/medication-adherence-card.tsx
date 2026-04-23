"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { api, type MedicationAdherence } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// MedicationAdherenceCard — Card de adesão (30d) pro prontuário.
// Mostra: % geral, breakdown por medicação, alertas de missed consecutivos.
// ═══════════════════════════════════════════════════════════════

export function MedicationAdherenceCard({
  patientId,
  days = 30,
}: {
  patientId: string;
  days?: number;
}) {
  const [data, setData] = useState<MedicationAdherence | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.medicationAdherence(patientId, days);
        setData(res);
      } finally {
        setLoading(false);
      }
    })();
  }, [patientId, days]);

  if (loading) {
    return (
      <div className="glass-card rounded-2xl p-5 border border-white/[0.06]">
        <div className="flex items-center gap-2 text-sm text-foreground/65">
          <Loader2 className="h-4 w-4 animate-spin" />
          Calculando adesão…
        </div>
      </div>
    );
  }

  if (!data || data.summary.total === 0) {
    return (
      <div className="glass-card rounded-2xl p-5 border border-white/[0.06]">
        <div className="flex items-center gap-2 mb-2">
          <Target className="h-4 w-4 text-accent-cyan" />
          <h3 className="text-[14px] font-semibold">Adesão à medicação</h3>
        </div>
        <p className="text-[12px] text-foreground/65 leading-relaxed">
          Ainda não há dados suficientes. Após algumas doses confirmadas, a
          adesão aparece aqui.
        </p>
      </div>
    );
  }

  const pct = data.summary.adherence_pct;
  const toneCfg =
    pct === null
      ? { border: "border-white/[0.06]", text: "text-foreground/70", icon: "text-foreground/60" }
      : pct >= 85
      ? {
          border: "border-classification-routine/25 bg-classification-routine/[0.02]",
          text: "text-classification-routine",
          icon: "text-classification-routine",
        }
      : pct >= 60
      ? {
          border: "border-classification-attention/25 bg-classification-attention/[0.02]",
          text: "text-classification-attention",
          icon: "text-classification-attention",
        }
      : {
          border: "border-classification-critical/25 bg-classification-critical/[0.02]",
          text: "text-classification-critical",
          icon: "text-classification-critical",
        };

  const hasConsecMissed = data.consecutive_missed.length > 0;

  return (
    <div className={`glass-card rounded-2xl p-5 border ${toneCfg.border}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-2.5">
          <div className={`w-9 h-9 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center ${toneCfg.icon}`}>
            <Target className="h-4.5 w-4.5" />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold">Adesão à medicação</h3>
            <p className="text-[11px] text-foreground/60">últimos {days} dias</p>
          </div>
        </div>
        <AdherenceTrend pct={pct} />
      </div>

      {/* Big number */}
      <div className="mb-4">
        <div className="flex items-baseline gap-3">
          <div className={`text-[42px] font-bold tabular leading-none ${toneCfg.text}`}>
            {pct !== null ? `${pct}%` : "—"}
          </div>
          <div className="text-[12px] text-foreground/65">
            {data.summary.taken}/{data.summary.total} doses confirmadas
          </div>
        </div>
      </div>

      {/* Breakdown */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <Stat label="Tomadas" value={data.summary.taken} tone="ok" />
        <Stat
          label="Perdidas"
          value={data.summary.missed}
          tone={data.summary.missed > 0 ? "alert" : "neutral"}
        />
        <Stat
          label="Recusadas"
          value={data.summary.refused + data.summary.skipped}
          tone="neutral"
        />
      </div>

      {/* Alertas de missed consecutivos */}
      {hasConsecMissed && (
        <div className="rounded-lg bg-classification-critical/5 border border-classification-critical/25 px-3 py-2.5 mb-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-classification-critical flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-[12px] font-semibold text-classification-critical">
                Atenção · 3+ doses perdidas consecutivas
              </div>
              <ul className="text-[12px] text-foreground/80 mt-1 space-y-0.5">
                {data.consecutive_missed.map((m, i) => (
                  <li key={i}>
                    • {m.medication_name}: {m.missed_in_last_n} perdidas nas
                    últimas {m.recent_statuses.length} doses
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Breakdown por medicação */}
      {data.by_medication.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold mb-2">
            Por medicamento
          </div>
          <ul className="space-y-1.5">
            {data.by_medication.map((m, i) => (
              <MedBreakdownRow key={i} med={m} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "ok" | "alert" | "neutral";
}) {
  const cls =
    tone === "ok"
      ? "bg-classification-routine/8 border-classification-routine/20 text-classification-routine"
      : tone === "alert"
      ? "bg-classification-critical/8 border-classification-critical/20 text-classification-critical"
      : "bg-white/[0.03] border-white/[0.06] text-foreground/70";
  return (
    <div className={`rounded-lg border px-2.5 py-2 ${cls}`}>
      <div className="text-[18px] font-bold tabular leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wider mt-0.5 opacity-80">
        {label}
      </div>
    </div>
  );
}

function AdherenceTrend({ pct }: { pct: number | null }) {
  if (pct === null) return null;
  if (pct >= 85)
    return (
      <div className="inline-flex items-center gap-1 text-[11px] text-classification-routine">
        <CheckCircle2 className="h-3.5 w-3.5" />
        <span className="font-semibold">Boa adesão</span>
      </div>
    );
  if (pct >= 60)
    return (
      <div className="inline-flex items-center gap-1 text-[11px] text-classification-attention">
        <TrendingDown className="h-3.5 w-3.5" />
        <span className="font-semibold">Atenção</span>
      </div>
    );
  return (
    <div className="inline-flex items-center gap-1 text-[11px] text-classification-critical">
      <TrendingDown className="h-3.5 w-3.5" />
      <span className="font-semibold">Abaixo do esperado</span>
    </div>
  );
}

function MedBreakdownRow({
  med,
}: {
  med: {
    medication_name: string;
    dose: string;
    taken: number;
    missed: number;
    refused_skipped: number;
    total: number;
    adherence_pct: number | null;
  };
}) {
  const pct = med.adherence_pct;
  const barColor =
    pct === null
      ? "bg-foreground/20"
      : pct >= 85
      ? "bg-classification-routine"
      : pct >= 60
      ? "bg-classification-attention"
      : "bg-classification-critical";

  return (
    <li className="flex items-center gap-3 bg-white/[0.02] border border-white/[0.04] rounded-lg px-3 py-2">
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium text-foreground">
          {med.medication_name}
          <span className="text-foreground/60 ml-1.5 font-normal">{med.dose}</span>
        </div>
        <div className="mt-1.5 h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} transition-all`}
            style={{ width: `${pct ?? 0}%` }}
          />
        </div>
      </div>
      <div className="text-right flex-shrink-0 w-20">
        <div className="text-[14px] font-bold tabular">
          {pct !== null ? `${pct}%` : "—"}
        </div>
        <div className="text-[10px] text-foreground/55">
          {med.taken}/{med.total}
        </div>
      </div>
    </li>
  );
}
