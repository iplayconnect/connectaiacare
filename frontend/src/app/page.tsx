import { AlertTriangle, Clock, Sparkles, UsersRound } from "lucide-react";

import { EventsDistribution } from "@/components/events-distribution";
import { LiveEventsFeed } from "@/components/live-events-feed";
import { SlaResponseChart } from "@/components/sla-response-chart";
import { api, type CareEventSummary } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function DashboardPage() {
  let events: CareEventSummary[] = [];
  let patientsCount = 0;
  let apiError = false;
  try {
    events = await api.listActiveEvents();
    try {
      const resp = await api.listPatients();
      patientsCount = (resp.patients || []).filter((p) => p.active).length;
    } catch {
      patientsCount = 0;
    }
  } catch {
    apiError = true;
  }

  if (apiError) {
    return (
      <div className="glass-card rounded-2xl p-10 text-center max-w-md mx-auto mt-12">
        <AlertTriangle className="h-10 w-10 text-classification-attention mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-1">API indisponível</h2>
        <p className="text-sm text-muted-foreground">
          Verifique se o backend está rodando em demo.connectaia.com.br.
        </p>
      </div>
    );
  }

  // KPIs
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
  const criticalOrUrgent = critical + urgent;

  // Tempo médio (placeholder — será endpoint real no futuro)
  const avgResponseTime = "38s";

  return (
    <div className="space-y-8 max-w-[1400px]">
      {/* ════════════════ Hero ════════════════ */}
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Dashboard clínico · ao vivo
            </span>
          </div>
          <h1 className="text-[2.25rem] md:text-[2.75rem] font-bold tracking-tight leading-[1.1]">
            Visão em <span className="accent-gradient-text">tempo real</span>
          </h1>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
            Equipe de enfermagem e corpo médico acompanham pacientes com insights
            estruturados de cada relato processado pela Íris.
          </p>
        </div>

        {criticalOrUrgent > 0 && (
          <div className="glass-card rounded-xl px-5 py-4 border-classification-critical/30 glow-critical">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 bg-classification-critical rounded-full opacity-30 blur animate-pulse-soft" />
                <AlertTriangle className="relative h-5 w-5 text-classification-critical" />
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-wider text-classification-critical">
                  Atenção imediata
                </div>
                <div className="text-sm text-foreground mt-0.5">
                  <span className="tabular font-bold text-lg">{criticalOrUrgent}</span>{" "}
                  {criticalOrUrgent === 1 ? "alerta pendente" : "alertas pendentes"}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ════════════════ KPIs ════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard
          label="Pacientes ativos"
          value={patientsCount}
          hint="em acompanhamento"
          icon={<UsersRound className="h-4 w-4" />}
          tone="cyan"
        />
        <KPICard
          label="Relatos hoje"
          value={events.length}
          hint="análises processadas"
          icon={<Sparkles className="h-4 w-4" />}
          tone="teal"
        />
        <KPICard
          label="Urgente / Crítico"
          value={criticalOrUrgent}
          hint="requer ação"
          icon={<AlertTriangle className="h-4 w-4" />}
          tone="critical"
          alert
        />
        <KPICard
          label="Tempo médio de resposta"
          value={avgResponseTime}
          hint="áudio → análise"
          icon={<Clock className="h-4 w-4" />}
          tone="cyan"
          isText
        />
      </div>

      {/* ════════════════ Distribuição + SLA (2 colunas) ════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EventsDistribution
          counts={{ routine, attention, urgent, critical }}
          total={events.length}
        />
        <SlaResponseChart
          counts={{ routine, attention, urgent, critical }}
          median={avgResponseTime}
          familyCalls={escalating}
        />
      </div>

      {/* ════════════════ Live feed de eventos (polling + anim + countdown) ════════════════ */}
      <LiveEventsFeed initialEvents={events} />
    </div>
  );
}

// ---------------------------------------------------------------
// KPICard — cartão denso com micro-interação hover
// ---------------------------------------------------------------
function KPICard({
  label,
  value,
  hint,
  icon,
  tone,
  alert = false,
  isText = false,
}: {
  label: string;
  value: number | string;
  hint: string;
  icon: React.ReactNode;
  tone: "cyan" | "teal" | "critical" | "attention";
  alert?: boolean;
  isText?: boolean;
}) {
  const toneStyles: Record<string, string> = {
    cyan: "border-accent-cyan/20 text-accent-cyan",
    teal: "border-accent-teal/20 text-accent-teal",
    critical: "border-classification-critical/25 text-classification-critical",
    attention: "border-classification-attention/25 text-classification-attention",
  };

  return (
    <div
      className={`
        glass-card rounded-xl p-4 relative overflow-hidden
        transition-all hover:border-white/[0.12] hover:translate-y-[-1px]
        ${alert && typeof value === "number" && value > 0 ? "glow-critical border-classification-critical/30" : ""}
      `}
    >
      {/* accent top border quando alert */}
      {alert && typeof value === "number" && value > 0 && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-classification-critical to-transparent animate-pulse-soft" />
      )}

      <div className="flex items-start justify-between mb-3">
        <div
          className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border bg-white/[0.02] ${toneStyles[tone]}`}
        >
          {icon}
        </div>
        {alert && typeof value === "number" && value > 0 && (
          <span className="text-[9px] uppercase tracking-wider font-bold text-classification-critical animate-pulse-soft">
            • ATENÇÃO
          </span>
        )}
      </div>

      <div className={`tabular ${isText ? "text-2xl" : "text-[2rem]"} font-bold leading-none mb-1 text-foreground`}>
        {value}
      </div>
      <div className="text-xs font-medium text-foreground/80 mt-1">{label}</div>
      <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>
    </div>
  );
}
