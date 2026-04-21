"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight,
  Clock,
  HeartPulse,
  Radio,
  Users,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import type { CareEventSummary, EventStatus } from "@/lib/api";
import {
  CLASSIFICATION_LABELS,
  classificationTone,
  timeAgo,
} from "@/lib/utils";

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

const RANK: Record<string, number> = {
  critical: 0,
  urgent: 1,
  attention: 2,
  routine: 3,
};

const POLL_INTERVAL_MS = 10_000;

export function LiveEventsFeed({
  initialEvents,
}: {
  initialEvents: CareEventSummary[];
}) {
  const [events, setEvents] = useState<CareEventSummary[]>(initialEvents);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date>(new Date());
  const [isPolling, setIsPolling] = useState(true);
  const [nowTick, setNowTick] = useState<number>(Date.now());
  const knownIdsRef = useRef<Set<string>>(
    new Set(initialEvents.map((e) => e.id)),
  );

  // Polling dos eventos a cada POLL_INTERVAL_MS
  useEffect(() => {
    if (!isPolling) return;

    let mounted = true;
    // Browser chama API pública (mesmo host do frontend não tem backend — é container Next separado).
    // NEXT_PUBLIC_API_URL cai no valor do hostname ("https://demo.connectaia.com.br") em prod.
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
    async function poll() {
      try {
        const res = await fetch(`${apiBase}/api/events/active?limit=100`, {
          cache: "no-store",
        });
        if (!mounted || !res.ok) return;
        const next = (await res.json()) as CareEventSummary[];

        // Detecta novos eventos pra animação de entrada
        const previousIds = knownIdsRef.current;
        const nextIds = new Set(next.map((e) => e.id));
        knownIdsRef.current = nextIds;

        // Mantém flag de "novo" por 6s pra disparar animação
        const withFreshness = next.map((e) => ({
          ...e,
          _isNew: !previousIds.has(e.id),
        }));

        setEvents(withFreshness as typeof events);
        setLastUpdatedAt(new Date());
      } catch {
        // silencioso — tenta de novo no próximo tick
      }
    }

    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [isPolling]);

  // Tick de 1s pra contadores regressivos e "há X min"
  useEffect(() => {
    const id = setInterval(() => setNowTick(Date.now()), 1_000);
    return () => clearInterval(id);
  }, []);

  // Nota: setEvents é o próprio setter. Os campos "_isNew" serão reescritos no próximo poll.
  // Não precisamos de timer pra remover esse flag — CSS animation só roda na montagem.

  // Ordena: por classificação (critical → routine) + mais recente primeiro
  const sortedEvents = useMemo(() => {
    const copy = [...events];
    copy.sort((a, b) => {
      const ra = RANK[a.classification || "routine"] ?? 9;
      const rb = RANK[b.classification || "routine"] ?? 9;
      if (ra !== rb) return ra - rb;
      return (b.opened_at || "").localeCompare(a.opened_at || "");
    });
    return copy;
  }, [events]);

  const secondsSinceUpdate = Math.floor((nowTick - lastUpdatedAt.getTime()) / 1000);

  return (
    <section className="glass-card rounded-2xl overflow-hidden">
      <div className="p-6 border-b border-white/[0.05] flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold">Eventos ativos</h2>
          <p className="text-xs text-muted-foreground">
            Priorizados por classificação · atualização automática
          </p>
        </div>
        <div className="flex items-center gap-3">
          <LivePulse
            isPolling={isPolling}
            secondsSinceUpdate={secondsSinceUpdate}
            onToggle={() => setIsPolling((v) => !v)}
          />
          <Link
            href="/patients"
            className="text-xs font-medium text-accent-cyan hover:text-accent-teal transition-colors flex items-center gap-1"
          >
            Todos os pacientes <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>
      </div>

      <ul className="divide-y divide-white/[0.04]">
        {sortedEvents.length === 0 ? (
          <EmptyState />
        ) : (
          sortedEvents.map((e) => (
            <EventListItem key={e.id} event={e} nowTick={nowTick} />
          ))
        )}
      </ul>
    </section>
  );
}

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
    : `atualizado há ${secondsSinceUpdate}s`;

  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-full border border-white/[0.06] hover:border-white/[0.14] transition-colors group"
      title={isPolling ? "Clique para pausar atualização" : "Clique para retomar"}
    >
      <span className="relative flex h-2 w-2">
        {isPolling && (
          <span className="absolute inline-flex h-full w-full rounded-full bg-accent-cyan opacity-50 animate-ping" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            isPolling ? "bg-accent-cyan" : "bg-muted-foreground"
          }`}
        />
      </span>
      <span className="text-xs font-medium tracking-wide text-muted-foreground group-hover:text-foreground">
        {label}
      </span>
      {isPolling && <Radio className="h-3 w-3 text-accent-cyan opacity-50" />}
    </button>
  );
}

function EventListItem({
  event,
  nowTick,
}: {
  event: CareEventSummary & { _isNew?: boolean };
  nowTick: number;
}) {
  const tone = classificationTone(event.classification);
  const label = CLASSIFICATION_LABELS[event.classification || "routine"];
  const status = event.status;
  const dot = STATUS_DOT[status];
  const statusLabel = STATUS_LABEL[status];
  const humanId = event.human_id
    ? `#${event.human_id.toString().padStart(4, "0")}`
    : "#----";
  const patient = event.patient_nickname || event.patient_name || "Paciente";

  // Contador regressivo pro expires_at
  const countdown = useMemo(() => {
    if (!event.expires_at) return null;
    const expiresMs = new Date(event.expires_at).getTime();
    const leftMs = expiresMs - nowTick;
    if (leftMs <= 0) return { text: "expirando", urgent: true };
    const mins = Math.floor(leftMs / 60_000);
    const secs = Math.floor((leftMs % 60_000) / 1_000);
    if (mins >= 60) {
      const hours = Math.floor(mins / 60);
      return { text: `${hours}h ${mins % 60}min restantes`, urgent: false };
    }
    if (mins >= 10) return { text: `${mins} min restantes`, urgent: false };
    if (mins >= 1)
      return {
        text: `${mins}min ${secs}s restantes`,
        urgent: mins < 5,
      };
    return { text: `${secs}s restantes`, urgent: true };
  }, [event.expires_at, nowTick]);

  return (
    <li className={event._isNew ? "animate-slide-in-fade" : ""}>
      <Link
        href={`/eventos/${event.id}`}
        className="flex items-center gap-4 p-5 hover:bg-white/[0.02] transition-colors group relative"
      >
        {event._isNew && (
          <span className="absolute top-2 right-4 text-xs font-semibold uppercase tracking-wider text-accent-cyan animate-pulse-soft">
            • novo
          </span>
        )}

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
            <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
              {humanId}
            </span>
            <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
              {patient}
            </h3>
            {event.patient_care_unit && (
              <span className="text-xs uppercase tracking-wider text-muted-foreground hidden md:inline">
                · {event.patient_care_unit}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground truncate mb-1.5">
            {event.summary || "Análise em andamento…"}
          </p>
          <div className="flex items-center gap-3 text-[13px] text-muted-foreground/90 flex-wrap">
            <span className="inline-flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
              {statusLabel}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {timeAgo(event.opened_at)}
            </span>
            {countdown && (
              <span
                className={`inline-flex items-center gap-1 font-medium tabular ${
                  countdown.urgent
                    ? "text-classification-urgent animate-pulse-soft"
                    : "text-muted-foreground"
                }`}
                title="Tempo até decisão automática de encerramento"
              >
                ⏱ {countdown.text}
              </span>
            )}
            {event.event_tags && event.event_tags.length > 0 && (
              <span className="inline-flex items-center gap-1 flex-wrap">
                {event.event_tags.slice(0, 3).map((t) => (
                  <span
                    key={t}
                    className="px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.05] text-xs"
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
          <span
            className={`text-xs uppercase tracking-wider font-semibold ${tone}`}
          >
            {label}
          </span>
        </div>
      </Link>
    </li>
  );
}

function EmptyState() {
  return (
    <li className="p-12 text-center">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.03] border border-white/[0.06] mb-4">
        <HeartPulse className="h-6 w-6 text-accent-teal" />
      </div>
      <h3 className="font-medium mb-1">Nenhum evento em andamento</h3>
      <p className="text-sm text-muted-foreground max-w-sm mx-auto">
        Quando um cuidador enviar um áudio pelo WhatsApp, o evento aparece aqui
        em tempo real.
      </p>
    </li>
  );
}
