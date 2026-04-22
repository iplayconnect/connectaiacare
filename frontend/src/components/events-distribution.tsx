"use client";

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

// Donut chart da distribuição de classificações em 24h
// Design: números no centro + legenda vertical minimalista

const COLORS: Record<string, string> = {
  routine: "#10b981",    // emerald
  attention: "#f59e0b",  // amber
  urgent: "#f43f5e",     // rose
  critical: "#ef4444",   // red
};

const LABELS: Record<string, string> = {
  routine: "Rotina",
  attention: "Atenção",
  urgent: "Urgente",
  critical: "Crítico",
};

type Counts = Record<"routine" | "attention" | "urgent" | "critical", number>;

export function EventsDistribution({
  counts,
  total,
}: {
  counts: Counts;
  total: number;
}) {
  const data = (["routine", "attention", "urgent", "critical"] as const)
    .map((key) => ({
      name: LABELS[key],
      value: counts[key],
      key,
    }))
    .filter((d) => d.value > 0);

  const hasData = total > 0;

  return (
    <section className="glass-card rounded-xl p-5">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold">Distribuição de classificações</h2>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-0.5">
            Últimas 24h · N = {total}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-[160px_1fr] gap-5 items-center">
        {/* Donut */}
        <div className="relative h-40 w-40 mx-auto">
          {hasData ? (
            <>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={74}
                    paddingAngle={2}
                    stroke="none"
                    animationDuration={800}
                  >
                    {data.map((entry) => (
                      <Cell
                        key={entry.key}
                        fill={COLORS[entry.key]}
                        className="transition-opacity hover:opacity-80"
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <div className="tabular text-4xl font-bold leading-none">{total}</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1">
                  relatos
                </div>
              </div>
            </>
          ) : (
            <div className="h-40 w-40 flex items-center justify-center rounded-full border-2 border-dashed border-white/[0.08]">
              <div className="text-center">
                <div className="tabular text-4xl font-bold leading-none text-muted-foreground/60">0</div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground/50 mt-1">
                  relatos
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Legenda */}
        <ul className="space-y-2">
          {(["routine", "attention", "urgent", "critical"] as const).map((key) => (
            <li
              key={key}
              className="flex items-center gap-2.5 text-sm group"
            >
              <span
                className="w-2.5 h-2.5 rounded-sm flex-shrink-0 transition-transform group-hover:scale-125"
                style={{ backgroundColor: COLORS[key] }}
              />
              <span className="text-foreground/80 text-[13px]">{LABELS[key]}</span>
              <span
                className={`ml-auto tabular font-semibold ${
                  counts[key] > 0 ? "text-foreground" : "text-muted-foreground/50"
                }`}
              >
                {counts[key]}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
