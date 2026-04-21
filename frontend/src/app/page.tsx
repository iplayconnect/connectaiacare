import Image from "next/image";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Clock,
  HeartPulse,
  PhoneCall,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { api, type CareEventSummary, type EventStatus } from "@/lib/api";
import {
  CLASSIFICATION_LABELS,
  classificationTone,
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

const STATUS_DOT: Record<EventStatus, string> = {
  analyzing: "bg-accent-cyan animate-pulse-soft",
  awaiting_ack: "bg-accent-teal animate-pulse-soft",
  pattern_analyzed: "bg-accent-teal",
  escalating: "bg-classification-urgent animate-pulse-glow",
  awaiting_status_update: "bg-classification-attention animate-pulse-soft",
  resolved: "bg-classification-routine",
  expired: "bg-muted-foreground",
};

const RANK: Record<string, number> = { critical: 0, urgent: 1, attention: 2, routine: 3 };

export default async function DashboardPage() {
  let events: CareEventSummary[] = [];
  let apiError = false;
  try {
    events = await api.listActiveEvents();
  } catch {
    apiError = true;
  }

  if (apiError) {
    return (
      <div className="glass-card rounded-2xl p-10 text-center max-w-md mx-auto">
        <AlertTriangle className="h-10 w-10 text-classification-attention mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-1">API indisponível</h2>
        <p className="text-sm text-muted-foreground">
          Verifique se o backend está rodando em demo.connectaia.com.br.
        </p>
      </div>
    );
  }

  // Ordena por classificação (critical → routine) e mais recente primeiro
  events.sort((a, b) => {
    const ra = RANK[a.classification || "routine"] ?? 9;
    const rb = RANK[b.classification || "routine"] ?? 9;
    if (ra !== rb) return ra - rb;
    return (b.opened_at || "").localeCompare(a.opened_at || "");
  });

  const byClass = events.reduce<Record<string, number>>((acc, e) => {
    const c = e.classification || "routine";
    acc[c] = (acc[c] || 0) + 1;
    return acc;
  }, {});

  const critical = byClass.critical || 0;
  const urgent = byClass.urgent || 0;
  const attention = byClass.attention || 0;
  const routine = byClass.routine || 0;
  const escalating = events.filter((e) => e.status === "escalating").length;
  const total = events.length;

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Centro de operação · ao vivo
            </span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
            <span className="accent-gradient-text">
              {total} {total === 1 ? "evento ativo" : "eventos ativos"}
            </span>
            {" "}neste momento
          </h1>
          <p className="text-muted-foreground mt-1 max-w-xl">
            Cada evento representa um ciclo de cuidado em andamento — do relato
            inicial do cuidador até o encerramento categorizado.
          </p>
        </div>

        {(critical + urgent) > 0 && (
          <div className="glass-card rounded-xl px-5 py-4 border-classification-urgent/40 glow-critical">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 bg-classification-critical rounded-full opacity-30 blur animate-pulse-soft" />
                <AlertTriangle className="relative h-5 w-5 text-classification-critical" />
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-classification-urgent">
                  Atenção imediata
                </div>
                <div className="text-sm text-foreground mt-0.5">
                  <span className="tabular font-bold text-lg">
                    {critical + urgent}
                  </span>{" "}
                  {critical + urgent === 1
                    ? "cuidado urgente"
                    : "cuidados urgentes"}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <KPICard
          icon={<AlertTriangle className="h-5 w-5" />}
          iconBg="bg-classification-critical/10 text-classification-critical border-classification-critical/30"
          label="Críticos"
          value={critical}
          hint="acionamento imediato"
          highlight={critical > 0}
        />
        <KPICard
          icon={<Zap className="h-5 w-5" />}
          iconBg="bg-classification-urgent/10 text-classification-urgent border-classification-urgent/30"
          label="Urgentes"
          value={urgent}
          hint="próximas horas"
          highlight={urgent > 0}
        />
        <KPICard
          icon={<Activity className="h-5 w-5" />}
          iconBg="bg-classification-attention/10 text-classification-attention border-classification-attention/30"
          label="Atenção"
          value={attention}
          hint="observar no plantão"
        />
        <KPICard
          icon={<PhoneCall className="h-5 w-5" />}
          iconBg="bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30"
          label="Escalando"
          value={escalating}
          hint="cascata em execução"
          highlight={escalating > 0}
        />
      </div>

      {/* Live feed de eventos ativos */}
      <section className="glass-card rounded-2xl overflow-hidden">
        <div className="p-6 border-b border-white/[0.05] flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Eventos ativos</h2>
            <p className="text-xs text-muted-foreground">
              Priorizados por classificação · atualização automática
            </p>
          </div>
          <Link
            href="/patients"
            className="text-xs font-medium text-accent-cyan hover:text-accent-teal transition-colors flex items-center gap-1"
          >
            Todos os pacientes <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>

        <ul className="divide-y divide-white/[0.04]">
          {events.length === 0 ? (
            <EmptyState routineCount={routine} />
          ) : (
            events.map((e) => <EventListItem key={e.id} event={e} />)
          )}
        </ul>
      </section>
    </div>
  );
}

// ----------------------------------------------------------------
// Componentes internos
// ----------------------------------------------------------------
function EventListItem({ event }: { event: CareEventSummary }) {
  const tone = classificationTone(event.classification);
  const label = CLASSIFICATION_LABELS[event.classification || "routine"];
  const status = event.status;
  const dot = STATUS_DOT[status];
  const statusLabel = STATUS_LABEL[status];
  const humanId = event.human_id
    ? `#${event.human_id.toString().padStart(4, "0")}`
    : "#----";
  const patient = event.patient_nickname || event.patient_name || "Paciente";

  return (
    <li>
      <Link
        href={`/eventos/${event.id}`}
        className="flex items-center gap-4 p-5 hover:bg-white/[0.02] transition-colors group"
      >
        {/* Foto */}
        {event.patient_photo ? (
          <div className="relative">
            <Image
              src={event.patient_photo}
              alt={patient}
              width={52}
              height={52}
              className="rounded-full object-cover w-13 h-13 ring-1 ring-white/10"
            />
            {event.classification === "critical" && (
              <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-classification-critical border-2 border-background animate-pulse-glow" />
            )}
          </div>
        ) : (
          <div className="w-13 h-13 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
            <Users className="h-5 w-5 text-muted-foreground" />
          </div>
        )}

        {/* Conteúdo */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
              {humanId}
            </span>
            <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
              {patient}
            </h3>
            {event.patient_care_unit && (
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground hidden md:inline">
                · {event.patient_care_unit}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground truncate mb-1.5">
            {event.summary || "Análise em andamento…"}
          </p>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground/90 flex-wrap">
            <span className="inline-flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
              {statusLabel}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {timeAgo(event.opened_at)}
            </span>
            {event.event_tags && event.event_tags.length > 0 && (
              <span className="inline-flex items-center gap-1 flex-wrap">
                {event.event_tags.slice(0, 3).map((t) => (
                  <span
                    key={t}
                    className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.05] text-[10px]"
                  >
                    {t}
                  </span>
                ))}
              </span>
            )}
          </div>
        </div>

        {/* Classificação */}
        <div className="text-right flex flex-col items-end gap-1.5">
          <ClassificationBadge classification={event.classification} />
          <span className={`text-[10px] uppercase tracking-wider font-semibold ${tone}`}>
            {label}
          </span>
        </div>
      </Link>
    </li>
  );
}

function EmptyState({ routineCount }: { routineCount: number }) {
  return (
    <li className="p-12 text-center">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.03] border border-white/[0.06] mb-4">
        <HeartPulse className="h-6 w-6 text-accent-teal" />
      </div>
      <h3 className="font-medium mb-1">Nenhum evento em andamento</h3>
      <p className="text-sm text-muted-foreground max-w-sm mx-auto">
        {routineCount > 0
          ? `${routineCount} evento(s) de rotina já encerrado(s) nas últimas 24h.`
          : "Quando um cuidador enviar um áudio pelo WhatsApp, o evento aparece aqui em tempo real."}
      </p>
    </li>
  );
}

function KPICard({
  icon,
  iconBg,
  label,
  value,
  hint,
  highlight = false,
}: {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: number;
  hint: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`glass-card rounded-xl p-5 ${
        highlight ? "border-classification-urgent/40 glow-critical" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-lg border ${iconBg}`}>{icon}</div>
        {highlight && value > 0 && (
          <span className="text-[10px] uppercase tracking-wider font-semibold text-classification-urgent animate-pulse-soft">
            • ativo
          </span>
        )}
      </div>
      <div className="tabular text-3xl font-bold leading-none mb-1">{value}</div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</div>
    </div>
  );
}
