/**
 * Mock canônico de pacientes — fixture para protótipos (HTML + TSX)
 *
 * Schema 1:1 com backend. Se um campo não está aqui, NÃO está no banco.
 * Se precisar adicionar campo, falar com Coder antes (migration necessária).
 *
 * Tabelas origem:
 *   - aia_health_patients        (migration 001)
 *   - aia_health_reports         (migration 001)
 *   - aia_health_care_events     (migration 005)
 *   - aia_health_vital_signs     (migration 004)
 *   - aia_health_medication_schedules (migration 010)
 *   - aia_health_medication_events    (migration 010)
 *   - aia_health_conversation_messages (migration 013)
 *
 * Uso em HTML:
 *   <script>
 *     // copia valores direto do arquivo ou hardcode strings equivalentes
 *   </script>
 *
 * Uso em TSX (após aprovação):
 *   import { mockMaria } from '@/exploracoes/mocks/patients';
 *   // substitui por usePatient(id) antes do deploy final
 */

// ═══════════════════════════════════════════════════════════════
// Types — refletem exatamente o schema backend
// ═══════════════════════════════════════════════════════════════

export type Classification = "routine" | "attention" | "urgent" | "critical";

export type Gender = "M" | "F" | "O";

export interface Condition {
  name: string;
  cid10?: string;        // código CID-10 (ex: "I10" hipertensão)
  since?: string;        // ISO date "2018-03-15"
  severity?: "mild" | "moderate" | "severe";
  controlled?: boolean;
}

export interface Medication {
  name: string;
  dose: string;          // ex: "50mg"
  frequency: string;     // ex: "1x/dia manhã"
  since?: string;
  prescriber?: string;   // "Dra. Ana Silva"
  class?: string;        // "antihipertensivo" | "antidiabético"
}

export interface Allergy {
  substance: string;
  reaction?: string;
  severity?: "mild" | "moderate" | "severe";
}

export interface ResponsibleFamily {
  name: string;
  relationship: string;  // "filha" | "filho" | "esposo"
  phone: string;
  email?: string;
  is_primary?: boolean;
}

export interface Patient {
  // Core (aia_health_patients)
  id: string;                          // UUID
  tenant_id: string;
  external_id?: string;                // vindo do MedMonitor
  full_name: string;
  nickname?: string;
  birth_date: string;                  // ISO "1948-07-22"
  gender: Gender;
  photo_url?: string;
  care_unit?: string;                  // "Residência familiar" | "SPA Central"
  room_number?: string;
  care_level?: "autonomo" | "semi_dependente" | "dependente";
  conditions: Condition[];             // JSONB
  medications: Medication[];           // JSONB
  allergies: Allergy[];                // JSONB
  responsible: ResponsibleFamily[];    // JSONB (array no mock, objeto no backend atual)
  active: boolean;
  created_at: string;                  // ISO timestamp
  updated_at: string;
}

export interface Report {
  // aia_health_reports
  id: string;
  patient_id: string;
  caregiver_name_claimed?: string;
  caregiver_phone: string;
  audio_duration_seconds?: number;
  transcription: string;
  transcription_confidence?: number;   // 0..1
  extracted_entities?: Record<string, unknown>;
  analysis?: {
    summary?: string;
    classification_reasoning?: string;
    symptoms_concerning?: string[];
    alerts?: Array<{ level: string; title: string; description: string }>;
    recommendations_caregiver?: string[];
    recommendations_medical?: string[];
  };
  classification: Classification;
  needs_medical_attention: boolean;
  status: "received" | "confirmed" | "analyzed" | "synced" | "error";
  received_at: string;                 // ISO
  analyzed_at?: string;
}

export interface CareEvent {
  // aia_health_care_events
  id: string;
  human_id: number;                    // #0042
  patient_id: string;
  caregiver_phone: string;
  initial_classification: Classification;
  current_classification: Classification;
  event_type?: string;                 // "queda" | "dispneia" | "confusao"
  event_tags: string[];
  status:
    | "analyzing"
    | "awaiting_ack"
    | "pattern_analyzed"
    | "escalating"
    | "awaiting_status_update"
    | "resolved"
    | "expired";
  summary?: string;
  opened_at: string;
  resolved_at?: string;
  closed_reason?: string;
}

