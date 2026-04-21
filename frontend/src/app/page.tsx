import {
  Activity,
  AlertTriangle,
  PhoneCall,
  Sparkles,
  Zap,
} from "lucide-react";

import { LiveEventsFeed } from "@/components/live-events-feed";
import { api, type CareEventSummary } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

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

      {/* Live feed de eventos ativos — client component com polling */}
      <LiveEventsFeed initialEvents={events} />
    </div>
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
          <span className="text-xs uppercase tracking-wider font-semibold text-classification-urgent animate-pulse-soft">
            • ativo
          </span>
        )}
      </div>
      <div className="tabular text-3xl font-bold leading-none mb-1">{value}</div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="text-xs text-muted-foreground/70 mt-0.5">{hint}</div>
    </div>
  );
}
