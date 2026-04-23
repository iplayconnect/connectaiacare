"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Clock,
  Info,
  Loader2,
  Moon,
  Pill,
  Plus,
  Sun,
  Sunrise,
  Sunset,
  XCircle,
} from "lucide-react";

import { api, type MedicationEvent, type MedicationSchedule } from "@/lib/api";

import { AddMedicationWizard } from "./add-medication-wizard";

// ═══════════════════════════════════════════════════════════════
// MedicationTimeline — visão combinada de próximas doses + histórico
// Usada na ficha do paciente e no dashboard do cuidador.
// ═══════════════════════════════════════════════════════════════

type Tab = "upcoming" | "schedules" | "history";

export function MedicationTimeline({
  patientId,
  patientName,
}: {
  patientId: string;
  patientName?: string;
}) {
  const [tab, setTab] = useState<Tab>("upcoming");
  const [schedules, setSchedules] = useState<MedicationSchedule[]>([]);
  const [upcoming, setUpcoming] = useState<MedicationEvent[]>([]);
  const [history, setHistory] = useState<MedicationEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sc, up, hi] = await Promise.all([
        api.listMedicationSchedules(patientId),
        api.listUpcomingMedicationEvents(patientId, 48),
        api.listMedicationHistory(patientId, 7),
      ]);
      setSchedules(sc.results || []);
      setUpcoming(up.results || []);
      setHistory(hi.results || []);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleConfirm(event: MedicationEvent) {
    await api.confirmMedicationEvent(event.id, { confirmed_by: "caregiver" });
    await load();
  }

  async function handleSkip(event: MedicationEvent) {
    const reason =
      typeof window !== "undefined"
        ? window.prompt("Motivo para pular esta dose?") || "sem motivo"
        : "sem motivo";
    await api.skipMedicationEvent(event.id, reason);
    await load();
  }

  const tabs: Array<{ id: Tab; label: string; count?: number }> = [
    { id: "upcoming", label: "Próximas doses", count: upcoming.length },
    { id: "schedules", label: "Medicações ativas", count: schedules.length },
    { id: "history", label: "Histórico 7d", count: history.length },
  ];

  return (
    <section className="glass-card rounded-2xl border border-white/[0.06] overflow-hidden">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 p-5 border-b border-white/[0.04]">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent-cyan/15 border border-accent-cyan/30 flex items-center justify-center flex-shrink-0">
            <Pill className="h-5 w-5 text-accent-cyan" />
          </div>
          <div>
            <h2 className="text-[16px] font-semibold">Medicação</h2>
            <p className="text-[12px] text-foreground/75 leading-relaxed mt-0.5">
              {patientName ? `${patientName} · ` : ""}
              Lembretes automáticos, adesão e histórico por dose
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowWizard(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors shadow-glow-cyan"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          Adicionar
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-white/[0.04]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 px-4 py-2.5 text-[12px] font-medium uppercase tracking-[0.08em] transition-colors relative ${
              tab === t.id
                ? "text-accent-cyan"
                : "text-foreground/55 hover:text-foreground/85"
            }`}
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-white/[0.06] text-[10px]">
                {t.count}
              </span>
            )}
            {tab === t.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-cyan" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-4">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-foreground/65">
            <Loader2 className="h-4 w-4 animate-spin" />
            Carregando…
          </div>
        ) : tab === "upcoming" ? (
          <UpcomingList
            events={upcoming}
            onConfirm={handleConfirm}
            onSkip={handleSkip}
          />
        ) : tab === "schedules" ? (
          <SchedulesList
            schedules={schedules}
            onDeactivated={load}
          />
        ) : (
          <HistoryList events={history} />
        )}
      </div>

      {showWizard && (
        <AddMedicationWizard
          patientId={patientId}
          patientName={patientName}
          onClose={() => setShowWizard(false)}
          onSuccess={() => {
            setShowWizard(false);
            load();
          }}
        />
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════
// UpcomingList — próximas doses agrupadas por período do dia
// ═══════════════════════════════════════════════════════════════════

function UpcomingList({
  events,
  onConfirm,
  onSkip,
}: {
  events: MedicationEvent[];
  onConfirm: (e: MedicationEvent) => void;
  onSkip: (e: MedicationEvent) => void;
}) {
  if (events.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-foreground/65">
        <Pill className="h-10 w-10 text-foreground/20 mx-auto mb-3" />
        Nenhuma dose prevista nas próximas 48 horas.
      </div>
    );
  }

  // Agrupa por dia+período
  const grouped = useMemo(() => groupByPeriod(events), [events]);

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([groupKey, group]) => (
        <div key={groupKey}>
          <div className="flex items-center gap-2 mb-2">
            {group.icon}
            <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold">
              {group.label}
            </div>
          </div>
          <ul className="space-y-2">
            {group.events.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                onConfirm={onConfirm}
                onSkip={onSkip}
              />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function EventRow({
  event,
  onConfirm,
  onSkip,
}: {
  event: MedicationEvent;
  onConfirm: (e: MedicationEvent) => void;
  onSkip: (e: MedicationEvent) => void;
}) {
  const dt = new Date(event.scheduled_at);
  const timeStr = dt.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const isPast = dt.getTime() < Date.now() - 60_000;
  const isOverdue = isPast && event.status !== "taken" && event.status !== "skipped";

  return (
    <li
      className={`flex items-center gap-3 p-3 rounded-xl border transition-colors ${
        event.status === "taken"
          ? "bg-classification-routine/5 border-classification-routine/20"
          : isOverdue
          ? "bg-classification-attention/5 border-classification-attention/25"
          : "bg-white/[0.025] border-white/[0.05] hover:border-white/[0.1]"
      }`}
    >
      <div className="w-12 text-center flex-shrink-0">
        <div className="text-[13px] font-bold tabular text-foreground">
          {timeStr}
        </div>
        <div className="text-[9px] uppercase tracking-wider text-foreground/55">
          {isPast ? "passou" : "próximo"}
        </div>
      </div>

      <div className="w-px h-10 bg-white/[0.08]" />

      <div className="flex-1 min-w-0">
        <div className="text-[14px] font-semibold text-foreground">
          {event.medication_name}
        </div>
        <div className="text-[12px] text-foreground/70 flex flex-wrap items-center gap-x-2 mt-0.5">
          <span className="font-medium">{event.dose}</span>
          {event.with_food === "without" && (
            <span className="text-classification-attention text-[10px] uppercase">
              em jejum
            </span>
          )}
          {event.with_food === "with" && (
            <span className="text-[10px] uppercase text-foreground/55">
              com alimento
            </span>
          )}
          {event.special_instructions && (
            <span className="text-foreground/55 truncate">
              · {event.special_instructions}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5 flex-shrink-0">
        {event.status === "taken" ? (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-classification-routine/15 border border-classification-routine/25 text-classification-routine text-[11px] font-semibold">
            <Check className="h-3 w-3" strokeWidth={3} />
            Tomou
          </span>
        ) : event.status === "skipped" || event.status === "refused" ? (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/[0.08] text-foreground/60 text-[11px]">
            <XCircle className="h-3 w-3" />
            Não tomou
          </span>
        ) : (
          <>
            <button
              onClick={() => onConfirm(event)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan text-[11px] font-semibold hover:bg-accent-cyan hover:text-slate-900 transition-colors"
              title="Confirmar tomada"
            >
              <Check className="h-3 w-3" strokeWidth={3} />
              Tomou
            </button>
            <button
              onClick={() => onSkip(event)}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-white/[0.03] border border-white/[0.06] text-foreground/55 text-[11px] hover:text-foreground/85 transition-colors"
              title="Pular esta dose"
            >
              Pular
            </button>
          </>
        )}
      </div>
    </li>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SchedulesList — medicações ativas com confiança e origem
// ═══════════════════════════════════════════════════════════════════

function SchedulesList({
  schedules,
  onDeactivated,
}: {
  schedules: MedicationSchedule[];
  onDeactivated: () => void;
}) {
  if (schedules.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-foreground/65">
        <Pill className="h-10 w-10 text-foreground/20 mx-auto mb-3" />
        Nenhuma medicação cadastrada ainda.
        <br />
        Use o botão <span className="text-accent-cyan">Adicionar</span> para
        começar — pode enviar foto da caixa ou receita.
      </div>
    );
  }

  async function handleDelete(s: MedicationSchedule) {
    const ok =
      typeof window !== "undefined"
        ? window.confirm(
            `Desativar ${s.medication_name} ${s.dose}?\nO histórico é preservado.`,
          )
        : false;
    if (!ok) return;
    await api.deleteMedicationSchedule(s.id, "desativado manualmente");
    onDeactivated();
  }

  return (
    <ul className="space-y-2.5">
      {schedules.map((s) => (
        <ScheduleCard key={s.id} schedule={s} onDelete={handleDelete} />
      ))}
    </ul>
  );
}

function ScheduleCard({
  schedule,
  onDelete,
}: {
  schedule: MedicationSchedule;
  onDelete: (s: MedicationSchedule) => void;
}) {
  const needsReview = schedule.verification_status === "needs_review";
  const conflicting = schedule.verification_status === "conflicting";

  return (
    <li
      className={`rounded-xl p-3.5 border ${
        conflicting
          ? "bg-classification-critical/5 border-classification-critical/25"
          : needsReview
          ? "bg-classification-attention/5 border-classification-attention/25"
          : "bg-white/[0.025] border-white/[0.05]"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center flex-shrink-0">
          <Pill className="h-4 w-4 text-accent-cyan" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-[14px] font-semibold">
                {schedule.medication_name}{" "}
                <span className="text-foreground/70 font-normal">{schedule.dose}</span>
              </div>
              <div className="text-[12px] text-foreground/70 mt-0.5">
                {formatSchedule(schedule)}
              </div>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {conflicting && (
                <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-classification-critical/15 text-classification-critical font-semibold">
                  conflito
                </span>
              )}
              {needsReview && (
                <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-classification-attention/15 text-classification-attention font-semibold">
                  revisar
                </span>
              )}
              <SourceBadge source={schedule.source_type} />
              <button
                onClick={() => onDelete(schedule)}
                className="text-foreground/40 hover:text-classification-critical text-[11px] ml-1"
                title="Desativar"
              >
                <XCircle className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {schedule.special_instructions && (
            <div className="mt-2 text-[12px] text-foreground/70 flex items-start gap-1.5">
              <Info className="h-3 w-3 text-accent-cyan/80 mt-0.5 flex-shrink-0" />
              <span>{schedule.special_instructions}</span>
            </div>
          )}

          {schedule.warnings && schedule.warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {schedule.warnings.slice(0, 3).map((w, i) => (
                <div
                  key={i}
                  className="text-[11px] text-classification-attention flex items-start gap-1.5"
                >
                  <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function SourceBadge({ source }: { source?: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    prescription: {
      label: "receita",
      cls: "bg-accent-cyan/10 border-accent-cyan/25 text-accent-cyan",
    },
    ocr_image: {
      label: "foto",
      cls: "bg-accent-teal/10 border-accent-teal/25 text-accent-teal",
    },
    ocr_audio: {
      label: "áudio",
      cls: "bg-accent-teal/10 border-accent-teal/25 text-accent-teal",
    },
    patient_self_report: {
      label: "paciente",
      cls: "bg-white/[0.04] border-white/[0.08] text-foreground/70",
    },
    family_report: {
      label: "família",
      cls: "bg-white/[0.04] border-white/[0.08] text-foreground/70",
    },
    caregiver_pro: {
      label: "cuidador",
      cls: "bg-white/[0.04] border-white/[0.08] text-foreground/70",
    },
  };
  const cfg = map[source || ""] || {
    label: source || "manual",
    cls: "bg-white/[0.04] border-white/[0.08] text-foreground/65",
  };
  return (
    <span
      className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// HistoryList — últimos 7 dias agrupados por dia
// ═══════════════════════════════════════════════════════════════════

function HistoryList({ events }: { events: MedicationEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-foreground/65">
        Nenhum evento nos últimos 7 dias.
      </div>
    );
  }

  const byDay = useMemo(() => {
    const m: Record<string, MedicationEvent[]> = {};
    for (const e of events) {
      const d = new Date(e.scheduled_at);
      const key = d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "short" });
      if (!m[key]) m[key] = [];
      m[key].push(e);
    }
    return m;
  }, [events]);

  return (
    <div className="space-y-4">
      {Object.entries(byDay).map(([day, dayEvents]) => {
        const taken = dayEvents.filter((e) => e.status === "taken").length;
        const missed = dayEvents.filter((e) => e.status === "missed").length;
        return (
          <div key={day}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold">
                {day}
              </div>
              <div className="text-[11px] text-foreground/60">
                {taken} ✅ · {missed > 0 ? `${missed} ❌ · ` : ""}
                {dayEvents.length} total
              </div>
            </div>
            <ul className="space-y-1.5">
              {dayEvents.map((e) => (
                <HistoryRow key={e.id} event={e} />
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function HistoryRow({ event }: { event: MedicationEvent }) {
  const dt = new Date(event.scheduled_at);
  const timeStr = dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  const statusCfg = {
    taken: {
      icon: <Check className="h-3 w-3" strokeWidth={3} />,
      cls: "bg-classification-routine/10 text-classification-routine border-classification-routine/20",
      label: "tomou",
    },
    missed: {
      icon: <XCircle className="h-3 w-3" />,
      cls: "bg-classification-critical/10 text-classification-critical border-classification-critical/20",
      label: "perdeu",
    },
    skipped: {
      icon: <ChevronRight className="h-3 w-3" />,
      cls: "bg-white/[0.04] text-foreground/55 border-white/[0.06]",
      label: "pulou",
    },
    refused: {
      icon: <XCircle className="h-3 w-3" />,
      cls: "bg-classification-attention/10 text-classification-attention border-classification-attention/20",
      label: "recusou",
    },
    reminder_sent: {
      icon: <Clock className="h-3 w-3" />,
      cls: "bg-classification-attention/10 text-classification-attention border-classification-attention/20",
      label: "aguardando",
    },
    scheduled: {
      icon: <Clock className="h-3 w-3" />,
      cls: "bg-white/[0.04] text-foreground/55 border-white/[0.06]",
      label: "pendente",
    },
    paused: {
      icon: <ChevronRight className="h-3 w-3" />,
      cls: "bg-white/[0.04] text-foreground/55 border-white/[0.06]",
      label: "pausado",
    },
    cancelled: {
      icon: <XCircle className="h-3 w-3" />,
      cls: "bg-white/[0.04] text-foreground/55 border-white/[0.06]",
      label: "cancelado",
    },
  };
  const cfg = statusCfg[event.status] || statusCfg.scheduled;

  return (
    <li className="flex items-center gap-3 text-[12px] px-3 py-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
      <div className="w-12 tabular font-medium text-foreground/70">{timeStr}</div>
      <div className="flex-1 min-w-0 truncate">
        <span className="text-foreground">{event.medication_name}</span>
        <span className="text-foreground/60 ml-1.5">{event.dose}</span>
      </div>
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase tracking-wider ${cfg.cls}`}
      >
        {cfg.icon}
        {cfg.label}
      </span>
    </li>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

function formatSchedule(s: MedicationSchedule): string {
  if (s.schedule_type === "prn") return "Se necessário (sem horário fixo)";
  const times = (s.times_of_day || []).map((t) => t.slice(0, 5)).join(" · ");
  if (s.schedule_type === "fixed_weekly" && s.days_of_week) {
    const dayNames = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
    const days = s.days_of_week.map((d) => dayNames[d - 1]).join(", ");
    return `${days} · ${times}`;
  }
  return times || "Horários não definidos";
}

function groupByPeriod(events: MedicationEvent[]): Record<
  string,
  { label: string; icon: React.ReactNode; events: MedicationEvent[] }
> {
  const groups: Record<string, {
    label: string;
    icon: React.ReactNode;
    events: MedicationEvent[];
  }> = {};
  const now = new Date();
  const todayKey = now.toDateString();

  for (const e of events) {
    const d = new Date(e.scheduled_at);
    const hh = d.getHours();
    const isToday = d.toDateString() === todayKey;
    const dayPrefix = isToday
      ? "Hoje"
      : d.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "short" });

    let period: string;
    let icon: React.ReactNode;
    if (hh < 6) {
      period = "Madrugada";
      icon = <Moon className="h-3.5 w-3.5 text-foreground/60" />;
    } else if (hh < 12) {
      period = "Manhã";
      icon = <Sunrise className="h-3.5 w-3.5 text-accent-cyan" />;
    } else if (hh < 18) {
      period = "Tarde";
      icon = <Sun className="h-3.5 w-3.5 text-accent-teal" />;
    } else {
      period = "Noite";
      icon = <Sunset className="h-3.5 w-3.5 text-classification-attention" />;
    }

    const key = `${dayPrefix}::${period}`;
    const label = `${dayPrefix} · ${period}`;
    if (!groups[key]) groups[key] = { label, icon, events: [] };
    groups[key].events.push(e);
  }
  return groups;
}
