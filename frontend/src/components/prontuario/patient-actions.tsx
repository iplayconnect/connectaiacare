import Link from "next/link";
import { FileText, MessageSquare, Video } from "lucide-react";

import type { CareEvent, Patient } from "@/mocks/patients";

interface Props {
  patient: Patient;
  care_events: CareEvent[];
}

/**
 * Ações contextuais do prontuário — aparecem como CTAs no canto superior direito.
 *
 * Lógica:
 *   - Se tem care_event ativo → "Iniciar teleconsulta" (leva ao evento)
 *   - Sem care_event → "Nova teleconsulta agendada"
 *   - Sempre: "Ver histórico" + "Mandar mensagem pela Sofia"
 */
export function PatientActions({ patient, care_events }: Props) {
  const activeEvent = care_events.find(
    (e) => e.status !== "resolved" && e.status !== "expired",
  );

  return (
    <div className="flex flex-col gap-2 w-full lg:w-auto lg:min-w-[200px]">
      {/* CTA principal — Teleconsulta */}
      {activeEvent ? (
        <Link
          href={`/eventos/${activeEvent.id}`}
          className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl accent-gradient text-slate-900 font-semibold text-sm hover:shadow-[0_0_24px_rgba(49,225,255,0.35)] transition-all"
          aria-label={`Iniciar teleconsulta para o evento ativo ${activeEvent.event_type}`}
        >
          <Video className="h-4 w-4" strokeWidth={2.5} />
          Iniciar teleconsulta
        </Link>
      ) : (
        <Link
          href={`/teleconsulta?patient=${patient.id}`}
          className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl accent-gradient text-slate-900 font-semibold text-sm hover:shadow-[0_0_24px_rgba(49,225,255,0.35)] transition-all"
        >
          <Video className="h-4 w-4" strokeWidth={2.5} />
          Agendar teleconsulta
        </Link>
      )}

      {/* Ações secundárias */}
      <div className="grid grid-cols-2 gap-2">
        <SecondaryAction
          href={`/reports?patient=${patient.id}`}
          icon={<FileText className="h-3.5 w-3.5" />}
          label="Histórico"
        />
        <SecondaryAction
          href={`/demo/onboarding`}
          icon={<MessageSquare className="h-3.5 w-3.5" />}
          label="Sofia"
        />
      </div>

      {/* Se tem evento ativo, chip de alerta */}
      {activeEvent && (
        <div className="mt-1 inline-flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[10px] uppercase tracking-wider font-semibold border border-classification-attention/35 bg-classification-attention/8 text-classification-attention">
          <span className="w-1.5 h-1.5 rounded-full bg-classification-attention animate-pulse" />
          Evento #{activeEvent.human_id.toString().padStart(4, "0")} ativo
        </div>
      )}
    </div>
  );
}

function SecondaryAction({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-lg text-xs font-medium border border-white/10 bg-white/[0.03] text-foreground/85 hover:bg-white/[0.07] hover:border-accent-cyan/30 hover:text-accent-cyan transition-all"
    >
      {icon}
      {label}
    </Link>
  );
}