export interface VitalSign {
  // aia_health_vital_signs
  id: string;
  patient_id: string;
  vital_type:
    | "blood_pressure_systolic"
    | "blood_pressure_diastolic"
    | "blood_pressure_composite"
    | "heart_rate"
    | "temperature"
    | "oxygen_saturation"
    | "blood_glucose"
    | "respiratory_rate"
    | "weight";
  value_numeric: number;
  value_secondary?: number;            // diastólica quando composite
  unit: string;                        // "mmHg" | "bpm" | "celsius" | "percent" | "mg/dl" | "kg"
  status: Classification;
  source: "manual" | "medmonitor" | "wearable" | "whatsapp_relato" | "imported";
  measured_at: string;
  notes?: string;
}

export interface MedicationEvent {
  // aia_health_medication_events
  id: string;
  schedule_id: string;
  patient_id: string;
  medication_name: string;
  dose: string;
  scheduled_at: string;
  status:
    | "scheduled"
    | "reminder_sent"
    | "taken"
    | "refused"
    | "skipped"
    | "missed";
  confirmed_by?: "patient" | "caregiver" | "auto";
  confirmed_at?: string;
}

export interface ConversationMessage {
  // aia_health_conversation_messages
  id: string;
  subject_phone: string;
  session_context: "onboarding" | "care_event" | "companion" | "general";
  channel: "whatsapp" | "alexa" | "voice_native" | "web";
  direction: "inbound" | "outbound";
  role: "user" | "assistant" | "system";
  content: string;
  received_at: string;
  safety_moderated?: boolean;
  processing_agent?: string;
}

// ═══════════════════════════════════════════════════════════════
// Persona 1 — Maria Santos (hipertensa + diabética, 30d timeline rica)
// ═══════════════════════════════════════════════════════════════

export const mockMaria: Patient = {
  id: "a1b2c3d4-e5f6-4789-a0b1-c2d3e4f56789",
  tenant_id: "sofiacuida_b2c",
  full_name: "Maria Aparecida Santos",
  nickname: "Dona Maria",
  birth_date: "1948-07-22",
  gender: "F",
  photo_url: "https://i.pravatar.cc/300?img=45",
  care_unit: "Residência familiar",
  care_level: "autonomo",
  conditions: [
    { name: "Hipertensão arterial", cid10: "I10", since: "2008-03-15",
      severity: "moderate", controlled: true },
    { name: "Diabetes mellitus tipo 2", cid10: "E11", since: "2015-11-02",
      severity: "moderate", controlled: false },
    { name: "Osteoartrite de joelho", cid10: "M17", since: "2020-06-10",
      severity: "mild", controlled: true },
  ],
  medications: [
    { name: "Losartana", dose: "50mg", frequency: "1x/dia manhã",
      since: "2008-04-01", class: "antihipertensivo" },
    { name: "Hidroclorotiazida", dose: "25mg", frequency: "1x/dia manhã",
      since: "2012-08-20", class: "diurético" },
    { name: "Metformina", dose: "850mg", frequency: "2x/dia (almoço e jantar)",
      since: "2015-11-10", class: "antidiabético" },
    { name: "Paracetamol", dose: "500mg", frequency: "SOS dor articular",
      since: "2020-07-01", class: "analgésico" },
  ],
  allergies: [
    { substance: "Dipirona", reaction: "Urticária", severity: "moderate" },
  ],
  responsible: [
    { name: "Juliana Santos Oliveira", relationship: "filha",
      phone: "5511987654321", email: "juliana.santos@email.com", is_primary: true },
    { name: "Ricardo Santos", relationship: "filho",
      phone: "5511987654322", is_primary: false },
  ],
  active: true,
  created_at: "2026-03-23T09:15:00Z",
  updated_at: "2026-04-22T18:30:00Z",
};

