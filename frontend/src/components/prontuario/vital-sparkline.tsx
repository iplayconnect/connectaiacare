import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";

interface Range {
  min: number;
  max: number;
}

interface Props {
  label: string;
  unit: string;
  values: number[];
  target?: Range; // banda alvo (verde no gráfico)
  delta7d?: number;
  direction?: "up" | "down" | "stable";
  /** inverter semântica da seta: quando o "bom" é descer (ex: PA), seta pra baixo não é alarme */
  betterIsLower?: boolean;
  anomalyThreshold?: Range; // acima/abaixo disso = ponto vermelho
  className?: string;
  ariaLabel?: string;
}

/**
 * Sparkline SVG mínimo pra sinais vitais.
 * - Banda verde = faixa alvo
 * - Linha cinza = valores
 * - Pontos vermelhos = fora do alvo (anomalia)
 * - Último ponto destacado em cyan (valor atual)
 * - Delta 7d com seta direcional
 */
export function VitalSparkline({
  label,
  unit,
  values,
  target,
  delta7d,
  direction,
  betterIsLower = false,
  anomalyThreshold,
  className = "",
  ariaLabel,
}: Props) {
  if (!values.length) {
    return (
      <div
        className={`solid-card rounded-xl p-4 ${className}`}
        aria-label={ariaLabel || label}
      >
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="mt-2 text-xs text-muted-foreground italic">Sem dados</div>
      </div>
    );
  }

  const last = values[values.length - 1];
  const min = Math.min(...values, target?.min ?? Infinity);
  const max = Math.max(...values, target?.max ?? -Infinity);
  const span = Math.max(1, max - min);

  const W = 200;
  const H = 50;
  const PAD = 4;

  const xStep = (W - 2 * PAD) / Math.max(1, values.length - 1);

  const points = values.map((v, i) => {
    const x = PAD + i * xStep;
    const y = H - PAD - ((v - min) / span) * (H - 2 * PAD);
    return { x, y, v };
  });

  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(" ");

  // Banda alvo (retângulo verde)
  let targetRect: JSX.Element | null = null;
  if (target) {
    const yTop = H - PAD - ((target.max - min) / span) * (H - 2 * PAD);
    const yBottom = H - PAD - ((target.min - min) / span) * (H - 2 * PAD);
    targetRect = (
      <rect
        x={PAD}
        y={Math.min(yTop, yBottom)}
        width={W - 2 * PAD}
        height={Math.abs(yBottom - yTop)}
        fill="rgba(52, 211, 153, 0.12)"
        stroke="rgba(52, 211, 153, 0.18)"
        strokeWidth="0.5"
        strokeDasharray="2 2"
      />
    );
  }

  // Delta interpretation
  const deltaIsGood =
    delta7d !== undefined &&
    (direction === "stable" ||
      (betterIsLower ? (direction === "down") : (direction === "up")));

  const deltaColor =
    direction === "stable"
      ? "text-muted-foreground"
      : deltaIsGood
        ? "text-classification-routine"
        : "text-classification-attention";

  // Anomaly dots
  const isAnomaly = (v: number): boolean => {
    if (!anomalyThreshold) return false;
    return v < anomalyThreshold.min || v > anomalyThreshold.max;
  };

  // Último valor — cor por anomalia
  const lastIsAnomaly = anomalyThreshold ? isAnomaly(last) : false;
  const lastColor = lastIsAnomaly
    ? "text-classification-attention"
    : "text-accent-cyan";

  return (
    <div
      className={`solid-card rounded-xl p-4 ${className}`}
      aria-label={ariaLabel || `${label}: último valor ${last} ${unit}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        {delta7d !== undefined && direction && (
          <div className={`flex items-center gap-0.5 text-[10px] font-semibold ${deltaColor}`}>
            {direction === "up" ? (
              <ArrowUp className="h-3 w-3" aria-hidden />
            ) : direction === "down" ? (
              <ArrowDown className="h-3 w-3" aria-hidden />
            ) : (
              <ArrowRight className="h-3 w-3" aria-hidden />
            )}
            <span className="tabular">
              {delta7d > 0 ? "+" : ""}
              {delta7d.toFixed(1)}
            </span>
            <span className="opacity-70">7d</span>
          </div>
        )}
      </div>

      <div className="mt-1 flex items-baseline gap-1.5">
        <span className={`text-2xl font-bold tabular ${lastColor}`}>
          {formatValue(last)}
        </span>
        <span className="text-xs text-muted-foreground">{unit}</span>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-12 mt-2"
        role="img"
        aria-hidden
      >
        {targetRect}
        <path
          d={pathD}
          fill="none"
          stroke="rgba(148, 163, 184, 0.5)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Anomaly dots */}
        {points.map((p, i) =>
          isAnomaly(p.v) ? (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={2.5}
              fill="#f87171"
              stroke="rgba(248, 113, 113, 0.4)"
              strokeWidth="2"
            />
          ) : null,
        )}
        {/* Último ponto em destaque */}
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r={3.5}
          fill={lastIsAnomaly ? "#fbbf24" : "#31e1ff"}
          stroke={lastIsAnomaly ? "rgba(251, 191, 36, 0.3)" : "rgba(49, 225, 255, 0.3)"}
          strokeWidth="3"
        />
      </svg>
    </div>
  );
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  if (v >= 100) return v.toFixed(0);
  return v.toFixed(1);
}
