import { Pill } from "lucide-react";

import type {
  MedicationEvent,
  Patient,
} from "../../../../exploracoes/mocks/patients";

interface Props {
  medications: Patient["medications"];
  events: MedicationEvent[];
}

interface AdherenceData {
  name: string;
  dose: string;
  frequency: string;
  class?: string;
  taken: number;
  total: number;
  percent: number;
  nextDose?: string;
}

/**
 * Cards de medicações com adesão visual (últimos 7 dias).
 *
 * Cor da barra de adesão:
 *   >= 90% → verde (routine)
 *   70-89% → âmbar (attention)
 *   50-69% → laranja (urgent)
 *   < 50% → vermelho (critical, pulsante se crítico)
 */
export function MedicationsAdherence({ medications, events }: Props) {
  if (!medications.length) {
    return (
      <section className="glass-card rounded-2xl p-6">
        <h2 className="text-lg font-semibold">Medicações ativas</h2>
        <p className="text-sm text-muted-foreground mt-2">
          Nenhuma medicação registrada.
        </p>
      </section>
    );
  }

  const data: AdherenceData[] = medications.map((m) => {
    const med_events = events.filter((e) => e.medication_name === m.name);
    const taken = med_events.filter((e) => e.status === "taken").length;
    const other = med_events.filter(
      (e) => e.status === "refused" || e.status === "missed",
    ).length;
    const total = taken + other;
    const percent = total > 0 ? Math.round((taken / total) * 100) : 100;
    const nextDose = med_events.find((e) => e.status === "scheduled")?.scheduled_at;

    return {
      name: m.name,
      dose: m.dose,
      frequency: m.frequency,
      class: m.class,
      taken,
      total,
      percent,
      nextDose,
    };
  });

  return (
    <section className="glass-card rounded-2xl p-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">Medicações ativas</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Adesão últimos 7 dias
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
          {medications.length} ativas
        </span>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {data.map((m) => (
          <MedCard key={m.name} data={m} />
        ))}
      </div>
    </section>
  );
}

function MedCard({ data }: { data: AdherenceData }) {
  const { barClass, labelClass, badgeClass } = adherenceStyles(data.percent);
  const nextDoseLabel = data.nextDose ? formatNextDose(data.nextDose) : null;

  return (
    <article className="solid-card rounded-xl p-3.5 flex flex-col gap-2.5">
      <div className="flex items-start gap-2.5">
        <div className="w-8 h-8 rounded-md bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center flex-shrink-0">
          <Pill className="h-4 w-4 text-accent-cyan" aria-hidden />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground truncate">
              {data.name}
            </h3>
            <span className="text-xs text-muted-foreground tabular flex-shrink-0">
              {data.dose}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
            {data.frequency}
          </p>
          {data.class && (
            <span className="inline-block mt-1 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-white/5 text-muted-foreground font-semibold">
              {data.class}
            </span>
          )}
        </div>
      </div>

      {/* Adesão */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider">
          <span className="text-muted-foreground">Adesão 7d</span>
          <span className={`tabular ${labelClass}`}>{data.percent}%</span>
        </div>
        <div
          className="h-1.5 bg-white/5 rounded-full overflow-hidden"
          role="progressbar"
          aria-valuenow={data.percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Adesão ${data.name}: ${data.percent}%`}
        >
          <div
            className={`h-full rounded-full transition-all ${barClass}`}
            style={{ width: `${data.percent}%` }}
          />
        </div>
      </div>

      {/* Próxima dose */}
      {nextDoseLabel && (
        <div className={`text-[10px] uppercase tracking-wider font-semibold ${badgeClass}`}>
          Próxima dose · {nextDoseLabel}
        </div>
      )}
    </article>
  );
}

function adherenceStyles(percent: number) {
  if (percent >= 90) {
    return {
      barClass: "bg-classification-routine",
      labelClass: "text-classification-routine",
      badgeClass: "text-accent-cyan",
    };
  }
  if (percent >= 70) {
    return {
      barClass: "bg-classification-attention",
      labelClass: "text-classification-attention",
      badgeClass: "text-classification-attention",
    };
  }
  if (percent >= 50) {
    return {
      barClass: "bg-classification-urgent",
      labelClass: "text-classification-urgent",
      badgeClass: "text-classification-urgent",
    };
  }
  return {
    barClass: "bg-classification-critical animate-pulse-glow",
    labelClass: "text-classification-critical",
    badgeClass: "text-classification-critical",
  };
}

function formatNextDose(iso: string): string {
  const d = new Date(iso);
  const now = new Date("2026-04-23T20:00:00Z");
  const diffMin = Math.round((d.getTime() - now.getTime()) / 1000 / 60);

  if (diffMin < -60) return "atrasada";
  if (diffMin < 0) return `${-diffMin}min atrasada`;
  if (diffMin < 60) return `em ${diffMin}min`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `em ${diffH}h`;
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}
