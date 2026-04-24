import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Calendar,
  Clock,
  Plus,
  Stethoscope,
  Video,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// /teleconsulta — Dashboard de teleconsultas (dados reais)
//
// Lista GET /api/teleconsulta que deriva de aia_health_teleconsultations.
// Inclui agendamentos via /teleconsulta/agendar + os abertos por
// care_events urgent (via start-from-event).
// ═══════════════════════════════════════════════════════════════════

export const dynamic = "force-dynamic";
export const revalidate = 0;

interface Teleconsulta {
  id: string;
  human_id?: number;
  state: "scheduling" | "active" | "documentation" | "signed" | "closed" | string;
  room_name: string;
  doctor_name?: string | null;
  doctor_crm?: string | null;
  specialty?: string | null;
  reason?: string | null;
  duration_min?: number | null;
  scheduled_for?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number | null;
  has_soap?: boolean;
  signed_at?: string | null;
  care_event_id?: string | null;
  patient: {
    id: string | null;
    name: string | null;
    nickname: string | null;
    unit: string | null;
    room: string | null;
  };
}

async function fetchTeleconsultas(): Promise<Teleconsulta[]> {
  const base =
    typeof window === "undefined"
      ? process.env.INTERNAL_API_URL || "http://api:5055"
      : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";
  try {
    const res = await fetch(`${base}/api/teleconsulta`, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return data.teleconsultas || [];
  } catch {
    return [];
  }
}

export default async function TeleconsultaPage() {
  const all = await fetchTeleconsultas();

  const active = all.filter((t) => t.state === "active");
  const scheduled = all.filter((t) => t.state === "scheduling");
  const finalized = all.filter(
    (t) => t.state === "documentation" || t.state === "signed" || t.state === "closed",
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-fade-up">
      {/* Header */}
      <header className="glass-card rounded-2xl p-6 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl accent-gradient flex items-center justify-center">
            <Video className="h-6 w-6 text-slate-900" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Teleconsultas</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Consultas por vídeo · apoio clínico IA · CFM 2.314/2022
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            <StatBadge label="Ao vivo" value={active.length} color="attention" />
            <StatBadge label="Agendadas" value={scheduled.length} color="cyan" />
            <StatBadge label="Finalizadas" value={finalized.length} color="routine" />
          </div>
          <Link
            href="/patients"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl accent-gradient text-slate-900 font-semibold text-sm hover:shadow-[0_0_24px_rgba(49,225,255,0.35)] transition-all"
          >
            <Plus className="h-4 w-4" strokeWidth={2.5} />
            Agendar nova
          </Link>
        </div>
      </header>

      {all.length === 0 && (
        <div className="glass-card rounded-2xl p-10 text-center">
          <Video className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
          <div className="text-base font-semibold">Nenhuma teleconsulta registrada</div>
          <p className="text-sm text-muted-foreground mt-1">
            Agende uma pelo prontuário de um paciente.
          </p>
          <Link
            href="/patients"
            className="inline-flex items-center gap-2 mt-5 px-5 py-2.5 rounded-xl accent-gradient text-slate-900 font-semibold text-sm"
          >
            Ir para pacientes
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {/* Em andamento */}
      {active.length > 0 && (
        <section>
          <SectionHeader
            icon={<Activity className="h-4 w-4" />}
            label="Em andamento"
            color="attention"
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
            {active.map((tc) => (
              <TeleconsultaCard key={tc.id} tc={tc} />
            ))}
          </div>
        </section>
      )}

      {/* Agendadas */}
      {scheduled.length > 0 && (
        <section>
          <SectionHeader
            icon={<Calendar className="h-4 w-4" />}
            label="Próximas agendadas"
            color="cyan"
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
            {scheduled.map((tc) => (
              <TeleconsultaCard key={tc.id} tc={tc} />
            ))}
          </div>
        </section>
      )}

      {/* Finalizadas */}
      {finalized.length > 0 && (
        <section>
          <SectionHeader
            icon={<Stethoscope className="h-4 w-4" />}
            label="Finalizadas recentemente"
            color="routine"
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
            {finalized.map((tc) => (
              <TeleconsultaCard key={tc.id} tc={tc} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Components
// ══════════════════════════════════════════════════════════════════

function StatBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: "cyan" | "attention" | "routine";
}) {
  const colorMap = {
    cyan: "border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan",
    attention:
      "border-classification-attention/30 bg-classification-attention/5 text-classification-attention",
    routine:
      "border-classification-routine/30 bg-classification-routine/5 text-classification-routine",
  };
  return (
    <div
      className={`px-4 py-2 rounded-xl border ${colorMap[color]} text-center min-w-[85px]`}
    >
      <div className="text-2xl font-bold tabular leading-none">{value}</div>
      <div className="text-[10px] uppercase tracking-wider mt-1 opacity-80">
        {label}
      </div>
    </div>
  );
}

function SectionHeader({
  icon,
  label,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  color: "cyan" | "attention" | "routine";
}) {
  const colorMap = {
    cyan: "text-accent-cyan",
    attention: "text-classification-attention",
    routine: "text-classification-routine",
  };
  return (
    <h2
      className={`flex items-center gap-2 text-sm font-semibold uppercase tracking-wider ${colorMap[color]}`}
    >
      {icon}
      {label}
    </h2>
  );
}

function TeleconsultaCard({ tc }: { tc: Teleconsulta }) {
  const dateSource = tc.scheduled_for || tc.started_at || null;
  const dateStr = dateSource
    ? new Date(dateSource).toLocaleString("pt-BR", {
        weekday: "short",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const isActive = tc.state === "active";
  const hasDoc = tc.state === "documentation" || tc.has_soap;
  const isSigned = tc.state === "signed";

  let href: string;
  if (isActive && tc.room_name) {
    href = `/consulta/${tc.room_name}?tc=${tc.id}&role=doctor`;
  } else if (hasDoc || isSigned) {
    href = `/teleconsulta/${tc.id}/documentacao`;
  } else {
    href = `/consulta/${tc.room_name}?tc=${tc.id}&role=doctor`;
  }

  const patientName = tc.patient.nickname || tc.patient.name || "Paciente";
  const durationLabel = tc.duration_seconds
    ? `${Math.floor(tc.duration_seconds / 60)}min ${tc.duration_seconds % 60}s`
    : tc.duration_min
      ? `${tc.duration_min}min`
      : null;

  return (
    <Link
      href={href}
      className={`
        solid-card rounded-xl p-4 block transition-all group
        ${isActive ? "border-classification-attention/35 bg-classification-attention/5 hover:shadow-[0_0_20px_rgba(251,191,36,0.15)]" : ""}
        ${isSigned ? "opacity-75" : ""}
      `}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm truncate">
            {patientName}
            {tc.human_id && (
              <span className="text-muted-foreground font-normal ml-2 text-[11px] tabular">
                #{String(tc.human_id).padStart(4, "0")}
              </span>
            )}
          </div>
          {(tc.doctor_name || tc.specialty) && (
            <div className="text-[11px] text-muted-foreground">
              {tc.doctor_name}
              {tc.specialty && ` · ${tc.specialty}`}
            </div>
          )}
        </div>

        <StateBadge state={tc.state} />
      </div>

      {tc.reason && (
        <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{tc.reason}</p>
      )}

      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground tabular">
          <Clock className="h-3 w-3" />
          {dateStr}
          {durationLabel && ` · ${durationLabel}`}
        </div>
        <ArrowRight className="h-3.5 w-3.5 text-accent-cyan opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </Link>
  );
}

function StateBadge({ state }: { state: string }) {
  const styles: Record<string, { bg: string; text: string; label: string; pulse?: boolean }> = {
    active: {
      bg: "bg-classification-attention/15 border border-classification-attention/30",
      text: "text-classification-attention",
      label: "Ao vivo",
      pulse: true,
    },
    scheduling: {
      bg: "bg-accent-cyan/10 border border-accent-cyan/30",
      text: "text-accent-cyan",
      label: "Agendada",
    },
    documentation: {
      bg: "bg-accent-teal/10 border border-accent-teal/30",
      text: "text-accent-teal",
      label: "Em documentação",
    },
    signed: {
      bg: "bg-classification-routine/10 border border-classification-routine/30",
      text: "text-classification-routine",
      label: "Assinada",
    },
    closed: {
      bg: "bg-white/5 border border-white/10",
      text: "text-muted-foreground",
      label: "Encerrada",
    },
  };

  const s = styles[state] || styles.closed;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider font-semibold ${s.bg} ${s.text}`}
    >
      {s.pulse && (
        <span className="w-1.5 h-1.5 rounded-full bg-classification-attention animate-pulse" />
      )}
      {s.label}
    </span>
  );
}
