import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

import type { AlertClassification } from "@/hooks/use-alerts";

// ══════════════════════════════════════════════════════════════════
// STATUS_SYSTEM — fonte única (DEC-005 · WCAG 2.1 AA)
// Cada status tem: cor + ícone + padrão de borda + label
// ══════════════════════════════════════════════════════════════════

export const STATUS_SYSTEM: Record<
  AlertClassification,
  {
    label: string;
    color: string;
    colorSoft: string;
    border: string;
    icon: LucideIcon;
    pattern: "solid-thin" | "dashed" | "solid-thick" | "solid-thick-pulse";
  }
> = {
  routine: {
    label: "Rotina",
    color: "#34d399",
    colorSoft: "rgba(52, 211, 153, 0.12)",
    border: "rgba(52, 211, 153, 0.32)",
    icon: CheckCircle2,
    pattern: "solid-thin",
  },
  attention: {
    label: "Atenção",
    color: "#fbbf24",
    colorSoft: "rgba(251, 191, 36, 0.12)",
    border: "rgba(251, 191, 36, 0.38)",
    icon: AlertTriangle,
    pattern: "dashed",
  },
  urgent: {
    label: "Urgente",
    color: "#fb923c",
    colorSoft: "rgba(251, 146, 60, 0.14)",
    border: "rgba(251, 146, 60, 0.48)",
    icon: ShieldAlert,
    pattern: "solid-thick",
  },
  critical: {
    label: "Crítico",
    color: "#ef4444",
    colorSoft: "rgba(239, 68, 68, 0.16)",
    border: "rgba(239, 68, 68, 0.55)",
    icon: AlertOctagon,
    pattern: "solid-thick-pulse",
  },
};

export const SEVERITY_ORDER: Record<AlertClassification, number> = {
  critical: 0,
  urgent: 1,
  attention: 2,
  routine: 3,
};

// ══════════════════════════════════════════════════════════════════
// StatusBadge (reusável em todo o app)
// ══════════════════════════════════════════════════════════════════

interface Props {
  classification: AlertClassification;
  size?: "sm" | "md";
}

export function AlertStatusBadge({ classification, size = "md" }: Props) {
  const s = STATUS_SYSTEM[classification];
  const Icon = s.icon;

  const sizeClasses =
    size === "sm"
      ? "px-2 py-0.5 text-[10px] gap-1"
      : "px-2.5 py-1 text-[11px] gap-1.5";
  const iconSize = size === "sm" ? 11 : 13;

  const borderStyle = {
    "solid-thin": { borderStyle: "solid", borderWidth: 1 },
    dashed: { borderStyle: "dashed", borderWidth: 1 },
    "solid-thick": { borderStyle: "solid", borderWidth: 1.5 },
    "solid-thick-pulse": { borderStyle: "solid", borderWidth: 1.5 },
  }[s.pattern];

  return (
    <span
      className={`inline-flex items-center font-semibold uppercase tracking-wider rounded-full ${sizeClasses} ${
        s.pattern === "solid-thick-pulse" ? "animate-pulse-soft" : ""
      }`}
      style={{
        background: s.colorSoft,
        borderColor: s.border,
        color: s.color,
        boxShadow: s.pattern === "solid-thick-pulse" ? `0 0 10px ${s.colorSoft}` : "none",
        ...borderStyle,
      }}
      aria-label={`Classificação: ${s.label}`}
    >
      <Icon size={iconSize} strokeWidth={2.5} aria-hidden />
      <span>{s.label}</span>
    </span>
  );
}
