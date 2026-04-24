import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Calendar,
  Clock,
  Stethoscope,
  Video,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// /teleconsulta — Dashboard de teleconsultas
//
// Em produção: vem de GET /api/teleconsultas com filtros.
// MVP demo: lista mockada com 3 estados (agendada, em andamento, finalizada).
// ═══════════════════════════════════════════════════════════════════

const MOCK_CONSULTAS = [
  {
    id: "tc-001",
    patient_name: "Maria Aparecida Santos",
    patient_nickname: "Dona Maria",
    doctor_name: "Dra. Ana Silva",
    doctor_crm: "CRM/RS 12345",
    specialty: "Geriatria",
    scheduled_at: "2026-04-24T14:30:00Z",
    duration_min: 30,
    status: "agendada",
    reason: "Hipertensão descontrolada - revisão de Losartana",
    care_event_id: "ce-001",
  },
  {
    id: "tc-002",
    patient_name: "Antônio Ferreira da Silva",
    patient_nickname: "Seu Antônio",
    doctor_name: "Dra. Ana Silva",
    doctor_crm: "CRM/RS 12345",
    specialty: "Geriatria",
    scheduled_at: "2026-04-23T19:50:00Z",
    duration_min: 45,
    status: "em_andamento",
    reason: "Queda - avaliação pós-fratura",
    care_event_id: "ce-101",
  },
  {
    id: "tc-003",
    patient_name: "Lúcia Helena Oliveira",
    patient_nickname: "Dona Lúcia",
    doctor_name: "Dr. Carlos Mendes",
    doctor_crm: "CRM/SP 67890",
    specialty: "Neurologia",
    scheduled_at: "2026-04-23T10:00:00Z",
    duration_min: 40,
    status: "finalizada",
    reason: "Avaliação Alzheimer - progressão",
    soap_available: true,
  },
];

export default function TeleconsultaPage() {
  const scheduled = MOCK_CONSULTAS.filter((c) => c.status === "agendada");
  const inProgress = MOCK_CONSULTAS.filter((c) => c.status === "em_andamento");
  const finalized = MOCK_CONSULTAS.filter((c) => c.status === "finalizada");

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
              Consultas por vídeo com IA de apoio clínico (CFM 2.314/2022)
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <StatBadge label="Agendadas" value={scheduled.length} color="cyan" />
          <StatBadge label="Em andamento" value={inProgress.length} color="attention" />
          <StatBadge label="Finalizadas 7d" value={finalized.length} color="routine" />
        </div>
      </header>

      {/* Em andamento — CTA grande */}
      {inProgress.length > 0 && (
        <section>
          <SectionHeader
            icon={<Activity className="h-4 w-4" />}
            label="Em andamento agora"
            color="attention"
          />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
            {inProgress.map((c) => (
              <ConsultaCard key={c.id} consulta={c} />
            ))}
          </div>
        </section>
      )}

      {/* Agendadas */}
      <section>
        <SectionHeader
          icon={<Calendar className="h-4 w-4" />}
          label="Próximas"
          color="cyan"
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          {scheduled.length === 0 ? (
            <div className="solid-card rounded-xl p-6 text-center text-muted-foreground col-span-full">
              Nenhuma consulta agendada.
            </div>
          ) : (
            scheduled.map((c) => <ConsultaCard key={c.id} consulta={c} />)
          )}
        </div>
      </section>

      {/* Finalizadas */}
      <section>
        <SectionHeader
          icon={<Stethoscope className="h-4 w-4" />}
          label="Finalizadas recentemente"
          color="routine"
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          {finalized.map((c) => (
            <ConsultaCard key={c.id} consulta={c} />
          ))}
        </div>
      </section>
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
    attention: "border-classification-attention/30 bg-classification-attention/5 text-classification-attention",
    routine: "border-classification-routine/30 bg-classification-routine/5 text-classification-routine",
  };
  return (
    <div className={`px-4 py-2 rounded-xl border ${colorMap[color]} text-center min-w-[100px]`}>
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
    <h2 className={`flex items-center gap-2 text-sm font-semibold uppercase tracking-wider ${colorMap[color]}`}>
      {icon}
      {label}
    </h2>
  );
}

function ConsultaCard({ consulta }: { consulta: (typeof MOCK_CONSULTAS)[0] }) {
  const date = new Date(consulta.scheduled_at);
  const dateStr = date.toLocaleString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  const isInProgress = consulta.status === "em_andamento";
  const isFinalized = consulta.status === "finalizada";
  const href = isInProgress
    ? `/consulta/${consulta.id}`
    : isFinalized && "soap_available" in consulta && consulta.soap_available
      ? `/consulta/${consulta.id}/finalizada`
      : `/teleconsulta/${consulta.id}`;

  return (
    <Link
      href={href}
      className={`
        solid-card rounded-xl p-4 block transition-all group
        ${isInProgress ? "border-classification-attention/35 bg-classification-attention/5 hover:shadow-[0_0_20px_rgba(251,191,36,0.15)]" : ""}
      `}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm truncate">
            {consulta.patient_nickname || consulta.patient_name}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {consulta.doctor_name} · {consulta.specialty}
          </div>
        </div>

        {isInProgress && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider font-semibold bg-classification-attention/15 text-classification-attention border border-classification-attention/30">
            <span className="w-1.5 h-1.5 rounded-full bg-classification-attention animate-pulse" />
            ao vivo
          </span>
        )}
      </div>

      <p className="text-xs text-muted-foreground mb-3 line-clamp-2">
        {consulta.reason}
      </p>

      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground tabular">
          <Clock className="h-3 w-3" />
          {dateStr} · {consulta.duration_min}min
        </div>
        <ArrowRight className="h-3.5 w-3.5 text-accent-cyan opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </Link>
  );
}