export const mockMariaReports: Report[] = [
  {
    id: "r001",
    patient_id: mockMaria.id,
    caregiver_name_claimed: "Juliana (filha)",
    caregiver_phone: "5511987654321",
    audio_duration_seconds: 28,
    transcription:
      "Oi Sofia, minha mãe tá reclamando de tontura desde ontem à tarde. Medi a pressão agora e tá 160 por 95. Ela tomou o Losartana normal de manhã. Ela fez xixi bastante vezes essa noite também, acho que é por causa do Hidroclorotiazida.",
    transcription_confidence: 0.94,
    classification: "attention",
    needs_medical_attention: true,
    status: "analyzed",
    received_at: "2026-04-22T14:30:00Z",
    analyzed_at: "2026-04-22T14:30:42Z",
    analysis: {
      summary:
        "Hipertensão descontrolada (160x95 mmHg) associada a tontura — possível hipotensão ortostática secundária a diurético.",
      symptoms_concerning: ["Tontura", "PA sistólica 160", "Noctúria aumentada"],
      alerts: [
        { level: "moderado", title: "PA acima da meta",
          description: "Meta individualizada: < 140x90. Valor atual sugere titulação terapêutica." },
      ],
      recommendations_caregiver: [
        "Monitorar PA 3x ao dia nos próximos 3 dias",
        "Evitar levantar rapidamente (risco queda por tontura)",
        "Manter hidratação (300ml a cada 2h na manhã)",
      ],
      recommendations_medical: [
        "Considerar revisão do esquema diurético",
        "Solicitar MAPA 24h se persistir > 3 dias",
      ],
    },
  },
  {
    id: "r002",
    patient_id: mockMaria.id,
    caregiver_name_claimed: "Juliana",
    caregiver_phone: "5511987654321",
    audio_duration_seconds: 18,
    transcription:
      "Sofia, a mãe tá mais animada hoje. Comeu bem no almoço, tomou os remédios, andou no jardim. Glicemia pré-jantar 142.",
    transcription_confidence: 0.97,
    classification: "routine",
    needs_medical_attention: false,
    status: "analyzed",
    received_at: "2026-04-21T19:45:00Z",
    analyzed_at: "2026-04-21T19:45:30Z",
    analysis: {
      summary: "Dia de rotina estável. Glicemia pré-prandial levemente elevada (142), dentro do aceitável para faixa etária.",
    },
  },
  {
    id: "r003",
    patient_id: mockMaria.id,
    caregiver_name_claimed: "Ricardo",
    caregiver_phone: "5511987654322",
    audio_duration_seconds: 42,
    transcription:
      "Sofia, tô com a mãe aqui, ela começou a sentir uma dor no peito há uns 15 minutos. Não é forte mas tá incomodando. Pressão 145 por 88, pulso 92. Ela tomou nitrato sublingual que o cardiologista deixou.",
    transcription_confidence: 0.96,
    classification: "urgent",
    needs_medical_attention: true,
    status: "analyzed",
    received_at: "2026-04-18T21:10:00Z",
    analyzed_at: "2026-04-18T21:10:35Z",
    analysis: {
      summary:
        "Dor torácica de início recente em paciente hipertensa com múltiplos fatores de risco. Necessária avaliação presencial IMEDIATA.",
      symptoms_concerning: ["Dor torácica", "Taquicardia leve (92bpm)", "PA 145x88"],
      alerts: [
        { level: "alto", title: "Dor torácica — descartar SCA",
          description: "Paciente com FR: HAS, DM2. Protocolo: ECG + troponina em < 1h." },
      ],
      recommendations_caregiver: [
        "NÃO DEIXAR SOZINHA",
        "Repetir nitrato sublingual em 5 min se dor persistir",
        "Levar ao PS imediatamente",
      ],
    },
  },
];

