"use client";

// SLA chart — 3 barras horizontais (rotina/atenção/urgente) + mediana + ligações família
// Não usa Recharts (é só 3 barras simples) — CSS puro é mais leve e preciso pro design

type Counts = Record<"routine" | "attention" | "urgent" | "critical", number>;

export function SlaResponseChart({
  counts,
  median,
  familyCalls,
}: {
  counts: Counts;
  median: string;
  familyCalls: number;
}) {
  const total = counts.routine + counts.attention + counts.urgent + counts.critical;
  const maxCount = Math.max(counts.routine, counts.attention, counts.urgent + counts.critical, 1);

  const buckets = [
    {
      label: "< 30s",
      kind: "Rotina",
      value: counts.routine,
      color: "bg-classification-routine",
      textColor: "text-classification-routine",
    },
    {
      label: "30-60s",
      kind: "Atenção",
      value: counts.attention,
      color: "bg-classification-attention",
      textColor: "text-classification-attention",
    },
    {
      label: "> 60s",
      kind: "Urgente",
      value: counts.urgent + counts.critical,
      color: "bg-classification-urgent",
      textColor: "text-classification-urgent",
    },
  ];

  return (
    <section className="glass-card rounded-xl p-5">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold">SLA de resposta · 24h</h2>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-0.5">
            Áudio → análise → acionamento
          </p>
        </div>
      </div>

      {/* Barras */}
      <div className="space-y-3 mb-5">
        {buckets.map((b) => {
          const pct = (b.value / maxCount) * 100;
          return (
            <div key={b.label} className="flex items-center gap-3 text-[13px]">
              <div className="w-16 text-muted-foreground tabular font-mono text-xs">
                {b.label}
              </div>
              <div className={`w-20 ${b.textColor} font-medium`}>{b.kind}</div>
              <div className="flex-1 h-2 rounded-full bg-white/[0.04] overflow-hidden">
                <div
                  className={`h-full ${b.color} transition-all duration-700 ease-out rounded-full`}
                  style={{
                    width: b.value > 0 ? `${Math.max(pct, 8)}%` : "0%",
                  }}
                />
              </div>
              <div className="w-6 text-right tabular font-semibold">
                {b.value}
              </div>
            </div>
          );
        })}
      </div>

      {/* Divider */}
      <div className="border-t border-white/[0.04] -mx-5 px-5 pt-4 grid grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
            Mediana
          </div>
          <div className="tabular text-2xl font-bold mt-0.5">{median}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
            Ligações à família
          </div>
          <div className="tabular text-2xl font-bold mt-0.5">{familyCalls}</div>
        </div>
      </div>

      {total === 0 && (
        <div className="mt-4 text-xs text-muted-foreground italic text-center">
          Sem relatos nas últimas 24h.
        </div>
      )}
    </section>
  );
}
