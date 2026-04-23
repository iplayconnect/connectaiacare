/**
 * use-patient — hook de acesso ao prontuário completo.
 *
 * Estado atual (MVP demo): retorna mock canônico do exploracoes/mocks/patients.ts.
 * TODO(coder): substituir por fetch real ao backend quando endpoints estiverem prontos:
 *   - GET /api/patients/:id
 *   - GET /api/patients/:id/reports?limit=30
 *   - GET /api/patients/:id/vital-signs?days=30
 *   - GET /api/patients/:id/medications/events?days=7
 *   - GET /api/patients/:id/care-events?status=active,resolved
 *   - GET /api/patients/:id/insights  (Onda C+ — distiller + pattern detection)
 *
 * Padrão: suspense-friendly (Next.js 14 Server Components) + revalidate 0.
 * Para Client Components, use useSWR ou TanStack Query se precisar de polling.
 */
import {
  mockAntonio,
  mockAntonioCareEvents,
  mockAntonioReports,
  mockLucia,
  mockMaria,
  mockMariaCareEvents,
  mockMariaMedicationEvents,
  mockMariaReports,
  mockMariaVitalSigns,
  type CareEvent,
  type MedicationEvent,
  type Patient,
  type Report,
  type VitalSign,
} from "../../../exploracoes/mocks/patients";

// ══════════════════════════════════════════════════════════════════
// Tipos consolidados
// ══════════════════════════════════════════════════════════════════

export interface SofiaInsight {
  id: string;
  type: "pattern" | "recommendation" | "alert";
  title: string;
  description: string;
  confidence: number; // 0..1
  sources: string[]; // chunk_ids ou "últimos 7 dias de vitais"
  cfm_disclaimer?: boolean;
  created_at: string;
}

export interface PatientFull {
  patient: Patient;
  reports: Report[];
  vital_signs: VitalSign[];
  care_events: CareEvent[];
  medication_events: MedicationEvent[];
  insights: SofiaInsight[];
}

// ══════════════════════════════════════════════════════════════════
// Mock registry — por enquanto, 3 personas do mock canônico
// ══════════════════════════════════════════════════════════════════

const MOCK_REGISTRY: Record<string, PatientFull> = {
  [mockMaria.id]: {
    patient: mockMaria,
    reports: mockMariaReports,
    vital_signs: mockMariaVitalSigns,
    care_events: mockMariaCareEvents,
    medication_events: mockMariaMedicationEvents,
    insights: buildMariaInsights(),
  },
  [mockAntonio.id]: {
    patient: mockAntonio,
    reports: mockAntonioReports,
    vital_signs: [],
    care_events: mockAntonioCareEvents,
    medication_events: [],
    insights: buildAntonioInsights(),
  },
  [mockLucia.id]: {
    patient: mockLucia,
    reports: [],
    vital_signs: [],
    care_events: [],
    medication_events: [],
    insights: [],
  },
};

// Também aceita "maria" / "antonio" / "lucia" como id pra demo
MOCK_REGISTRY["maria"] = MOCK_REGISTRY[mockMaria.id];
MOCK_REGISTRY["antonio"] = MOCK_REGISTRY[mockAntonio.id];
MOCK_REGISTRY["lucia"] = MOCK_REGISTRY[mockLucia.id];

// ══════════════════════════════════════════════════════════════════
// Hook principal (Server Component-friendly)
// ══════════════════════════════════════════════════════════════════

export async function getPatient(id: string): Promise<PatientFull | null> {
  // TODO(coder): descomentar quando endpoints existirem
  // const [patient, reports, vitals, events, meds, insights] = await Promise.all([
  //   api.getPatient(id),
  //   api.listPatientReports(id, 30),
  //   api.listVitalSigns(id, 30),
  //   api.listCareEvents(id),
  //   api.listMedicationEvents(id, 7),
  //   api.listSofiaInsights(id),
  // ]);
  // return { patient, reports, vital_signs: vitals, care_events: events,
  //          medication_events: meds, insights };

  // Mock pra demo
  return MOCK_REGISTRY[id] ?? null;
}