export const mockMariaCareEvents: CareEvent[] = [
  {
    id: "ce-001",
    human_id: 42,
    patient_id: mockMaria.id,
    caregiver_phone: "5511987654321",
    initial_classification: "attention",
    current_classification: "attention",
    event_type: "hipertensao_descontrolada",
    event_tags: ["tontura", "pressao_alta"],
    status: "awaiting_status_update",
    summary: "PA 160x95 com tontura — acompanhamento médico ativado.",
    opened_at: "2026-04-22T14:30:00Z",
  },
  {
    id: "ce-002",
    human_id: 38,
    patient_id: mockMaria.id,
    caregiver_phone: "5511987654322",
    initial_classification: "urgent",
    current_classification: "urgent",
    event_type: "dor_toracica",
    event_tags: ["dor_peito", "cardiovascular"],
    status: "resolved",
    summary: "Dor torácica autolimitada após nitrato SL. ECG sem alterações agudas no PS.",
    opened_at: "2026-04-18T21:10:00Z",
    resolved_at: "2026-04-19T03:45:00Z",
    closed_reason: "encaminhado_hospital",
  },
];

export const mockMariaVitalSigns: VitalSign[] = [
  // Últimos 30 dias de pressão arterial (samples)
  { id: "v1", patient_id: mockMaria.id, vital_type: "blood_pressure_composite",
    value_numeric: 160, value_secondary: 95, unit: "mmHg", status: "attention",
    source: "manual", measured_at: "2026-04-22T14:20:00Z" },
  { id: "v2", patient_id: mockMaria.id, vital_type: "blood_pressure_composite",
    value_numeric: 138, value_secondary: 84, unit: "mmHg", status: "routine",
    source: "manual", measured_at: "2026-04-22T08:00:00Z" },
  { id: "v3", patient_id: mockMaria.id, vital_type: "blood_pressure_composite",
    value_numeric: 142, value_secondary: 86, unit: "mmHg", status: "routine",
    source: "manual", measured_at: "2026-04-21T08:15:00Z" },
  { id: "v4", patient_id: mockMaria.id, vital_type: "blood_pressure_composite",
    value_numeric: 145, value_secondary: 88, unit: "mmHg", status: "attention",
    source: "manual", measured_at: "2026-04-18T21:00:00Z" },
  { id: "v5", patient_id: mockMaria.id, vital_type: "heart_rate",
    value_numeric: 82, unit: "bpm", status: "routine",
    source: "wearable", measured_at: "2026-04-22T14:25:00Z" },
  { id: "v6", patient_id: mockMaria.id, vital_type: "blood_glucose",
    value_numeric: 142, unit: "mg/dl", status: "routine",
    source: "manual", measured_at: "2026-04-21T19:30:00Z" },
  { id: "v7", patient_id: mockMaria.id, vital_type: "oxygen_saturation",
    value_numeric: 97, unit: "percent", status: "routine",
    source: "wearable", measured_at: "2026-04-22T14:25:00Z" },
];

export const mockMariaMedicationEvents: MedicationEvent[] = [
  {
    id: "me1", schedule_id: "s1", patient_id: mockMaria.id,
    medication_name: "Losartana", dose: "50mg",
    scheduled_at: "2026-04-22T07:00:00Z",
    status: "taken", confirmed_by: "caregiver",
    confirmed_at: "2026-04-22T07:10:00Z",
  },
  {
    id: "me2", schedule_id: "s2", patient_id: mockMaria.id,
    medication_name: "Metformina", dose: "850mg",
    scheduled_at: "2026-04-22T12:00:00Z",
    status: "taken", confirmed_by: "caregiver",
    confirmed_at: "2026-04-22T12:15:00Z",
  },
  {
    id: "me3", schedule_id: "s2", patient_id: mockMaria.id,
    medication_name: "Metformina", dose: "850mg",
    scheduled_at: "2026-04-22T19:00:00Z",
    status: "scheduled", // próxima dose
  },
  {
    id: "me4", schedule_id: "s3", patient_id: mockMaria.id,
    medication_name: "Hidroclorotiazida", dose: "25mg",
    scheduled_at: "2026-04-21T07:00:00Z",
    status: "refused", confirmed_by: "patient",
    confirmed_at: "2026-04-21T07:30:00Z",
  },
];

