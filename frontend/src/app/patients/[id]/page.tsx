import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Phone, UserRound } from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { PatientVitalsSection } from "@/components/patient-vitals-section";
import { api, type CareEventSummary } from "@/lib/api";
import { calcAge, formatDateTime, timeAgo } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// ═══════════════════════════════════════════════════════════════
// Prontuário Longitudinal — ficha completa do paciente
// Inspiração: mockup Claude Design + refinamentos
// ═══════════════════════════════════════════════════════════════

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let patient;
  let reports;
  let events: CareEventSummary[] = [];

  try {
    const [patientResp, eventsResp] = await Promise.all([
      api.getPatient(id),
      api.listPatientEvents(id, true).catch(() => [] as CareEventSummary[]),
    ]);
    patient = patientResp.patient;
    reports = patientResp.reports || [];
    events = eventsResp;
  } catch {
    notFound();
  }

  const age = calcAge(patient.birth_date);
  const activeEvents = events.filter(
    (e) => e.status !== "resolved" && e.status !== "expired",
  );

  // Responsável (primário)
  const responsible =
    (patient.responsible as any) && (patient.responsible as any).family?.[0]
      ? (patient.responsible as any).family[0]
      : patient.responsible &&
        ("phone" in patient.responsible || "name" in patient.responsible)
      ? patient.responsible
      : null;

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* ═══════════════ Header do paciente ═══════════════ */}
      <header className="glass-card rounded-2xl p-6">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          {/* Avatar + identidade */}
          <div className="flex items-start gap-5 flex-1 min-w-0">
            {patient.photo_url ? (
              <Image
                src={patient.photo_url}
                alt={patient.full_name}
                width={72}
                height={72}
                className="rounded-2xl object-cover w-[72px] h-[72px] ring-2 ring-white/10"
              />
            ) : (
              <div className="w-[72px] h-[72px] rounded-2xl bg-gradient-to-br from-accent-cyan/20 to-accent-teal/20 border border-white/10 flex items-center justify-center text-lg font-bold tracking-wider">
                {initials(patient.full_name)}
              </div>
            )}

            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-3 flex-wrap mb-1">
                <h1 className="text-2xl md:text-[1.75rem] font-bold tracking-tight">
                  {patient.full_name}
                </h1>
                {age && (
                  <span className="text-sm text-muted-foreground tabular">
                    {age} anos
                  </span>
                )}
                {activeEvents.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-wider font-semibold text-classification-urgent">
                    <span className="w-1.5 h-1.5 rounded-full bg-classification-urgent animate-pulse-soft" />
                    {activeEvents.length} evento{activeEvents.length > 1 ? "s" : ""} ativo{activeEvents.length > 1 ? "s" : ""}
                  </span>
                )}
              </div>

              <div className="text-xs text-muted-foreground mb-3">
                {patient.care_unit && <span>{patient.care_unit}</span>}
                {patient.room_number && (
                  <>
                    <span className="mx-2 opacity-40">·</span>
                    <span>Quarto {patient.room_number}</span>
                  </>
                )}
                {patient.nickname && patient.nickname !== patient.full_name && (
                  <>
                    <span className="mx-2 opacity-40">·</span>
                    <span>Conhecid{patient.gender === "F" ? "a" : "o"} como {patient.nickname}</span>
                  </>
                )}
              </div>

              {/* Tags condições */}
              {patient.conditions && patient.conditions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {patient.conditions.slice(0, 6).map((c, i) => (
                    <span
                      key={i}
                      className="text-[11px] font-medium px-2 py-1 rounded-md bg-accent-cyan/5 border border-accent-cyan/20 text-accent-cyan/90"
                      title={c.severity ? `${c.description} (${c.severity})` : c.description}
                    >
                      {c.description}
                    </span>
                  ))}
                  {patient.conditions.length > 6 && (
                    <span className="text-[11px] text-muted-foreground px-2 py-1">
                      +{patient.conditions.length - 6} mais
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Responsável (card direita) */}
          {responsible && (
            <div className="text-right bg-white/[0.02] rounded-xl p-4 border border-white/[0.04] min-w-[200px]">
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-1">
                Responsável
              </div>
              <div className="font-semibold text-sm mb-0.5">
                {responsible.name || "—"}
                {responsible.relationship && (
                  <span className="text-xs text-muted-foreground font-normal ml-1">
                    ({responsible.relationship})
                  </span>
                )}
              </div>
              {responsible.phone && (
                <div className="flex items-center justify-end gap-1.5 text-xs text-accent-teal tabular font-mono mt-1">
                  <Phone className="h-3 w-3" />
                  {formatPhone(responsible.phone)}
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* ═══════════════ Sinais Vitais (cards com sparkline) ═══════════════ */}
      <PatientVitalsSection patientId={id} />

      {/* ═══════════════ Eventos ativos (se houver) ═══════════════ */}
      {activeEvents.length > 0 && (
        <section className="glass-card rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.05] flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Eventos em andamento · Íris
              </div>
              <h2 className="text-base font-semibold mt-0.5">
                {activeEvents.length} evento{activeEvents.length > 1 ? "s" : ""} ativo{activeEvents.length > 1 ? "s" : ""}
              </h2>
            </div>
          </div>
          <ul className="divide-y divide-white/[0.04]">
            {activeEvents.map((e) => (
              <li key={e.id}>
                <Link
                  href={`/eventos/${e.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
                        #{String(e.human_id || 0).padStart(4, "0")}
                      </span>
                      {e.event_type && (
                        <span className="text-xs uppercase tracking-wider text-muted-foreground">
                          · {e.event_type}
                        </span>
                      )}
                    </div>
                    <p className="text-sm group-hover:text-accent-cyan transition-colors truncate">
                      {e.summary || "Em análise…"}
                    </p>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      aberto {timeAgo(e.opened_at)}
                    </div>
                  </div>
                  <ClassificationBadge classification={e.classification} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ═══════════════ Histórico de relatos ═══════════════ */}
      <section className="glass-card rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.05]">
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Cuidador · WhatsApp · Transcrição + IA
          </div>
          <div className="flex items-baseline justify-between mt-0.5">
            <h2 className="text-base font-semibold">Relatos recentes</h2>
            <span className="text-xs text-muted-foreground tabular">
              {reports.length} {reports.length === 1 ? "relato" : "relatos"}
            </span>
          </div>
        </div>

        {reports.length === 0 ? (
          <div className="p-10 text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-white/[0.03] border border-white/[0.06] mb-3">
              <UserRound className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              Nenhum relato registrado ainda para {patient.nickname || patient.full_name}.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {reports.slice(0, 10).map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-start gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors group"
                >
                  <div className="text-[10px] text-muted-foreground tabular font-mono min-w-[56px] text-right mt-1 leading-tight">
                    {formatDateShort(r.received_at)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <ClassificationBadge classification={r.classification} compact />
                      {r.caregiver_name_claimed && (
                        <span className="text-[11px] text-muted-foreground">
                          · {r.caregiver_name_claimed}
                        </span>
                      )}
                    </div>
                    <p className="text-[13px] text-foreground/90 group-hover:text-accent-cyan transition-colors line-clamp-2">
                      {r.analysis?.summary ||
                        r.transcription?.slice(0, 180) ||
                        "Aguardando análise…"}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// Helpers
function initials(name: string): string {
  return name
    .split(" ")
    .filter((n) => n.length > 1)
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();
}

function formatPhone(phone: string): string {
  const d = phone.replace(/\D/g, "");
  if (d.length === 13 && d.startsWith("55")) {
    return `+55 ${d.slice(2, 4)} ${d.slice(4, 9)}-${d.slice(9)}`;
  }
  if (d.length === 11) {
    return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  }
  return phone;
}

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d
    .toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
    .replace(", ", "\n");
}
