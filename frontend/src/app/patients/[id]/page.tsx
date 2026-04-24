import { notFound } from "next/navigation";

import { MedicationTimeline } from "@/components/medication/medication-timeline";
import { MedicationsAdherence } from "@/components/prontuario/medications-adherence";
import { PatientHero } from "@/components/prontuario/patient-hero";
import { SofiaInsights } from "@/components/prontuario/sofia-insights";
import { Timeline30d } from "@/components/prontuario/timeline-30d";
import { VitalSignsGrid } from "@/components/prontuario/vital-signs-grid";
import { getPatient } from "@/hooks/use-patient";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// ═══════════════════════════════════════════════════════════════
// Prontuário 360° — visão completa do paciente
//
// Data flow: getPatient(id) é a única interface.
//   - Hoje: retorna mock de exploracoes/mocks/patients.ts
//   - Amanhã: swap interno pra chamada API real (GET /api/patients/:id/*)
// Componentes aqui NÃO sabem disso — só consomem o PatientFull.
//
// IDs suportados hoje (mock):
//   "maria"   → Dona Maria Aparecida Santos, 78, HAS+DM2
//   "antonio" → Seu Antônio Ferreira, 82, Parkinson + queda recente
//   "lucia"   → Dona Lúcia Oliveira, 75, Alzheimer moderado
// ═══════════════════════════════════════════════════════════════

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const data = await getPatient(id);

  if (!data) {
    notFound();
  }

  const { patient, reports, vital_signs, care_events, medication_events, insights } =
    data;

  // Score ACG mockado — em produção virá de `aia_health_acg_scores` (Onda D)
  const acgScore = computeMockACG(patient);

  return (
    <div className="space-y-5 max-w-[1400px] animate-fade-up">
      <PatientHero patient={patient} acgScore={acgScore} care_events={care_events} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <VitalSignsGrid
            vital_signs={vital_signs}
            medication_events={medication_events}
          />
          <Timeline30d
            reports={reports}
            care_events={care_events}
            medication_events={medication_events}
          />
        </div>

        <div className="space-y-5">
          <SofiaInsights insights={insights} />
          <MedicationTimeline
            patientId={patient.id}
            patientName={patient.nickname || patient.full_name}
          />
          <MedicationsAdherence
            medications={patient.medications}
            events={medication_events}
          />
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Mock ACG — em produção: chamada a serviço de risk stratification
// ══════════════════════════════════════════════════════════════════

function computeMockACG(patient: {
  conditions: Array<{ name: string; severity?: string; controlled?: boolean }>;
}): { value: number; label: string } {
  let score = 0;
  for (const c of patient.conditions) {
    if (c.severity === "severe") score += 25;
    else if (c.severity === "moderate") score += 15;
    else score += 8;
    if (c.controlled === false) score += 10;
  }
  const clamped = Math.min(100, score);

  let label = "Baixo";
  if (clamped >= 75) label = "Alto";
  else if (clamped >= 50) label = "Moderado";
  else if (clamped >= 25) label = "Leve";

  return { value: clamped, label };
}
