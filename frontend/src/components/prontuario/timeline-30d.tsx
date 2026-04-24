"use client";

import { useMemo, useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Eye,
  FileText,
  MessageSquare,
  Pill,
  Stethoscope,
  Video,
} from "lucide-react";

import type {
  CareEvent,
  MedicationEvent,
  Report,
} from "../../../../exploracoes/mocks/patients";

// ══════════════════════════════════════════════════════════════════
// Unified event model (combina reports + care_events + medication_events)
// ══════════════════════════════════════════════════════════════════

type EventKind =
  | "checkin"
  | "medication_taken"
  | "medication_refused"
  | "care_event_open"
  | "care_event_resolved"
  | "teleconsulta"
  | "exam"
  | "family_access"
  | "alert_critical";

interface TimelineEvent {
  id: string;
  at: string; // ISO
  kind: EventKind;
  title: string;
  description: string;
  severity?: "routine" | "attention" | "urgent" | "critical";
}

interface Props {
  reports: Report[];
  care_events: CareEvent[];
  medication_events: MedicationEvent[];
}

// ══════════════════════════════════════════════════════════════════
// Transformer
// ══════════════════════════════════════════════════════════════════

function buildTimeline(p: Props): TimelineEvent[] {
  const out: TimelineEvent[] = [];

  // Reports → check-ins
  for (const r of p.reports) {
    out.push({
      id: `r-${r.id}`,
      at: r.received_at,
      kind: r.classification === "critical" || r.classification === "urgent"
        ? "alert_critical"
        : "checkin",
      title:
        r.analysis?.summary ??
        (r.transcription ? r.transcription.slice(0, 80) : "Relato do cuidador"),
      description: r.caregiver_name_claimed
        ? `Por ${r.caregiver_name_claimed} · classificação ${labelSeverity(r.classification)}`
        : labelSeverity(r.classification),
      severity: r.classification,
    });
  }

  // Care events (aberto/resolvido)
  for (const e of p.care_events) {
    out.push({
      id: `ce-${e.id}-open`,
      at: e.opened_at,
      kind: "care_event_open",
      title: `Evento #${e.human_id.toString().padStart(4, "0")} aberto`,
      description: e.summary ?? `Tipo: ${e.event_type ?? "—"}`,
      severity: e.current_classification,
    });
    if (e.resolved_at) {
      out.push({
        id: `ce-${e.id}-resolved`,
        at: e.resolved_at,
        kind: "care_event_resolved",
        title: `Evento #${e.human_id.toString().padStart(4, "0")} resolvido`,
        description: e.closed_reason
          ? labelClosedReason(e.closed_reason)
          : "Encerrado",
        severity: "routine",
      });
    }
  }

  // Medication events
  for (const m of p.medication_events) {
    if (m.status === "taken") {
      out.push({
        id: `m-${m.id}`,
        at: m.confirmed_at ?? m.scheduled_at,
        kind: "medication_taken",
        title: `${m.medication_name} ${m.dose} tomada`,
        description: m.confirmed_by
          ? `Confirmado por ${m.confirmed_by === "patient" ? "paciente" : "cuidador"}`
          : "Confirmado",
        severity: "routine",
      });
    } else if (m.status === "refused") {
      out.push({
        id: `m-${m.id}`,
        at: m.confirmed_at ?? m.scheduled_at,
        kind: "medication_refused",
        title: `${m.medication_name} recusada`,
        description: "Paciente não tomou a dose",
        severity: "attention",
      });
    }
  }

  return out.sort((a, b) => b.at.localeCompare(a.at));
}

// ══════════════════════════════════════════════════════════════════
// Component
// ══════════════════════════════════════════════════════════════════

const FILTERS: { key: EventKind | "all"; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "checkin", label: "Check-ins" },
  { key: "medication_taken", label: "Medicação" },
  { key: "care_event_open", label: "Eventos" },
  { key: "alert_critical", label: "Alertas" },
];