// ═══════════════════════════════════════════════════════════════
// Persona 2 — Antônio Ferreira (Parkinson inicial, queda recente)
// ═══════════════════════════════════════════════════════════════

export const mockAntonio: Patient = {
  id: "b2c3d4e5-f6a7-4890-b1c2-d3e4f5a67890",
  tenant_id: "sofiacuida_b2c",
  full_name: "Antônio Ferreira da Silva",
  nickname: "Seu Antônio",
  birth_date: "1944-02-08",
  gender: "M",
  photo_url: "https://i.pravatar.cc/300?img=12",
  care_unit: "SPA Tecnosenior Moema",
  room_number: "214",
  care_level: "semi_dependente",
  conditions: [
    { name: "Doença de Parkinson", cid10: "G20", since: "2022-05-12",
      severity: "mild", controlled: true },
    { name: "Depressão leve", cid10: "F32.0", since: "2023-01-20",
      severity: "mild", controlled: true },
  ],
  medications: [
    { name: "Levodopa + Carbidopa", dose: "250/25mg", frequency: "3x/dia",
      since: "2022-06-01", class: "antiparkinsoniano" },
    { name: "Sertralina", dose: "50mg", frequency: "1x/dia manhã",
      since: "2023-02-10", class: "antidepressivo" },
  ],
  allergies: [],
  responsible: [
    { name: "Claudia Ferreira", relationship: "filha",
      phone: "5511966554433", is_primary: true },
  ],
  active: true,
  created_at: "2026-02-10T11:00:00Z",
  updated_at: "2026-04-22T20:15:00Z",
};

export const mockAntonioReports: Report[] = [
  {
    id: "r101",
    patient_id: mockAntonio.id,
    caregiver_name_claimed: "Simone (enfermeira plantão)",
    caregiver_phone: "5511955667788",
    audio_duration_seconds: 34,
    transcription:
      "Sofia, seu Antônio caiu do banho agora. Tá consciente, orientado, reclamando de dor no quadril direito. Não consegue ficar em pé. Já acionei enfermagem da unidade.",
    transcription_confidence: 0.95,
    classification: "critical",
    needs_medical_attention: true,
    status: "analyzed",
    received_at: "2026-04-22T19:45:00Z",
    analyzed_at: "2026-04-22T19:45:20Z",
    analysis: {
      summary:
        "Queda do banho com dor em quadril direito em paciente com Parkinson. Suspeita de fratura de fêmur.",
      symptoms_concerning: [
        "Queda", "Dor quadril D", "Incapacidade de descarga de peso",
      ],
      alerts: [
        { level: "critico", title: "Suspeita fratura fêmur",
          description: "Paciente idoso + queda + dor quadril + incapacidade de DP = alta probabilidade. Imobilizar e transferir." },
      ],
      recommendations_caregiver: [
        "NÃO MOBILIZAR. Manter decúbito dorsal",
        "Aguardar SAMU / transferência",
        "Jejum até avaliação ortopédica",
      ],
    },
  },
];

export const mockAntonioCareEvents: CareEvent[] = [
  {
    id: "ce-101",
    human_id: 51,
    patient_id: mockAntonio.id,
    caregiver_phone: "5511955667788",
    initial_classification: "critical",
    current_classification: "critical",
    event_type: "queda",
    event_tags: ["queda", "dor_quadril", "fratura_suspeita"],
    status: "escalating",
    summary: "Queda do banho — suspeita fratura fêmur. SAMU acionado.",
    opened_at: "2026-04-22T19:45:00Z",
  },
];

// ═══════════════════════════════════════════════════════════════
// Persona 3 — Lúcia Oliveira (Alzheimer moderado, alta demanda família)
// ═══════════════════════════════════════════════════════════════

