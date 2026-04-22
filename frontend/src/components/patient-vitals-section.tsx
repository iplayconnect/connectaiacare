"use client";

import { useEffect, useState } from "react";
import { Activity, Loader2 } from "lucide-react";

import { VitalSignCard, type VitalSeries } from "@/components/vital-sign-card";

// ═══════════════════════════════════════════════════════════════
// Seção de sinais vitais do paciente com tabs 7d/30d/90d
// Fetch client-side pra poder trocar janela sem recarregar página
// ═══════════════════════════════════════════════════════════════

type VitalRaw = {
  id: string;
  vital_type: string;
  value_numeric: number | null;
  value_secondary: number | null;
  unit: string;
  status: string;
  source: string;
  measured_at: string;
};

type WindowDays = 7 | 30 | 90;

const VITAL_TYPES_ORDER = [
  "blood_pressure_composite",
  "heart_rate",
  "oxygen_saturation",
  "temperature",
  "blood_glucose",
  "weight",
] as const;

const VITAL_META: Record<
  string,
  {
    label: string;
    unit: string;
    color: VitalSeries["color"];
    normalRange: (v: number, secondary?: number | null) => "ok" | "attention" | "urgent" | "critical";
  }
> = {
  blood_pressure_composite: {
    label: "Pressão Arterial",
    unit: "mmHg",
    color: "rose",
    normalRange: (sys, dia) => {
      const d = dia ?? 0;
      if (sys >= 180 || d >= 120) return "critical";
      if (sys >= 160 || d >= 100) return "urgent";
      if (sys >= 140 || d >= 90) return "attention";
      if (sys < 90 || d < 60) return "attention";
      return "ok";
    },
  },
  heart_rate: {
    label: "Frequência Cardíaca",
    unit: "bpm",
    color: "cyan",
    normalRange: (v) => {
      if (v < 45 || v > 130) return "urgent";
      if (v < 55 || v > 110) return "attention";
      return "ok";
    },
  },
  oxygen_saturation: {
    label: "Saturação",
    unit: "%",
    color: "teal",
    normalRange: (v) => {
      if (v < 88) return "critical";
      if (v < 92) return "urgent";
      if (v < 95) return "attention";
      return "ok";
    },
  },
  temperature: {
    label: "Temperatura",
    unit: "°C",
    color: "amber",
    normalRange: (v) => {
      if (v >= 39 || v <= 35) return "urgent";
      if (v >= 37.8 || v <= 35.5) return "attention";
      return "ok";
    },
  },
  blood_glucose: {
    label: "Glicemia",
    unit: "mg/dL",
    color: "violet",
    normalRange: (v) => {
      if (v >= 250 || v <= 60) return "urgent";
      if (v >= 180 || v <= 70) return "attention";
      return "ok";
    },
  },
  weight: {
    label: "Peso",
    unit: "kg",
    color: "emerald",
    normalRange: () => "ok",
  },
};

