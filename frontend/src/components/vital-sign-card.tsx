"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";

// ═══════════════════════════════════════════════════════════════
// Card de sinal vital com sparkline + indicador de tendência
// Inspiração: mockup Claude Design + refinamentos (hover valor exato)
// ═══════════════════════════════════════════════════════════════

export type VitalSeries = {
  label: string;
  unit: string;
  icon: string;              // emoji ou texto curto
  current: number | null;
  secondary?: number | null; // pro caso PA (sys/dia)
  data: Array<{ t: string; v: number }>;
  status?: "ok" | "attention" | "urgent" | "critical";
  trend?: "up" | "down" | "stable";
  trendLabel?: string;       // "+10.6% vs média 7d"
  color?: "cyan" | "teal" | "violet" | "amber" | "rose" | "emerald";
};

const COLORS: Record<string, { line: string; fill: string; glow: string }> = {
  cyan: { line: "#31e1ff", fill: "url(#gradCyan)", glow: "rgba(49,225,255,0.2)" },
  teal: { line: "#14b8a6", fill: "url(#gradTeal)", glow: "rgba(20,184,166,0.2)" },
  violet: { line: "#a78bfa", fill: "url(#gradViolet)", glow: "rgba(167,139,250,0.2)" },
  amber: { line: "#fbbf24", fill: "url(#gradAmber)", glow: "rgba(251,191,36,0.2)" },
  rose: { line: "#fb7185", fill: "url(#gradRose)", glow: "rgba(251,113,133,0.2)" },
  emerald: { line: "#34d399", fill: "url(#gradEmerald)", glow: "rgba(52,211,153,0.2)" },
};

const STATUS_CONFIG: Record<string, { ring: string; dot: string; label: string }> = {
  ok: { ring: "border-white/[0.06]", dot: "bg-classification-routine", label: "ok" },
  attention: {
    ring: "border-classification-attention/40",
    dot: "bg-classification-attention",
    label: "atenção",
  },
  urgent: {
    ring: "border-classification-urgent/50 glow-critical",
    dot: "bg-classification-urgent animate-pulse-soft",
    label: "urgente",
  },
  critical: {
    ring: "border-classification-critical/60 glow-critical",
    dot: "bg-classification-critical animate-pulse-glow",
    label: "crítico",
  },
};

export function VitalSignCard({ vital }: { vital: VitalSeries }) {
  const color = vital.color || "cyan";
  const col = COLORS[color];
  const statusKey = vital.status || "ok";
  const statusCfg = STATUS_CONFIG[statusKey];

  const hasData = vital.data && vital.data.length > 0;
  const displayValue =
    vital.current !== null && vital.current !== undefined
      ? vital.secondary
        ? `${vital.current}/${vital.secondary}`
        : formatNumber(vital.current)
      : "—";

  return (
    <div
      className={`
        glass-card rounded-xl p-4 relative overflow-hidden
        transition-all hover:translate-y-[-1px] hover:border-white/[0.12]
        border ${statusCfg.ring}
      `}
    >
      {/* Header: status + ícone/nome */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-1.5 h-1.5 rounded-full ${statusCfg.dot}`} />
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground truncate">
            {vital.label}
          </div>
        </div>
        {vital.trend && (
          <TrendBadge trend={vital.trend} label={vital.trendLabel} status={statusKey} />
        )}
      </div>

      {/* Valor principal */}
      <div className="flex items-baseline gap-1.5 mb-2">
        <span className="tabular text-[1.75rem] font-bold leading-none">
          {displayValue}
        </span>
        {vital.unit && (
          <span className="text-xs text-muted-foreground font-medium">{vital.unit}</span>
        )}
      </div>

      {/* Sparkline */}
      <div className="h-12 -mx-1">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={vital.data}>
              <defs>
                <linearGradient id="gradCyan" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#31e1ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#31e1ff" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradTeal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradViolet" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#a78bfa" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradAmber" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#fbbf24" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradRose" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#fb7185" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#fb7185" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gradEmerald" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#34d399" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Tooltip
                cursor={{ stroke: col.line, strokeOpacity: 0.3 }}
                contentStyle={{
                  backgroundColor: "hsl(222, 47%, 9%)",
                  border: "1px solid hsl(220, 20%, 16%)",
                  borderRadius: "8px",
                  fontSize: "11px",
                  padding: "6px 10px",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
                }}
                labelStyle={{ color: "hsl(215,16%,57%)" }}
                itemStyle={{ color: col.line }}
                formatter={(value) => [
                  formatNumber(Number(value)) + " " + vital.unit,
                  vital.label,
                ]}
                labelFormatter={(t) => formatDate(String(t))}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke={col.line}
                strokeWidth={1.8}
                fill={col.fill}
                animationDuration={600}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground/40 text-[10px]">
            sem dados no período
          </div>
        )}
      </div>
    </div>
  );
}

function TrendBadge({
  trend,
  label,
  status,
}: {
  trend: "up" | "down" | "stable";
  label?: string;
  status: string;
}) {
  const isBad = status !== "ok";
  const Icon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;

  const color = isBad
    ? "text-classification-attention"
    : trend === "stable"
    ? "text-muted-foreground"
    : "text-classification-routine";

  return (
    <div
      className={`flex items-center gap-1 text-[10px] font-medium ${color}`}
      title={label}
    >
      <Icon className="h-3 w-3" />
      {label && <span className="truncate max-w-[110px]">{label}</span>}
    </div>
  );
}

function formatNumber(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
}

function formatDate(t: string): string {
  try {
    const d = new Date(t);
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return t;
  }
}
