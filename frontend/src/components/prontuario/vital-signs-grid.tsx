import { VitalSparkline } from "./vital-sparkline";

import type { MedicationEvent, VitalSign } from "@/mocks/patients";

interface Props {
  vital_signs: VitalSign[];
  medication_events: MedicationEvent[];
}

/**
 * Grid de 6 sinais vitais principais com sparklines + alvos + tendências.
 *
 * Inclui também "Adesão" como 6ª métrica derivada dos medication_events.
 */
export function VitalSignsGrid({ vital_signs, medication_events }: Props) {
  const systolic = extract(vital_signs, "blood_pressure_composite", (v) => v.value_numeric);
  const diastolic = extract(vital_signs, "blood_pressure_composite", (v) => v.value_secondary ?? 0);
  const heartRate = extract(vital_signs, "heart_rate", (v) => v.value_numeric);
  const spo2 = extract(vital_signs, "oxygen_saturation", (v) => v.value_numeric);
  const glucose = extract(vital_signs, "blood_glucose", (v) => v.value_numeric);
  const adherence = computeAdherenceSeries(medication_events);

  return (
    <section className="glass-card rounded-2xl p-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">Sinais vitais</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Últimas 30 medições · alvo em verde
          </p>
        </div>
      </header>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <VitalSparkline
          label="PA Sistólica"
          unit="mmHg"
          values={systolic}
          target={{ min: 120, max: 140 }}
          anomalyThreshold={{ min: 100, max: 150 }}
          delta7d={deltaOf(systolic)}
          direction={directionOf(systolic)}
          betterIsLower
          ariaLabel="Pressão arterial sistólica"
        />
        <VitalSparkline
          label="PA Diastólica"
          unit="mmHg"
          values={diastolic}
          target={{ min: 70, max: 90 }}
          anomalyThreshold={{ min: 60, max: 95 }}
          delta7d={deltaOf(diastolic)}
          direction={directionOf(diastolic)}
          betterIsLower
          ariaLabel="Pressão arterial diastólica"
        />
        <VitalSparkline
          label="Glicemia"
          unit="mg/dL"
          values={glucose}
          target={{ min: 90, max: 130 }}
          anomalyThreshold={{ min: 70, max: 180 }}
          delta7d={deltaOf(glucose)}
          direction={directionOf(glucose)}
          ariaLabel="Glicemia"
        />
        <VitalSparkline
          label="Frequência Cardíaca"
          unit="bpm"
          values={heartRate}
          target={{ min: 60, max: 100 }}
          anomalyThreshold={{ min: 55, max: 110 }}
          delta7d={deltaOf(heartRate)}
          direction={directionOf(heartRate)}
          ariaLabel="Frequência cardíaca"
        />
        <VitalSparkline
          label="Saturação O₂"
          unit="%"
          values={spo2}
          target={{ min: 95, max: 100 }}
          anomalyThreshold={{ min: 92, max: 100 }}
          delta7d={deltaOf(spo2)}
          direction={directionOf(spo2)}
          ariaLabel="Saturação de oxigênio"
        />
        <VitalSparkline
          label="Adesão Medicação"
          unit="%"
          values={adherence}
          target={{ min: 85, max: 100 }}
          anomalyThreshold={{ min: 70, max: 100 }}
          delta7d={deltaOf(adherence)}
          direction={directionOf(adherence)}
          ariaLabel="Adesão a medicação"
        />
      </div>
    </section>
  );
}

// ══════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════

function extract(
  vitals: VitalSign[],
  type: VitalSign["vital_type"],
  getter: (v: VitalSign) => number,
): number[] {
  return vitals
    .filter((v) => v.vital_type === type)
    .sort((a, b) => a.measured_at.localeCompare(b.measured_at))
    .map(getter)
    .filter((n) => Number.isFinite(n) && n > 0);
}

function deltaOf(values: number[]): number {
  if (values.length < 2) return 0;
  return values[values.length - 1] - values[0];
}

function directionOf(values: number[]): "up" | "down" | "stable" {
  if (values.length < 2) return "stable";
  const delta = values[values.length - 1] - values[0];
  const threshold = Math.abs(values[0]) * 0.05;
  if (Math.abs(delta) < threshold) return "stable";
  return delta > 0 ? "up" : "down";
}

function computeAdherenceSeries(events: MedicationEvent[]): number[] {
  if (!events.length) return [95, 92, 94, 88, 96, 90, 93];
  // Agrupa por dia (ISO date) e calcula % tomadas/total
  const byDay: Record<string, { taken: number; total: number }> = {};
  for (const e of events) {
    const day = (e.confirmed_at || e.scheduled_at).slice(0, 10);
    if (!byDay[day]) byDay[day] = { taken: 0, total: 0 };
    if (e.status === "taken") byDay[day].taken++;
    if (e.status === "taken" || e.status === "refused" || e.status === "missed") {
      byDay[day].total++;
    }
  }
  const days = Object.keys(byDay).sort();
  return days.map((d) =>
    byDay[d].total > 0 ? Math.round((byDay[d].taken / byDay[d].total) * 100) : 100,
  );
}
