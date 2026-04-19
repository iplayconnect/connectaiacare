import { cn, CLASSIFICATION_LABELS, CLASSIFICATION_COLORS } from "@/lib/utils";

export function ClassificationBadge({
  classification,
  className,
}: {
  classification: string | null | undefined;
  className?: string;
}) {
  const key = classification || "routine";
  const label = CLASSIFICATION_LABELS[key] || key;
  const color = CLASSIFICATION_COLORS[key] || "badge-routine";

  const icon =
    key === "critical" ? "🆘" : key === "urgent" ? "🚨" : key === "attention" ? "⚠️" : "✅";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-semibold",
        color,
        className
      )}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </span>
  );
}
