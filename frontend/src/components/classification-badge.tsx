import { AlertOctagon, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

import { cn, CLASSIFICATION_LABELS } from "@/lib/utils";

type Classification = "routine" | "attention" | "urgent" | "critical" | null | undefined;

const BADGE_CLASS: Record<string, string> = {
  routine: "badge-routine",
  attention: "badge-attention",
  urgent: "badge-urgent",
  critical: "badge-critical",
};

const ICONS: Record<string, React.ReactNode> = {
  routine: <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.5} />,
  attention: <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2.5} />,
  urgent: <ShieldAlert className="h-3.5 w-3.5" strokeWidth={2.5} />,
  critical: <AlertOctagon className="h-3.5 w-3.5" strokeWidth={2.5} />,
};

export function ClassificationBadge({
  classification,
  className,
  compact = false,
}: {
  classification: Classification;
  className?: string;
  /** Versão reduzida — só ícone + label pequeno, sem padding grande */
  compact?: boolean;
}) {
  const key = classification || "routine";
  const label = CLASSIFICATION_LABELS[key] || key;

  if (compact) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-md",
          BADGE_CLASS[key],
          className,
        )}
      >
        {ICONS[key]}
        <span>{label}</span>
      </span>
    );
  }

  return (
    <span className={cn("badge-classification", BADGE_CLASS[key], className)}>
      {ICONS[key]}
      <span>{label}</span>
    </span>
  );
}