export function PatientVitalsSection({ patientId }: { patientId: string }) {
  const [window, setWindow] = useState<WindowDays>(7);
  const [data, setData] = useState<VitalSeries[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastSync, setLastSync] = useState<Date | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

    async function load() {
      try {
        const res = await fetch(
          `${apiBase}/api/patients/${patientId}/vitals?days=${window}`,
          { cache: "no-store" },
        );
        if (!mounted || !res.ok) return;
        const payload = await res.json();
        const vitals: VitalRaw[] = payload.vitals || [];

        // Agrupa por tipo
        const byType: Record<string, VitalRaw[]> = {};
        vitals.forEach((v) => {
          if (!byType[v.vital_type]) byType[v.vital_type] = [];
          byType[v.vital_type].push(v);
        });

        // Sort asc dentro de cada tipo pro sparkline ir da esquerda→direita
        Object.values(byType).forEach((arr) => {
          arr.sort((a, b) => a.measured_at.localeCompare(b.measured_at));
        });

        // Pega última sync: medição mais recente entre todas
        const allSorted = [...vitals].sort((a, b) =>
          b.measured_at.localeCompare(a.measured_at),
        );
        if (allSorted.length > 0) {
          setLastSync(new Date(allSorted[0].measured_at));
        }

        // Monta series na ordem fixa
        const series: VitalSeries[] = VITAL_TYPES_ORDER.map((type) => {
          const meta = VITAL_META[type];
          const rows = byType[type] || [];
          const last = rows[rows.length - 1] || null;

          const current = last?.value_numeric ?? null;
          const secondary = last?.value_secondary ?? null;

          // Calcular status do valor atual
          let status: VitalSeries["status"] = "ok";
          if (current !== null) {
            status = meta.normalRange(current, secondary);
          }

          // Tendência vs média 7d
          let trend: VitalSeries["trend"] = "stable";
          let trendLabel: string | undefined;
          if (rows.length >= 3 && current !== null) {
            const values = rows.map((r) => r.value_numeric ?? 0);
            const avg = values.reduce((a, b) => a + b, 0) / values.length;
            const diff = current - avg;
            const pct = (diff / avg) * 100;
            if (Math.abs(pct) >= 5) {
              trend = pct > 0 ? "up" : "down";
              trendLabel = `${pct > 0 ? "+" : ""}${pct.toFixed(1)}% vs média ${window}d`;
            } else {
              trendLabel = "estável";
            }
          }

          return {
            label: meta.label,
            unit: meta.unit,
            icon: "",
            current,
            secondary,
            data: rows.map((r) => ({
              t: r.measured_at,
              v: Number(r.value_numeric || 0),
            })),
            status,
            trend,
            trendLabel,
            color: meta.color,
          };
        });

        setData(series);
      } catch (err) {
        console.error("vitals load failed", err);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [patientId, window]);

  return (
    <section>
      {/* Header com label + tabs */}
      <div className="flex items-baseline justify-between mb-4 flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground flex items-center gap-2">
            <Activity className="h-3 w-3 text-accent-cyan" />
            MedMonitor · {lastSync ? `última sincronização ${timeAgo(lastSync)}` : "aguardando dados"}
          </div>
          <h2 className="text-[1.125rem] font-semibold mt-0.5">
            Sinais Vitais <span className="text-muted-foreground font-normal text-sm">· últimos {window} dias</span>
          </h2>
        </div>
        <WindowTabs current={window} onChange={setWindow} />
      </div>

      {/* Grid de 6 cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {loading || !data ? (
          Array.from({ length: 6 }).map((_, i) => (
            <VitalSkeleton key={i} />
          ))
        ) : (
          data.map((v) => <VitalSignCard key={v.label} vital={v} />)
        )}
      </div>
    </section>
  );
}

function WindowTabs({
  current,
  onChange,
}: {
  current: WindowDays;
  onChange: (w: WindowDays) => void;
}) {
  const options: WindowDays[] = [7, 30, 90];
  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-white/[0.03] border border-white/[0.06]">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`
            px-3 py-1 rounded-md text-xs font-medium transition-all
            ${
              current === o
                ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20"
                : "text-muted-foreground hover:text-foreground border border-transparent"
            }
          `}
        >
          {o}d
        </button>
      ))}
    </div>
  );
}

function VitalSkeleton() {
  return (
    <div className="glass-card rounded-xl p-4 border border-white/[0.06]">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1.5 h-1.5 rounded-full bg-white/10" />
        <div className="h-3 w-20 rounded bg-white/5 animate-pulse" />
      </div>
      <div className="h-7 w-24 rounded bg-white/5 animate-pulse mb-2" />
      <div className="h-12 rounded bg-white/[0.02] flex items-center justify-center">
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/50" />
      </div>
    </div>
  );
}

function timeAgo(date: Date): string {
  const s = Math.floor((Date.now() - date.getTime()) / 1000);
  if (s < 60) return `${s}s atrás`;
  if (s < 3600) return `há ${Math.floor(s / 60)}min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)}h`;
  return `há ${Math.floor(s / 86400)}d`;
}
