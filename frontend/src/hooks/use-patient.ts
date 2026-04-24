/**
 * use-patient — hook de acesso ao prontuário completo.
 *
 * Resolve paciente em 2 etapas:
 *   1. Checa mock registry (demo: "maria", "antonio", "lucia" ou UUIDs deles)
 *   2. Fallback pra API real GET /api/patients/:id
 *      Campos não retornados pela API (vital_signs, insights, med_events)
 *      são preenchidos com arrays vazios OU mocks genéricos pra demo visual.
 *
 * Quando backend ganhar endpoints dedicados (/api/patients/:id/vital-signs etc),
 * basta adicionar chamadas paralelas na seção "Real API fallback".
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
} from "@/mocks/patients";
import { api, type Patient as ApiPatient, type Report as ApiReport } from "@/lib/api";

// ══════════════════════════════════════════════════════════════════
// Tipos consolidados
// ══════════════════════════════════════════════════════════════════

export interface SofiaInsight {
  id: string;
  type: "pattern" | "recommendation" | "alert";
  title: string;
  description: string;
  confidence: number;
  sources: string[];
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
// Mock registry — 3 personas do mock canônico
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

// Aliases pra demo (pra digitar /patients/maria em vez de UUID)
MOCK_REGISTRY["maria"] = MOCK_REGISTRY[mockMaria.id];
MOCK_REGISTRY["antonio"] = MOCK_REGISTRY[mockAntonio.id];
MOCK_REGISTRY["lucia"] = MOCK_REGISTRY[mockLucia.id];

// ══════════════════════════════════════════════════════════════════
// Hook principal
// ══════════════════════════════════════════════════════════════════

export async function getPatient(id: string): Promise<PatientFull | null> {
  // 1. Mock registry primeiro (3 personas de demo)
  if (MOCK_REGISTRY[id]) {
    return MOCK_REGISTRY[id];
  }

  // 2. Fallback pra API real do backend
  try {
    const [patientData, eventsData] = await Promise.all([
      api.getPatient(id),
      api.listPatientEvents(id, true).catch(() => []),
    ]);

    return {
      patient: adaptApiPatient(patientData.patient),
      reports: (patientData.reports || []).map(adaptApiReport),
      care_events: (eventsData || []).map(adaptApiCareEvent),
      // Ainda sem endpoint dedicado — campos vazios são aceitáveis
      // TODO: quando backend expuser, plugar /api/patients/:id/vital-signs etc.
      vital_signs: [],
      medication_events: [],
      insights: [],
    };
  } catch (err) {
    // Paciente não existe nem no mock nem no backend
    console.error("[use-patient] getPatient failed", id, err);
    return null;
  }
}

// ══════════════════════════════════════════════════════════════════
// Adapters — converte shapes do backend pro shape do mock canônico
// ══════════════════════════════════════════════════════════════════

function adaptApiPatient(p: ApiPatient): Patient {
  return {
    id: p.id,
    tenant_id: "connectaiacare_demo",
    full_name: p.full_name,
    nickname: p.nickname ?? undefined,
    birth_date: p.birth_date ?? "1950-01-01",
    gender: (p.gender as "F" | "M" | "O") ?? "O",
    photo_url: p.photo_url ?? undefined,
    care_unit: p.care_unit ?? undefined,
    room_number: p.room_number ?? undefined,
    care_level:
      p.care_level === "autonomo" ||
      p.care_level === "semi_dependente" ||
      p.care_level === "dependente"
        ? p.care_level
        : undefined,
    conditions: (p.conditions || []).map((c) => ({
      name: c.description,
      cid10: c.code,
      severity:
        c.severity === "mild" || c.severity === "moderate" || c.severity === "severe"
          ? c.severity
          : undefined,
    })),
    medications: (p.medications || []).map((m) => ({
      name: m.name,
      dose: m.dose ?? "",
      frequency: m.schedule ?? "",
    })),
    allergies: (p.allergies || []).map((a) => ({ substance: a })),
    responsible: p.responsible
      ? [
          {
            name: p.responsible.name ?? "Responsável",
            relationship: p.responsible.relationship ?? "familiar",
            phone: p.responsible.phone ?? "",
            is_primary: true,
          },
        ]
      : [],
    active: p.active,
    created_at: p.created_at,
    updated_at: p.updated_at,
  };
}

function adaptApiReport(r: ApiReport): Report {
  return {
    id: r.id,
    patient_id: r.patient_id ?? "",
    caregiver_name_claimed: r.caregiver_name_claimed ?? undefined,
    caregiver_phone: "",
    transcription: r.transcription ?? "",
    classification: (r.classification as Report["classification"]) ?? "routine",
    needs_medical_attention: false,
    status: "analyzed",
    received_at: (r as unknown as { received_at?: string }).received_at ?? new Date().toISOString(),
    analysis: r.analysis as Report["analysis"],
  };
}

function adaptApiCareEvent(e: unknown): CareEvent {
  const raw = e as Record<string, unknown>;
  return {
    id: String(raw.id ?? ""),
    human_id: Number(raw.human_id ?? 0),
    patient_id: "",
    caregiver_phone: "",
    initial_classification: (raw.classification ?? "routine") as CareEvent["initial_classification"],
    current_classification: (raw.classification ?? "routine") as CareEvent["current_classification"],
    event_type: raw.event_type ? String(raw.event_type) : undefined,
    event_tags: [],
    status: (raw.status ?? "analyzing") as CareEvent["status"],
    summary: raw.summary ? String(raw.summary) : undefined,
    opened_at: raw.opened_at ? String(raw.opened_at) : new Date().toISOString(),
  };
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
      sources: ["vital_signs_30d", "care_event_ce-001", "transcriptions_similarity"],
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