export const mockLucia: Patient = {
  id: "c3d4e5f6-a7b8-4901-c2d3-e4f5a6b78901",
  tenant_id: "sofiacuida_b2c",
  full_name: "Lúcia Helena Oliveira",
  nickname: "Dona Lúcia",
  birth_date: "1950-11-30",
  gender: "F",
  photo_url: "https://i.pravatar.cc/300?img=36",
  care_unit: "Residência familiar",
  care_level: "dependente",
  conditions: [
    { name: "Doença de Alzheimer", cid10: "G30", since: "2021-04-18",
      severity: "moderate", controlled: false },
    { name: "Hipotireoidismo", cid10: "E03", since: "2019-09-05",
      severity: "mild", controlled: true },
  ],
  medications: [
    { name: "Donepezila", dose: "10mg", frequency: "1x/dia noite",
      since: "2021-05-01", class: "anticolinesterásico" },
    { name: "Memantina", dose: "20mg", frequency: "1x/dia manhã",
      since: "2022-03-15", class: "antagonista NMDA" },
    { name: "Levotiroxina", dose: "75mcg", frequency: "1x/dia jejum",
      since: "2019-10-01", class: "hormônio tireoidiano" },
  ],
  allergies: [],
  responsible: [
    { name: "Fernanda Oliveira Campos", relationship: "filha",
      phone: "5511944332211", is_primary: true },
    { name: "Paulo Oliveira", relationship: "filho",
      phone: "5511944332212", is_primary: false },
    { name: "Roberto Campos", relationship: "genro",
      phone: "5511944332213", is_primary: false },
  ],
  active: true,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-04-22T21:00:00Z",
};

// ═══════════════════════════════════════════════════════════════
// Conversas Sofia — exemplos de mensagens pra simular chat live
// ═══════════════════════════════════════════════════════════════

export const mockOnboardingConversation: ConversationMessage[] = [
  {
    id: "m1", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "inbound", role: "user",
    content: "oi",
    received_at: "2026-04-23T20:10:00Z",
  },
  {
    id: "m2", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "outbound", role: "assistant",
    content:
      "Olá! 👋 Aqui é a *Sofia*, assistente da ConnectaIACare.\n\nEstou aqui pra ajudar você a cuidar de quem você ama, com monitoramento 24h por WhatsApp e uma central humana quando precisar.\n\nAntes de tudo, me conta: você está se cadastrando pra você mesmo ou pra monitorar um ente querido (mãe, pai, sogro, etc.)?",
    received_at: "2026-04-23T20:10:02Z",
    processing_agent: "sofia_onboarding",
  },
  {
    id: "m3", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "inbound", role: "user",
    content: "é pra minha mãe, ela tá ficando esquecida",
    received_at: "2026-04-23T20:10:30Z",
  },
  {
    id: "m4", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "outbound", role: "assistant",
    content:
      "Que carinho cuidar da sua mãe 💙\n\nMe diga SEU nome completo (você que está fazendo o cadastro).",
    received_at: "2026-04-23T20:10:32Z",
    processing_agent: "sofia_onboarding",
  },
  {
    id: "m5", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "inbound", role: "user",
    content: "Juliana Santos Oliveira",
    received_at: "2026-04-23T20:11:10Z",
  },
  {
    id: "m6", subject_phone: "5511987654321",
    session_context: "onboarding", channel: "whatsapp",
    direction: "outbound", role: "assistant",
    content:
      "Prazer, *Juliana*! 🤝\n\nAgora preciso do seu CPF — é pra vincular a conta e garantir a segurança dos seus dados.",
    received_at: "2026-04-23T20:11:12Z",
    processing_agent: "sofia_onboarding",
  },
];

// ═══════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════

export const allPatients = [mockMaria, mockAntonio, mockLucia];

export function patientAge(patient: Patient): number {
  const birth = new Date(patient.birth_date);
  const today = new Date("2026-04-23"); // freeze demo date
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return age;
}

export function classificationLabel(c: Classification): string {
  return {
    routine: "Rotina",
    attention: "Atenção",
    urgent: "Urgente",
    critical: "Crítico",
  }[c];
}

export function classificationColor(c: Classification): string {
  // matches tailwind.config.ts e globals.css
  return {
    routine: "#34d399",
    attention: "#fbbf24",
    urgent: "#fb923c",
    critical: "#ef4444",
  }[c];
}
