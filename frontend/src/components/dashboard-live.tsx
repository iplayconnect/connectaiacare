"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Clock, Sparkles, UsersRound } from "lucide-react";

import { EventsDistribution } from "@/components/events-distribution";
import { LiveEventsFeed } from "@/components/live-events-feed";
import { SlaResponseChart } from "@/components/sla-response-chart";
import type { CareEventSummary } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// DashboardLive — client component que polla eventos a cada 5s e
// re-renderiza TODOS os widgets (KPIs, charts, hero alert, feed).
// Server Component fica responsável apenas pelo estado inicial +
// pacientes ativos (dado estável, não precisa polling).
// ═══════════════════════════════════════════════════════════════

const POLL_INTERVAL_MS = 5_000;

export function DashboardLive({
  initialEvents,
  patientsCount,
}: {
  initialEvents: CareEventSummary[];
  patientsCount: number;
}) {
  const [events, setEvents] = useState<CareEventSummary[]>(initialEvents);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date>(new Date());
  const [isPolling, setIsPolling] = useState(true);
  const [nowTick, setNowTick] = useState<number>(Date.now());
  const knownIdsRef = useRef<Set<string>>(
    new Set(initialEvents.map((e) => e.id)),
  );

  // Polling dos eventos — dispara imediato ao montar e a cada 5s
  useEffect(() => {
    if (!isPolling) return;
    let mounted = true;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

    async function poll() {
      try {
        const res = await fetch(`${apiBase}/api/events/active?limit=100`, {
          cache: "no-store",
        });
        if (!mounted || !res.ok) return;
        const next = (await res.json()) as CareEventSummary[];
        const previousIds = knownIdsRef.current;
        const nextIds = new Set(next.map((e) => e.id));
        knownIdsRef.current = nextIds;

        const withFreshness = next.map((e) => ({
          ...e,
          _isNew: !previousIds.has(e.id),
        })) as CareEventSummary[];

        setEvents(withFreshness);
        setLastUpdatedAt(new Date());
      } catch {
        // silencioso — tenta de novo no próximo tick
      }
    }

    // Primeiro poll imediato (sem esperar 5s) para diminuir TTL percebido
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [isPolling]);

  // Tick de 1s pra contadores e "há Xs"
  useEffect(() => {
    const id = setInterval(() => setNowTick(Date.now()), 1_000);
    return () => clearInterval(id);
  }, []);

  const derived = useMemo(() => {
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
    return {
      critical,
      urgent,
      attention,
      routine,
      escalating,
      criticalOrUrgent: critical + urgent,
    };
  }, [events]);

  const secondsSinceUpdate = Math.floor((nowTick - lastUpdatedAt.getTime()) / 1000);
  const avgResponseTime = "38s"; // placeholder — endpoint real futuro

  return (
    <div className="space-y-8 max-w-[1400px]">
      {/* ════════════════ Hero + Live Pulse ════════════════ */}
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Sparkles className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Dashboard clínico · ao vivo
            </span>
            <LivePulse
              isPolling={isPolling}
              secondsSinceUpdate={secondsSinceUpdate}
              onToggle={() => setIsPolling((v) => !v)}
            />
          </div>
          <h1 className="text-[2.25rem] md:text-[2.75rem] font-bold tracking-tight leading-[1.1]">
            Visão em <span className="accent-gradient-text">tempo real</span>
          </h1>
          <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
            Equipe de enfermagem e corpo médico acompanham pacientes com insights
            estruturados de cada relato processado pela Íris.
          </p>
        </div>

        {derived.criticalOrUrgent > 0 && (
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
                  <span className="tabular font-bold text-lg">{derived.criticalOrUrgent}</span>{" "}
                  {derived.criticalOrUrgent === 1 ? "alerta pendente" : "alertas pendentes"}
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
          label="Eventos ativos"
          value={events.length}
          hint="em andamento agora"
          icon={<Sparkles className="h-4 w-4" />}
          tone="teal"
        />
        <KPICard
          label="Urgente / Crítico"
          value={derived.criticalOrUrgent}
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

      {/* ════════════════ Distribuição + SLA ════════════════ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EventsDistribution
          counts={{
            routine: derived.routine,
            attention: derived.attention,
            urgent: derived.urgent,
            critical: derived.critical,
          }}
          total={events.length}
        />
        <SlaResponseChart
          counts={{
            routine: derived.routine,
            attention: derived.attention,
            urgent: derived.urgent,
            critical: derived.critical,
          }}
          median={avgResponseTime}
          familyCalls={derived.escalating}
        />
      </div>

      {/* ════════════════ Live feed (controlled pelo parent) ════════════════ */}
      <LiveEventsFeed initialEvents={events} externalEvents={events} />
    </div>
  );
}

// ---------------------------------------------------------------
// LivePulse — chip mostrando status do polling
// ---------------------------------------------------------------
function LivePulse({
  isPolling,
  secondsSinceUpdate,
  onToggle,
}: {
  isPolling: boolean;
  secondsSinceUpdate: number;
  onToggle: () => void;
}) {
  const label = !isPolling
    ? "pausado"
    : secondsSinceUpdate < 2
    ? "ao vivo"
    : secondsSinceUpdate < 10
    ? `${secondsSinceUpdate}s atrás`
    : `atualizado há ${secondsSinceUpdate}s`;

  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-white/[0.08] hover:border-white/[0.16] transition-colors group"
      title={isPolling ? "Clique para pausar" : "Clique para retomar"}
    >
      <span className="relative flex h-1.5 w-1.5">
        {isPolling && (
          <span className="absolute inline-flex h-full w-full rounded-full bg-accent-cyan opacity-50 animate-ping" />
        )}
        <span
          className={`relative inline-flex rounded-full h-1.5 w-1.5 ${
            isPolling ? "bg-accent-cyan" : "bg-muted-foreground"
          }`}
        />
      </span>
      <span className="text-[10px] font-medium tracking-wide text-muted-foreground group-hover:text-foreground uppercase">
        {label}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------
// KPICard
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

  // Animação suave quando o valor numérico muda
  const [displayValue, setDisplayValue] = useState(value);
  const [bump, setBump] = useState(false);
  useEffect(() => {
    if (displayValue !== value) {
      setBump(true);
      setDisplayValue(value);
      const t = setTimeout(() => setBump(false), 400);
      return () => clearTimeout(t);
    }
  }, [value, displayValue]);

  return (
    <div
      className={`
        glass-card rounded-xl p-4 relative overflow-hidden
        transition-all hover:border-white/[0.12] hover:translate-y-[-1px]
        ${alert && typeof value === "number" && value > 0 ? "glow-critical border-classification-critical/30" : ""}
      `}
    >
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

      <div
        className={`tabular ${isText ? "text-2xl" : "text-[2rem]"} font-bold leading-none mb-1 text-foreground transition-transform ${
          bump ? "scale-110" : "scale-100"
        }`}
      >
        {displayValue}
      </div>
      <div className="text-xs font-medium text-foreground/80 mt-1">{label}</div>
      <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>
    </div>
  );
}
