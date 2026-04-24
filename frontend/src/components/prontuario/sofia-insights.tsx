import { AlertTriangle, Lightbulb, TrendingUp } from "lucide-react";

import type { SofiaInsight } from "@/hooks/use-patient";

interface Props {
  insights: SofiaInsight[];
}

/**
 * Insights da Sofia — 3 cards (padrão, recomendação, alerta preventivo).
 *
 * Cada card mostra:
 *   - Ícone + tipo + título
 *   - Descrição do insight
 *   - Confiança (barra + %)
 *   - Fontes (chunks KB / janelas de dados que fundamentaram)
 *   - Disclaimer CFM 2.314/2022 (apoio, não autônomo)
 *
 * Filosofia (ADR-027 §5): Sofia NUNCA diagnostica/prescreve.
 * Estes insights são sugestões pro médico, não decisões.
 */
export function SofiaInsights({ insights }: Props) {
  if (!insights.length) {
    return null;
  }

  return (
    <section className="glass-card rounded-2xl p-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full accent-gradient flex items-center justify-center">
              <Lightbulb className="h-3.5 w-3.5 text-slate-900" strokeWidth={2.5} />
            </div>
            <h2 className="text-lg font-semibold">
              <span className="accent-gradient-text">Sofia</span>
              <span className="text-foreground/80"> insights</span>
            </h2>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5 ml-9">
            Padrões detectados nos últimos 30 dias
          </p>
        </div>

        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {insights.length} novos
        </span>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} />
        ))}
      </div>
    </section>
  );
}

function InsightCard({ insight }: { insight: SofiaInsight }) {
  const { accent, icon: Icon, label } = styleForType(insight.type);
  const confPct = Math.round(insight.confidence * 100);

  return (
    <article
      className={`solid-card rounded-xl p-4 border-l-2 ${accent.borderL} flex flex-col gap-3`}
      aria-label={`${label}: ${insight.title}`}
    >
      <div className="flex items-start gap-2">
        <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 ${accent.iconBg}`}>
          <Icon className={`h-4 w-4 ${accent.icon}`} aria-hidden />
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-[10px] uppercase tracking-wider font-semibold ${accent.label}`}>
            {label}
          </div>
          <h3 className="text-sm font-semibold text-foreground leading-tight mt-0.5">
            {insight.title}
          </h3>
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed flex-1">
        {insight.description}
      </p>

      {/* Confiança */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
          <span className="text-muted-foreground font-semibold">Confiança</span>
          <span className={`font-semibold tabular ${accent.label}`}>{confPct}%</span>
        </div>
        <div className="h-1 bg-white/5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${accent.bar}`}
            style={{ width: `${confPct}%` }}
            aria-hidden
          />
        </div>
      </div>

      {/* Fontes */}
      {insight.sources.length > 0 && (
        <details className="group">
          <summary className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
            {insight.sources.length} fonte{insight.sources.length > 1 ? "s" : ""}
          </summary>
          <ul className="mt-2 space-y-0.5">
            {insight.sources.map((s) => (
              <li key={s} className="text-[10px] text-muted-foreground font-mono">
                · {s}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Disclaimer CFM */}
      {insight.cfm_disclaimer && (
        <div className="mt-auto pt-2 border-t border-white/5 text-[10px] text-muted-foreground/80 italic">
          Apoio clínico (CFM 2.314/2022) · não autônomo, decisão médica
        </div>
      )}
    </article>
  );
}

function styleForType(type: SofiaInsight["type"]) {
  switch (type) {
    case "pattern":
      return {
        icon: TrendingUp,
        label: "Padrão",
        accent: {
          borderL: "border-accent-cyan/60",
          iconBg: "bg-accent-cyan/12",
          icon: "text-accent-cyan",
          label: "text-accent-cyan",
          bar: "bg-accent-cyan",
        },
      };
    case "recommendation":
      return {
        icon: Lightbulb,
        label: "Recomendação",
        accent: {
          borderL: "border-accent-teal/60",
          iconBg: "bg-accent-teal/12",
          icon: "text-accent-teal",
          label: "text-accent-teal",
          bar: "bg-accent-teal",
        },
      };
    case "alert":
      return {
        icon: AlertTriangle,
        label: "Alerta",
        accent: {
          borderL: "border-classification-attention/60",
          iconBg: "bg-classification-attention/12",
          icon: "text-classification-attention",
          label: "text-classification-attention",
          bar: "bg-classification-attention",
        },
      };
  }
}