export function Timeline30d(props: Props) {
  const [filter, setFilter] = useState<EventKind | "all">("all");
  const events = useMemo(() => buildTimeline(props), [props]);
  const filtered = useMemo(() => {
    if (filter === "all") return events;
    if (filter === "medication_taken") {
      return events.filter(
        (e) => e.kind === "medication_taken" || e.kind === "medication_refused",
      );
    }
    if (filter === "care_event_open") {
      return events.filter(
        (e) => e.kind === "care_event_open" || e.kind === "care_event_resolved",
      );
    }
    return events.filter((e) => e.kind === filter);
  }, [events, filter]);

  return (
    <section className="glass-card rounded-2xl p-6">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <div>
          <h2 className="text-lg font-semibold">Timeline — últimos 30 dias</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {events.length} eventos registrados
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtros de timeline">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                filter === f.key
                  ? "bg-accent-cyan/15 border border-accent-cyan/35 text-accent-cyan"
                  : "border border-white/5 text-muted-foreground hover:text-foreground hover:bg-white/5"
              }`}
              aria-pressed={filter === f.key}
            >
              {f.label}
            </button>
          ))}
        </div>
      </header>

      {filtered.length === 0 ? (
        <div className="text-center py-8 text-sm text-muted-foreground">
          Nenhum evento neste filtro.
        </div>
      ) : (
        <ol className="relative">
          {/* linha vertical */}
          <div
            aria-hidden
            className="absolute left-[13px] top-2 bottom-2 w-px bg-gradient-to-b from-accent-cyan/30 via-white/10 to-transparent"
          />

          {filtered.map((evt, idx) => (
            <TimelineRow
              key={evt.id}
              event={evt}
              isLast={idx === filtered.length - 1}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

// ══════════════════════════════════════════════════════════════════
// Row
// ══════════════════════════════════════════════════════════════════

function TimelineRow({
  event,
  isLast,
}: {
  event: TimelineEvent;
  isLast: boolean;
}) {
  const IconComp = iconForKind(event.kind);
  const colorClasses = colorForSeverity(event.severity);

  return (
    <li className={`relative pl-10 ${isLast ? "pb-0" : "pb-4"}`}>
      <div
        className={`absolute left-0 top-1 w-7 h-7 rounded-full flex items-center justify-center border ${colorClasses.dot}`}
      >
        <IconComp className="h-3.5 w-3.5" aria-hidden />
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className={`text-sm font-medium ${colorClasses.text}`}>
          {event.title}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground ml-auto tabular">
          {formatTime(event.at)}
        </span>
      </div>
      <p className="text-xs text-muted-foreground mt-0.5">{event.description}</p>
    </li>
  );
}

// ══════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════

function iconForKind(kind: EventKind) {
  switch (kind) {
    case "checkin":
      return MessageSquare;
    case "medication_taken":
      return Pill;
    case "medication_refused":
      return AlertTriangle;
    case "care_event_open":
      return Stethoscope;
    case "care_event_resolved":
      return CheckCircle2;
    case "teleconsulta":
      return Video;
    case "exam":
      return FileText;
    case "family_access":
      return Eye;
    case "alert_critical":
      return AlertOctagon;
    default:
      return MessageSquare;
  }
}

function colorForSeverity(severity?: string) {
  switch (severity) {
    case "critical":
      return {
        dot: "border-classification-critical/45 bg-classification-critical/15 text-classification-critical",
        text: "text-classification-critical",
      };
    case "urgent":
      return {
        dot: "border-classification-urgent/40 bg-classification-urgent/12 text-classification-urgent",
        text: "text-foreground",
      };
    case "attention":
      return {
        dot: "border-classification-attention/35 bg-classification-attention/10 text-classification-attention",
        text: "text-foreground",
      };
    default:
      return {
        dot: "border-classification-routine/30 bg-classification-routine/8 text-classification-routine",
        text: "text-foreground/90",
      };
  }
}

function labelSeverity(s: string): string {
  return {
    routine: "rotina",
    attention: "atenção",
    urgent: "urgente",
    critical: "crítico",
  }[s] ?? s;
}

function labelClosedReason(r: string): string {
  return {
    cuidado_iniciado: "Cuidado iniciado",
    encaminhado_hospital: "Encaminhado ao hospital",
    transferido: "Transferido",
    sem_intercorrencia: "Sem intercorrência",
    falso_alarme: "Falso alarme",
    paciente_estavel: "Paciente estável",
    expirou_sem_feedback: "Expirado sem feedback",
    outro: "Outro",
  }[r] ?? r;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date("2026-04-23T22:00:00Z");
  const diffMs = now.getTime() - d.getTime();
  const diffH = Math.round(diffMs / 1000 / 60 / 60);

  if (diffH < 1) return "agora há pouco";
  if (diffH < 24) return `há ${diffH}h`;
  const diffD = Math.round(diffH / 24);
  if (diffD <= 7) return `há ${diffD}d`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}
