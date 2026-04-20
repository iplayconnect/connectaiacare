import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function calcAge(birthDate: string | null): number | null {
  if (!birthDate) return null;
  const bd = new Date(birthDate);
  const today = new Date();
  let age = today.getFullYear() - bd.getFullYear();
  const m = today.getMonth() - bd.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < bd.getDate())) age--;
  return age;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "agora";
  if (diffSec < 3600) return `há ${Math.floor(diffSec / 60)} min`;
  if (diffSec < 86400) return `há ${Math.floor(diffSec / 3600)} h`;
  return `há ${Math.floor(diffSec / 86400)} dias`;
}

export const CLASSIFICATION_LABELS: Record<string, string> = {
  routine: "Rotina",
  attention: "Atenção",
  urgent: "Urgente",
  critical: "Crítico",
};

export const CLASSIFICATION_COLORS: Record<string, string> = {
  routine: "badge-routine",
  attention: "badge-attention",
  urgent: "badge-urgent",
  critical: "badge-critical",
};

export function classificationTone(classification?: string | null): string {
  switch (classification) {
    case "critical":
      return "text-classification-critical";
    case "urgent":
      return "text-classification-urgent";
    case "attention":
      return "text-classification-attention";
    case "routine":
    default:
      return "text-classification-routine";
  }
}