// ══════════════════════════════════════════════════════════════════
// Insights mockados (Sofia pattern detection)
// ══════════════════════════════════════════════════════════════════

function buildMariaInsights(): SofiaInsight[] {
  return [
    {
      id: "insight-1",
      type: "pattern",
      title: "Picos de pressão após visitas da família",
      description:
        "Nos últimos 30 dias, a PA sistólica mediana subiu 12 mmHg em dias de visita familiar (78% dos casos). Pode sugerir estresse social ou interação com tema emocional não processado.",
      confidence: 0.78,
      sources: [
        "vital_signs_30d",
        "care_event_ce-001",
        "transcriptions_similarity",
      ],
      cfm_disclaimer: true,
      created_at: "2026-04-22T22:00:00Z",
    },
    {
      id: "insight-2",
      type: "recommendation",
      title: "Considerar titulação de Losartana 50→75mg",
      description:
        "PA persistentemente acima da meta individualizada (140/90) nos últimos 14 dias, com média 148/89. Paciente tolerou bem a dose atual, sem hipotensão ortostática relatada. Possível revisão pelo cardiologista.",
      confidence: 0.84,
      sources: ["vital_signs_14d", "medication_schedules", "beers_criteria_2023"],
      cfm_disclaimer: true,
      created_at: "2026-04-22T22:01:00Z",
    },
    {
      id: "insight-3",
      type: "alert",
      title: "Risco leve de hipoglicemia madrugada",
      description:
        "Glicemia pré-jantar média 142 mg/dL nos últimos 7 dias, mas em 2 dias foi <110. Combinação com dose de Metformina noturna pode aumentar risco de hipoglicemia de madrugada em idosos.",
      confidence: 0.71,
      sources: ["blood_glucose_7d", "medication_events_metformina"],
      cfm_disclaimer: true,
      created_at: "2026-04-22T22:02:00Z",
    },
  ];
}

function buildAntonioInsights(): SofiaInsight[] {
  return [
    {
      id: "insight-a1",
      type: "alert",
      title: "Risco elevado de nova queda",
      description:
        "Paciente com Parkinson + queda recente (22/04). Evidência de instabilidade postural crescente nos relatos de cuidadores (últimas 2 semanas).",
      confidence: 0.91,
      sources: ["care_event_ce-101", "reports_r101"],
      cfm_disclaimer: true,
      created_at: "2026-04-22T20:00:00Z",
    },
  ];
}

// ══════════════════════════════════════════════════════════════════
// Helpers de análise (útil pros componentes)
// ══════════════════════════════════════════════════════════════════

export function computeVitalTrend(
  vitals: VitalSign[],
  type: VitalSign["vital_type"],
): { values: number[]; delta7d: number; direction: "up" | "down" | "stable" } {
  const filtered = vitals
    .filter((v) => v.vital_type === type)
    .sort((a, b) => a.measured_at.localeCompare(b.measured_at));
  const values = filtered.map((v) => v.value_numeric);

  if (values.length < 2) {
    return { values, delta7d: 0, direction: "stable" };
  }

  // Delta: último - primeiro
  const first = values[0];
  const last = values[values.length - 1];
  const delta = last - first;

  let direction: "up" | "down" | "stable" = "stable";
  if (Math.abs(delta) > first * 0.05) {
    direction = delta > 0 ? "up" : "down";
  }
  return { values, delta7d: delta, direction };
}

export function computeMedicationAdherence(
  events: MedicationEvent[],
  scheduleId: string,
): { taken: number; total: number; percent: number } {
  const filtered = events.filter((e) => e.schedule_id === scheduleId);
  const taken = filtered.filter((e) => e.status === "taken").length;
  const total = filtered.filter(
    (e) => e.status === "taken" || e.status === "refused" || e.status === "missed",
  ).length;
  const percent = total > 0 ? Math.round((taken / total) * 100) : 0;
  return { taken, total, percent };
}
