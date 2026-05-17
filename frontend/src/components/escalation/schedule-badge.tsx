"use client";

/**
 * ScheduleBadge — visualização compacta do turno de um contato de
 * escalação (migration 080).
 *
 * Renderiza:
 *   • Dias da semana como pílulas (S/T/Q/Q/S/S/D), com ativos
 *     destacados; inativos cinza.
 *   • Janela horária (08:00–18:00).
 *   • Indicador "ATIVO AGORA" (verde) ou "FORA DA JANELA" (cinza)
 *     calculado client-side com hora local America/Sao_Paulo.
 *   • Caso especial: schedule completamente NULL = chip "24/7"
 *     com infinity icon.
 *
 * Refresh a cada minuto pra atualizar status "ativo agora" sem
 * exigir reload (escala muda de turno às 8h e 18h, p.ex.).
 *
 * Props expostas:
 *   weekdays?: number[] | null  — ISO 1=seg..7=dom (NULL=todos)
 *   start?: string | null        — "HH:MM:SS" ou "HH:MM" (NULL=24h)
 *   end?: string | null          — idem
 *   showLiveStatus?: boolean     — default true; mostra chip ativo/fora
 */

import { useEffect, useState } from "react";
import { Activity, Infinity as InfinityIcon } from "lucide-react";

interface ScheduleBadgeProps {
  weekdays?: number[] | null;
  start?: string | null;
  end?: string | null;
  showLiveStatus?: boolean;
  /** Compacto remove emojis/icons grandes. Default false. */
  compact?: boolean;
}

const WEEKDAY_LETTERS = ["", "S", "T", "Q", "Q", "S", "S", "D"];
const WEEKDAY_FULL = ["", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

/** ISO weekday no fuso America/Sao_Paulo (1=seg, 7=dom). */
function isoWeekdaySP(): number {
  // JS getDay: 0=dom..6=sab; ISO: 1=seg..7=dom
  const now = new Date();
  const spStr = now.toLocaleString("en-US", { timeZone: "America/Sao_Paulo" });
  const sp = new Date(spStr);
  const js = sp.getDay();
  return js === 0 ? 7 : js;
}

/** "HH:MM" no fuso America/Sao_Paulo. */
function currentTimeSP(): string {
  const now = new Date();
  return now.toLocaleTimeString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function timeStrToMinutes(s: string): number {
  const [h, m] = s.split(":").map(Number);
  return h * 60 + (m || 0);
}

function inWindow(start: string, end: string, now: string): boolean {
  const s = timeStrToMinutes(start);
  const e = timeStrToMinutes(end);
  const n = timeStrToMinutes(now);
  // Janela mesmo dia (s <= e): ativa se s <= n <= e
  if (s <= e) return n >= s && n <= e;
  // Janela cross-midnight (ex: 22:00-06:00): ativa se n >= s ou n <= e
  return n >= s || n <= e;
}

export function ScheduleBadge({
  weekdays,
  start,
  end,
  showLiveStatus = true,
  compact = false,
}: ScheduleBadgeProps) {
  const [tick, setTick] = useState(0);

  // Atualiza a cada 60s pra refletir mudança de turno sem reload
  useEffect(() => {
    if (!showLiveStatus) return;
    const interval = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(interval);
  }, [showLiveStatus]);

  const hasDays = weekdays && weekdays.length > 0;
  const hasTime = start && end;

  // ── Caso 24/7: nem dias nem horários ──────────────────────────
  if (!hasDays && !hasTime) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan text-[10px] font-semibold uppercase tracking-wider">
        <InfinityIcon className="h-2.5 w-2.5" />
        24/7
      </span>
    );
  }

  // ── Live status (computed every render + 60s tick) ────────────
  const todayIso = isoWeekdaySP();
  const nowHHMM = currentTimeSP();
  const dayActive = !hasDays || (weekdays as number[]).includes(todayIso);
  const timeActive =
    !hasTime ||
    inWindow(start!.slice(0, 5), end!.slice(0, 5), nowHHMM);
  const liveActive = dayActive && timeActive;

  return (
    <div className="inline-flex items-center gap-2 flex-wrap">
      {/* Pílulas de dias da semana */}
      {hasDays && (
        <div className="inline-flex items-center gap-0.5" title={
          (weekdays as number[]).map((d) => WEEKDAY_FULL[d] || `?${d}`).join(", ")
        }>
          {[1, 2, 3, 4, 5, 6, 7].map((d) => {
            const isActive = (weekdays as number[]).includes(d);
            const isToday = d === todayIso;
            return (
              <span
                key={d}
                className={[
                  "inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold transition",
                  isActive
                    ? isToday
                      ? "bg-accent-cyan text-slate-900"
                      : "bg-white/[0.08] text-foreground"
                    : "bg-transparent text-muted-foreground/30 border border-white/[0.04]",
                ].join(" ")}
                aria-label={`${WEEKDAY_FULL[d]}${isActive ? " (ativo)" : ""}${isToday ? " (hoje)" : ""}`}
              >
                {WEEKDAY_LETTERS[d]}
              </span>
            );
          })}
        </div>
      )}

      {/* Janela horária */}
      {hasTime && (
        <span className="text-[10px] font-mono tabular text-muted-foreground">
          {start!.slice(0, 5)}–{end!.slice(0, 5)}
        </span>
      )}

      {/* Live status chip */}
      {showLiveStatus && !compact && (
        liveActive ? (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-classification-routine/40 bg-classification-routine/10 text-classification-routine text-[9px] font-semibold uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-classification-routine animate-pulse" />
            Ativo agora
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-white/[0.05] bg-white/[0.02] text-muted-foreground text-[9px] uppercase tracking-wider">
            <Activity className="h-2 w-2" />
            Fora da janela
          </span>
        )
      )}
    </div>
  );
}
