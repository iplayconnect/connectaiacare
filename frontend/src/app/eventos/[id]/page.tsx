import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowLeft,
  Bell,
  CalendarClock,
  Check,
  FileText,
  Headphones,
  Phone,
  Stethoscope,
  TrendingUp,
  UserCircle2,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { CloseEventButton } from "@/components/close-event-button";
import { api, type CareEventDetail, type EventStatus } from "@/lib/api";
import {
  CLASSIFICATION_LABELS,
  classificationTone,
  formatDateTime,
  timeAgo,
} from "@/lib/utils";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const STATUS_LABEL: Record<EventStatus, string> = {
  analyzing: "Analisando",
  awaiting_ack: "Aguardando ciência",
  pattern_analyzed: "Padrão analisado",
  escalating: "Escalando",
  awaiting_status_update: "Aguardando retorno",
  resolved: "Resolvido",
  expired: "Expirado",
};

const ROLE_LABEL: Record<string, string> = {
  central: "Central",
  nurse: "Enfermagem",
  doctor: "Médico",
  family_1: "Família · nível 1",
  family_2: "Família · nível 2",
  family_3: "Família · nível 3",
};

const CHECKIN_LABEL: Record<string, string> = {
  pattern_analysis: "Análise de padrão histórico",
  status_update: "Check-in proativo de status",
  closure_check: "Decisão de encerramento",
  post_escalation: "Escalação próximo nível",
};

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let data: CareEventDetail;
  try {
    data = await api.getEvent(id);
  } catch {
    notFound();
  }

  const { event, patient, timeline, escalations, checkins } = data;
  const tone = classificationTone(event.classification);
  const label = CLASSIFICATION_LABELS[event.classification || "routine"];
  const isResolved = event.status === "resolved" || event.status === "expired";
  const humanId = event.human_id
    ? `#${event.human_id.toString().padStart(4, "0")}`
    : "#----";
  const patientName =
    patient?.nickname || patient?.full_name || "Paciente não identificado";

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link
          href="/"
          className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar ao dashboard
        </Link>

        {!isResolved && (
          <CloseEventButton eventId={event.id} humanId={event.human_id} />
        )}
      </div>

      {/* Hero: paciente + classificação */}
      <section className="glass-card rounded-2xl p-6 md:p-7">
        <div className="flex items-start gap-5 flex-wrap">
          {/* Foto */}
          {patient?.photo_url ? (
            <Image
              src={patient.photo_url}
              alt={patientName}
              width={72}
              height={72}
              className="rounded-full object-cover w-18 h-18 ring-2 ring-white/10"
            />
          ) : (
            <div className="w-18 h-18 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
              <UserCircle2 className="h-8 w-8 text-muted-foreground" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                Evento {humanId}
              </span>
              <span className="text-muted-foreground/40">·</span>
              <span className={`text-xs font-semibold uppercase tracking-wider ${tone}`}>
                {label}
              </span>
              <span className="text-muted-foreground/40">·</span>
              <span className="text-xs text-muted-foreground">
                {STATUS_LABEL[event.status]}
              </span>
            </div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight mb-1">
              {patient?.full_name || "Paciente"}
              {patient?.nickname && patient.full_name !== patient.nickname && (
                <span className="text-muted-foreground font-normal text-xl ml-2">
                  ({patient.nickname})
                </span>
              )}
            </h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {patient?.care_unit && (
                <span className="inline-flex items-center gap-1.5">
                  <Stethoscope className="h-3.5 w-3.5" />
                  {patient.care_unit}
                </span>
              )}
              {patient?.room_number && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-muted-foreground/50">·</span>
                  Quarto {patient.room_number}
                </span>
              )}
              <span className="inline-flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5" />
                aberto {timeAgo(event.opened_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-col items-end">
            <ClassificationBadge classification={event.classification} />
          </div>
        </div>

        {/* Resumo clínico */}
        {event.summary && (
          <div className="mt-5 pt-5 border-t border-white/[0.05]">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              Resumo clínico
            </div>
            <p className="text-sm text-foreground leading-relaxed">{event.summary}</p>
            {event.reasoning && (
              <p className="text-xs text-muted-foreground mt-2 italic leading-relaxed">
                {event.reasoning}
              </p>
            )}
          </div>
        )}

        {/* Event tags */}
        {event.event_tags && event.event_tags.length > 0 && (
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <span className="text-xs uppercase tracking-wider text-muted-foreground">
              Tags:
            </span>
            {event.event_tags.map((t) => (
              <span
                key={t}
                className="px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.06] text-xs"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        {/* Closed info */}
        {isResolved && event.closed_reason && (
          <div className="mt-4 pt-4 border-t border-white/[0.05] flex items-center gap-2 text-xs">
            <Check className="h-4 w-4 text-classification-routine" />
            <span className="text-muted-foreground">
              Encerrado por <b className="text-foreground">{event.closed_by}</b> em{" "}
              {formatDateTime(event.resolved_at)} ·{" "}
              <span className="text-foreground">{event.closed_reason}</span>
            </span>
          </div>
        )}
      </section>

      {/* Grid 2 colunas */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Coluna principal — Timeline */}
        <div className="lg:col-span-2 space-y-6">
          <section className="glass-card rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-5">
              <TrendingUp className="h-4 w-4 text-accent-cyan" />
              <h2 className="font-semibold">Linha do tempo</h2>
              <span className="text-xs text-muted-foreground ml-1">
                ({timeline.length} eventos)
              </span>
            </div>

            {timeline.length === 0 ? (
              <div className="text-sm text-muted-foreground italic">
                Ainda sem eventos na timeline.
              </div>
            ) : (
              <ol className="relative border-l border-white/[0.08] ml-3 space-y-5">
                {timeline.map((item, i) => (
                  <li key={i} className="pl-5 relative">
                    <span className="absolute -left-[6px] top-1.5 w-3 h-3 rounded-full bg-background border-2 border-accent-cyan" />
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium">{item.label}</div>
                        {item.text && (
                          <div className="text-xs text-muted-foreground mt-1 leading-relaxed whitespace-pre-wrap break-words">
                            {item.text}
                          </div>
                        )}
                      </div>
                      <time className="text-xs uppercase tracking-wider text-muted-foreground whitespace-nowrap tabular">
                        {formatDateTime(item.t)}
                      </time>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>

          {/* Relatos (áudios) */}
          {data.reports.length > 0 && (
            <section className="glass-card rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Headphones className="h-4 w-4 text-accent-teal" />
                <h2 className="font-semibold">Relatos ({data.reports.length})</h2>
              </div>
              <ul className="space-y-3">
                {data.reports.map((r) => (
                  <li
                    key={r.id}
                    className="solid-card rounded-lg p-3 text-sm"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs uppercase tracking-wider text-muted-foreground">
                        {formatDateTime(r.received_at)}
                        {r.audio_duration_seconds &&
                          ` · ${r.audio_duration_seconds.toFixed(0)}s`}
                      </span>
                      <ClassificationBadge classification={r.classification} />
                    </div>
                    {r.transcription && (
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {r.transcription}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Coluna lateral — Escalations + Checkins + Patient info */}
        <div className="space-y-6">
          {/* Escalações */}
          <section className="glass-card rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Phone className="h-4 w-4 text-classification-urgent" />
              <h3 className="font-semibold text-sm">Escalações ({escalations.length})</h3>
            </div>
            {escalations.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                Nenhuma escalação disparada ainda.
              </div>
            ) : (
              <ul className="space-y-2">
                {escalations.map((e) => (
                  <li
                    key={e.id}
                    className="solid-card rounded-md p-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-semibold">
                        {ROLE_LABEL[e.target_role] || e.target_role}
                      </span>
                      <EscalationStatusBadge status={e.status} />
                    </div>
                    <div className="text-[13px] text-muted-foreground">
                      {e.target_name || e.target_phone} · {e.channel}
                    </div>
                    {e.sent_at && (
                      <div className="text-xs text-muted-foreground/70 mt-0.5">
                        enviado {timeAgo(e.sent_at)}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Check-ins agendados */}
          <section className="glass-card rounded-2xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <Bell className="h-4 w-4 text-accent-cyan" />
              <h3 className="font-semibold text-sm">Agenda ({checkins.length})</h3>
            </div>
            {checkins.length === 0 ? (
              <div className="text-xs text-muted-foreground italic">
                Sem ações agendadas.
              </div>
            ) : (
              <ul className="space-y-2">
                {checkins.map((c) => (
                  <li
                    key={c.id}
                    className="solid-card rounded-md p-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-medium">
                        {CHECKIN_LABEL[c.kind] || c.kind}
                      </span>
                      <CheckinStatusBadge status={c.status} />
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {c.sent_at
                        ? `enviado ${timeAgo(c.sent_at)}`
                        : `agendado para ${formatDateTime(c.scheduled_for)}`}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Ficha resumida do paciente */}
          {patient && (
            <section className="glass-card rounded-2xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <h3 className="font-semibold text-sm">Ficha clínica</h3>
              </div>
              <div className="text-xs space-y-2">
                {patient.conditions && patient.conditions.length > 0 && (
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                      Condições
                    </div>
                    <ul className="space-y-0.5">
                      {patient.conditions.slice(0, 5).map((c, i) => (
                        <li key={i} className="text-xs">
                          • {c.description}
                          {c.severity && (
                            <span className="text-muted-foreground ml-1">
                              ({c.severity})
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {patient.medications && patient.medications.length > 0 && (
                  <div className="pt-2 border-t border-white/[0.04]">
                    <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                      Medicações ({patient.medications.length})
                    </div>
                    <ul className="space-y-0.5">
                      {patient.medications.slice(0, 5).map((m, i) => (
                        <li key={i} className="text-xs text-muted-foreground">
                          • {m.name}
                          {m.dose && ` ${m.dose}`}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <Link
                href={`/patients/${patient.id}`}
                className="inline-flex items-center gap-1 text-xs text-accent-cyan mt-3 hover:text-accent-teal transition-colors"
              >
                Histórico completo do paciente →
              </Link>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function EscalationStatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; color: string }> = {
    queued: { label: "fila", color: "text-muted-foreground" },
    sent: { label: "enviado", color: "text-accent-cyan" },
    delivered: { label: "entregue", color: "text-accent-teal" },
    read: { label: "lido", color: "text-accent-teal" },
    responded: { label: "respondeu", color: "text-classification-routine" },
    no_answer: { label: "sem resposta", color: "text-classification-attention" },
    failed: { label: "falhou", color: "text-classification-critical" },
  };
  const c = config[status] || { label: status, color: "text-muted-foreground" };
  return (
    <span className={`text-xs uppercase font-semibold tracking-wider ${c.color}`}>
      {c.label}
    </span>
  );
}

function CheckinStatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; color: string }> = {
    scheduled: { label: "agendado", color: "text-accent-cyan" },
    sent: { label: "enviado", color: "text-accent-teal" },
    responded: { label: "respondido", color: "text-classification-routine" },
    skipped: { label: "pulado", color: "text-muted-foreground" },
    failed: { label: "falhou", color: "text-classification-critical" },
  };
  const c = config[status] || { label: status, color: "text-muted-foreground" };
  return (
    <span className={`text-xs uppercase font-semibold tracking-wider ${c.color}`}>
      {c.label}
    </span>
  );
}
