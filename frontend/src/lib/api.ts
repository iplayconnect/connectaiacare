/**
 * API client para ConnectaIACare backend.
 *
 * Em Next.js usamos Server Components (SSR) que rodam DENTRO do container do
 * frontend — o fetch "server-side" precisa resolver o service name docker
 * "api:5055". Já o browser (Client Components, interações) acessa via o
 * hostname público ou localhost em dev.
 *
 *   typeof window === "undefined"  → server (container) → INTERNAL_API_URL
 *   typeof window !== "undefined"  → browser → NEXT_PUBLIC_API_URL
 *
 * Auth: no browser, injeta `Authorization: Bearer <token>` lendo de
 * localStorage. 401 → limpa auth e redireciona pra /login.
 * SSR não injeta token — páginas com fetch SSR que precisem de auth devem
 * ser convertidas pra client components ou ler o cookie via `next/headers`.
 */

import { clearAuth, getToken } from "./auth";

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export class ApiError extends Error {
  status: number;
  reason?: string;
  body?: any;
  constructor(status: number, message: string, reason?: string, body?: any) {
    super(message);
    this.status = status;
    this.reason = reason;
    this.body = body;
  }
}

function buildHeaders(init?: RequestInit): HeadersInit {
  const base: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = getToken();
    if (token) base["Authorization"] = `Bearer ${token}`;
  }
  // Permite override individual via init.headers
  return { ...base, ...((init?.headers as Record<string, string>) || {}) };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: buildHeaders(init),
    cache: "no-store",
  });

  if (res.status === 401 && typeof window !== "undefined") {
    // Sessão expirou ou inválida → limpa e manda pro login.
    // Evita loop se já estiver na própria /login (login chama /api/auth/login que é público).
    clearAuth();
    if (!window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.href = `/login?next=${next}`;
    }
    throw new ApiError(401, "unauthorized", "unauthorized");
  }

  if (!res.ok) {
    const text = await res.text();
    let reason: string | undefined;
    let body: any = undefined;
    try {
      body = JSON.parse(text);
      reason = body?.reason;
    } catch {
      /* body não é JSON */
    }
    throw new ApiError(res.status, `API ${res.status}: ${text}`, reason, body);
  }
  return (await res.json()) as T;
}

export interface Patient {
  id: string;
  full_name: string;
  nickname: string | null;
  birth_date: string | null;
  gender: string | null;
  photo_url: string | null;
  care_unit: string | null;
  room_number: string | null;
  care_level: string | null;
  conditions: Array<{ code?: string; description: string; severity?: string }>;
  medications: Array<{ name: string; schedule: string; dose?: string }>;
  allergies: string[];
  responsible: { name?: string; relationship?: string; phone?: string } | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Report {
  id: string;
  patient_id: string | null;

  // Campos flat vindos do JOIN em report_service.get_by_id / list_recent
  patient_name?: string;
  patient_photo?: string;
  patient_room?: string;
  patient_birth_date?: string | null;
  patient_care_unit?: string | null;
  patient_conditions?: Array<{ code?: string; description: string; severity?: string }>;
  patient_medications?: Array<{ name: string; schedule: string; dose?: string }>;

  caregiver_name_claimed: string | null;
  transcription: string | null;
  audio_url: string | null;
  classification: "routine" | "attention" | "urgent" | "critical" | null;
  status: string;
  analysis: {
    summary?: string;
    alerts?: Array<{ level: string; title: string; description: string }>;
    recommendations_caregiver?: string[];
    needs_medical_attention?: boolean;
    classification_reasoning?: string;
    tags?: string[];
  };
  received_at: string;
  analyzed_at: string | null;
}

export interface DashboardSummary {
  last_24h_by_classification: Record<string, number>;
  active_patients: number;
  recent_reports: Report[];
}

// ============================================================
// Care Events (ADR-018) — modelo central de operação clínica
// ============================================================
export type EventStatus =
  | "analyzing"
  | "awaiting_ack"
  | "pattern_analyzed"
  | "escalating"
  | "awaiting_status_update"
  | "resolved"
  | "expired";

export type EventClassification = "routine" | "attention" | "urgent" | "critical";

export type ClosedReason =
  | "cuidado_iniciado"
  | "encaminhado_hospital"
  | "transferido"
  | "sem_intercorrencia"
  | "falso_alarme"
  | "paciente_estavel"
  | "expirou_sem_feedback"
  | "obito"
  | "outro";

export interface CareEventSummary {
  id: string;
  human_id: number | null;
  patient_id: string | null;
  patient_name: string | null;
  patient_nickname: string | null;
  patient_photo: string | null;
  patient_care_unit: string | null;
  caregiver_phone: string | null;
  classification: EventClassification | null;
  status: EventStatus;
  event_type: string | null;
  event_tags: string[];
  summary: string | null;
  opened_at: string | null;
  resolved_at: string | null;
  closed_by: string | null;
  closed_reason: ClosedReason | null;
  expires_at: string | null;
}

export interface TimelineItem {
  t: string;
  kind: string;
  label: string;
  text?: string;
}

export interface Escalation {
  id: string;
  target_role: "central" | "nurse" | "doctor" | "family_1" | "family_2" | "family_3";
  target_name: string | null;
  target_phone: string;
  channel: "whatsapp" | "voice" | "sms";
  status:
    | "queued"
    | "sent"
    | "delivered"
    | "read"
    | "responded"
    | "no_answer"
    | "failed";
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  responded_at: string | null;
  response_summary: string | null;
}

export interface CheckinItem {
  id: string;
  kind:
    | "pattern_analysis"
    | "status_update"
    | "closure_check"
    | "post_escalation";
  scheduled_for: string | null;
  sent_at: string | null;
  response_received_at: string | null;
  response_text: string | null;
  response_classification: string | null;
  status: "scheduled" | "sent" | "responded" | "skipped" | "failed";
}

export interface ReportBrief {
  id: string;
  received_at: string | null;
  transcription: string | null;
  classification: EventClassification | null;
  audio_duration_seconds: number | null;
  analysis_summary: string | null;
}

export interface CareEventDetail {
  event: CareEventSummary & {
    context: {
      messages?: Array<{
        role: "caregiver" | "assistant";
        kind: string;
        text?: string;
        summary?: string;
        timestamp?: string;
      }>;
      last_analysis?: {
        summary?: string;
        classification?: string;
        classification_reasoning?: string;
        recommendations_caregiver?: string[];
      };
    };
    reasoning: string | null;
    initial_classification: EventClassification | null;
    pattern_analyzed_at: string | null;
    first_escalation_at: string | null;
    last_check_in_at: string | null;
    closure_notes: string | null;
  };
  patient: {
    id: string;
    full_name: string;
    nickname: string | null;
    photo_url: string | null;
    care_unit: string | null;
    room_number: string | null;
    conditions: Array<{ code?: string; description: string; severity?: string }>;
    medications: Array<{ name: string; schedule: string; dose?: string }>;
  } | null;
  timeline: TimelineItem[];
  escalations: Escalation[];
  checkins: CheckinItem[];
  reports: ReportBrief[];
}

export interface CloseEventPayload {
  closed_by?: string;
  closed_reason: ClosedReason;
  closure_notes?: string;
}

export interface CloseEventResponse {
  status: "resolved";
  event_id: string;
  closed_reason: ClosedReason;
  medmonitor_sync: {
    attempted: boolean;
    created: boolean;
    note_id?: number;
    error?: string;
  };
}

// ============================================================
// Auth + Users + Profiles (Bloco A/B/C)
// ============================================================

import type { AuthUser } from "./auth";

// ============================================================
// Dose validation (cruzamento Bulário ANVISA / Beers / SBGG)
// ============================================================

export type DoseSeverity = "info" | "warning" | "warning_strong" | "block";

export interface DoseIssue {
  severity: DoseSeverity;
  code:
    | "dose_above_limit"
    | "beers_avoid"
    | "unknown_drug"
    | "dose_unparseable"
    | "no_limit_for_route"
    | "unit_mismatch"
    | "allergy_match"
    | "duplicate_therapy"
    | "polypharmacy"
    | "narrow_therapeutic_index"
    | "drug_interaction"
    | "condition_contraindicated"
    | "anticholinergic_burden"
    | "fall_risk"
    | "renal_adjustment"
    | "renal_adjust_no_data"
    | "hepatic_adjustment"
    | "hepatic_severity_unknown"
    | "vital_constraint";
  message: string;
  detail?: Record<string, unknown>;
}

export interface DoseValidation {
  ok: boolean;
  severity: DoseSeverity | null;
  principle_active: string | null;
  limit_found: boolean;
  computed_daily_dose: { value: number; unit: string } | null;
  max_daily_dose: { value: number; unit: string } | null;
  ratio: number | null;
  source: string | null;
  source_ref: string | null;
  notes: string | null;
  issues: DoseIssue[];
}

export interface SofiaMessage {
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  toolName?: string | null;
  toolOutput?: Record<string, unknown> | null;
  model?: string | null;
  tokensIn?: number | null;
  tokensOut?: number | null;
  audioUrl?: string | null;
  createdAt: string | null;
}

export interface ProfileRecord {
  id: string;
  tenantId: string;
  slug: string;
  displayName: string;
  description: string | null;
  permissions: string[];
  config: Record<string, unknown>;
  active: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export const api = {
  // Auth
  me: () => request<{ status: "ok"; user: AuthUser }>("/api/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ status: "ok" }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ currentPassword, newPassword }),
    }),
  forgotPassword: (email: string) =>
    request<{ status: "ok"; channel?: string; hint?: string }>(
      "/api/auth/forgot-password",
      { method: "POST", body: JSON.stringify({ email }) },
    ),
  resetPassword: (token: string, newPassword: string) =>
    request<{ status: "ok" }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, newPassword }),
    }),

  // Users (admin)
  listUsers: (includeInactive = false) =>
    request<{ status: "ok"; users: AuthUser[] }>(
      `/api/users?include_inactive=${includeInactive}`,
    ),
  getUser: (id: string) =>
    request<{ status: "ok"; user: AuthUser }>(`/api/users/${id}`),
  createUser: (payload: {
    email: string;
    fullName: string;
    password: string;
    role: AuthUser["role"];
    phone?: string;
    profileId?: string;
    permissions?: string[];
    crmRegister?: string;
    corenRegister?: string;
    caregiverId?: string;
    patientId?: string;
    allowedPatientIds?: string[];
    partnerOrg?: string;
    passwordChangeRequired?: boolean;
  }) =>
    request<{ status: "ok"; user: AuthUser }>("/api/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUser: (
    id: string,
    payload: Partial<{
      fullName: string;
      phone: string;
      avatarUrl: string;
      role: AuthUser["role"];
      permissions: string[];
      profileId: string | null;
      crmRegister: string;
      corenRegister: string;
      caregiverId: string | null;
      patientId: string | null;
      allowedPatientIds: string[];
      partnerOrg: string;
      active: boolean;
    }>,
  ) =>
    request<{ status: "ok"; user: AuthUser }>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteUser: (id: string) =>
    request<{ status: "ok" }>(`/api/users/${id}`, { method: "DELETE" }),
  uploadAvatar: (id: string, dataUrl: string) =>
    request<{ status: "ok" }>(`/api/users/${id}/avatar`, {
      method: "POST",
      body: JSON.stringify({ image: dataUrl }),
    }),
  adminSetPassword: (id: string, newPassword: string) =>
    request<{ status: "ok" }>(`/api/users/${id}/password`, {
      method: "POST",
      body: JSON.stringify({ newPassword }),
    }),

  // ─── Sofia Care ──────────────────────────────────
  sofiaChat: (message: string, channel: "web" | "whatsapp" = "web") =>
    request<{
      status: "ok";
      sessionId: string;
      agent: string;
      model: string;
      text: string;
      tokensIn: number;
      tokensOut: number;
      toolCalls: number;
      blocked?: boolean;
      reason?: string;
    }>("/api/sofia/chat", {
      method: "POST",
      body: JSON.stringify({ message, channel }),
    }),
  sofiaGreeting: () =>
    request<{ status: "ok"; text: string }>("/api/sofia/greeting", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  sofiaHistory: (sessionId: string) =>
    request<{
      status: "ok";
      sessionId: string;
      messages: SofiaMessage[];
    }>(`/api/sofia/sessions/${sessionId}`),
  sofiaUsage: () =>
    request<{
      status: "ok";
      usage: {
        year: number;
        month: number;
        messages: number;
        tokensIn: number;
        tokensOut: number;
        audioMinutes: number;
        toolCalls: number;
        planSku: string | null;
      };
    }>("/api/sofia/usage"),
  sofiaTTS: (text: string, voice?: string) =>
    request<{
      status: "ok";
      audioBase64: string;
      mimeType: string;
      durationSeconds: number;
      model: string;
      voice: string;
    }>("/api/sofia/tts", {
      method: "POST",
      body: JSON.stringify({ text, voice }),
    }),
  sofiaVoiceToken: () =>
    request<{
      status: "ok";
      wsUrl: string;
      expiresInSeconds: number;
      audio: {
        inputSampleRate: number;
        outputSampleRate: number;
        format: string;
      };
    }>("/api/sofia/voice/token", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // Profiles (Bloco C)
  listProfiles: () =>
    request<{ status: "ok"; profiles: ProfileRecord[] }>("/api/profiles"),
  listAvailablePermissions: () =>
    request<{ status: "ok"; groups: Record<string, string[]>; all: string[] }>(
      "/api/profiles/permissions",
    ),
  getProfile: (id: string) =>
    request<{ status: "ok"; profile: ProfileRecord }>(`/api/profiles/${id}`),
  createProfile: (payload: {
    slug: string;
    displayName: string;
    description?: string;
    permissions: string[];
    config?: Record<string, unknown>;
  }) =>
    request<{ status: "ok"; profile: ProfileRecord }>("/api/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateProfile: (
    id: string,
    payload: Partial<{
      displayName: string;
      description: string;
      permissions: string[];
      config: Record<string, unknown>;
      active: boolean;
    }>,
  ) =>
    request<{ status: "ok"; profile: ProfileRecord }>(`/api/profiles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteProfile: (id: string) =>
    request<{ status: "ok" }>(`/api/profiles/${id}`, { method: "DELETE" }),

  // Legados
  listPatients: () => request<{ patients: Patient[] }>("/api/patients"),
  getPatient: (id: string) =>
    request<{ patient: Patient; reports: Report[] }>(`/api/patients/${id}`),
  listReports: (limit = 50) =>
    request<{ reports: Report[] }>(`/api/reports?limit=${limit}`),
  getReport: (id: string) => request<{ report: Report }>(`/api/reports/${id}`),
  dashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),

  // Care Events (ADR-018)
  listActiveEvents: (limit = 100) =>
    request<CareEventSummary[]>(`/api/events/active?limit=${limit}`),
  getEvent: (id: string) => request<CareEventDetail>(`/api/events/${id}`),
  closeEvent: (id: string, payload: CloseEventPayload) =>
    request<CloseEventResponse>(`/api/events/${id}/close`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listPatientEvents: (patientId: string, includeClosed = true) =>
    request<CareEventSummary[]>(
      `/api/patients/${patientId}/events?include_closed=${includeClosed}`,
    ),

  // Teleconsulta (ADR-023)
  startTeleconsulta: (
    eventId: string,
    payload: { initiator_name?: string; initiator_role?: string },
  ) =>
    request<TeleconsultaStartResponse>(
      `/api/events/${eventId}/teleconsulta/start`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  endTeleconsulta: (eventId: string, closureNotes?: string) =>
    request<{ status: string; room_name: string }>(
      `/api/events/${eventId}/teleconsulta/end`,
      { method: "POST", body: JSON.stringify({ closure_notes: closureNotes }) },
    ),
  listTeleconsultaParticipants: (eventId: string) =>
    request<{
      room_name: string;
      participants: Array<{
        identity: string;
        name: string;
        joined_at: number;
        state: string;
      }>;
      active: boolean;
    }>(`/api/events/${eventId}/teleconsulta/participants`),

  // Teleconsulta pós-sala: transcrição, SOAP, prescrição, assinatura
  getTeleconsulta: (tcId: string) =>
    request<{ teleconsulta: TeleconsultaRecord }>(`/api/teleconsulta/${tcId}`),
  saveTranscription: (
    tcId: string,
    transcription: string,
    durationSeconds?: number,
  ) =>
    request<{ status: "ok"; chars: number }>(
      `/api/teleconsulta/${tcId}/transcription`,
      {
        method: "POST",
        body: JSON.stringify({
          transcription,
          duration_seconds: durationSeconds,
        }),
      },
    ),
  generateSoap: (tcId: string) =>
    request<{ status: "ok"; soap: SoapDocument }>(
      `/api/teleconsulta/${tcId}/soap/generate`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  getSoap: (tcId: string) =>
    request<{
      soap: SoapDocument;
      prescription: PrescriptionItem[];
      signed_at: string | null;
      state: string;
    }>(`/api/teleconsulta/${tcId}/soap`),
  updateSoap: (tcId: string, soap: SoapDocument) =>
    request<{ status: "ok" }>(`/api/teleconsulta/${tcId}/soap`, {
      method: "PUT",
      body: JSON.stringify({ soap }),
    }),
  addPrescription: (tcId: string, item: PrescriptionInput) =>
    request<{
      status: "ok";
      prescription_item: PrescriptionItem;
      validation: PrescriptionValidation;
    }>(`/api/teleconsulta/${tcId}/prescription`, {
      method: "POST",
      body: JSON.stringify(item),
    }),
  // ========== Medication (Bloco 1) ==========
  listMedicationSchedules: (patientId: string) =>
    request<{ results: MedicationSchedule[] }>(
      `/api/patients/${patientId}/medication-schedules`,
    ),
  createMedicationSchedule: (
    patientId: string,
    body: Partial<MedicationSchedule> & {
      medication_name: string;
      dose: string;
      force?: boolean;  // confirmação após warning ANVISA/Beers
    },
  ) =>
    request<{
      status: string;
      schedule: MedicationSchedule;
      validation: DoseValidation;
    }>(`/api/patients/${patientId}/medication-schedules`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateMedicationSchedule: (scheduleId: string, body: Partial<MedicationSchedule>) =>
    request<{ status: string; schedule: MedicationSchedule }>(
      `/api/medication-schedules/${scheduleId}`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  deleteMedicationSchedule: (scheduleId: string, reason?: string) =>
    request<{ status: string }>(
      `/api/medication-schedules/${scheduleId}${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`,
      { method: "DELETE" },
    ),
  listUpcomingMedicationEvents: (patientId: string, hours = 24) =>
    request<{ results: MedicationEvent[] }>(
      `/api/patients/${patientId}/medication-events/upcoming?hours=${hours}`,
    ),
  listMedicationHistory: (patientId: string, days = 7) =>
    request<{ results: MedicationEvent[] }>(
      `/api/patients/${patientId}/medication-events/history?days=${days}`,
    ),
  confirmMedicationEvent: (eventId: string, body: { confirmed_by?: string; actual_dose?: string; notes?: string }) =>
    request<{ status: string }>(
      `/api/medication-events/${eventId}/confirm`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  skipMedicationEvent: (eventId: string, reason: string) =>
    request<{ status: string }>(
      `/api/medication-events/${eventId}/skip`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
  medicationAdherence: (patientId: string, days = 30) =>
    request<MedicationAdherence>(
      `/api/patients/${patientId}/medication-adherence?days=${days}`,
    ),
  createMedicationImport: (patientId: string, body: {
    source_type: string;
    file_b64: string;
    file_mime?: string;
    uploaded_by_type?: string;
  }) =>
    request<MedicationImportAnalysis>(
      `/api/patients/${patientId}/medication-imports`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  confirmMedicationImport: (importId: string, body: {
    medications: ExtractedMedication[];
    added_by_type?: string;
  }) =>
    request<{ status: string; created_schedule_ids: string[]; count: number }>(
      `/api/medication-imports/${importId}/confirm`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  signTeleconsulta: (
    tcId: string,
    payload?: { doctor_name?: string; doctor_crm?: string; closure_notes?: string },
  ) =>
    request<{
      status: "signed";
      teleconsulta_id: string;
      fhir_bundle_id: string;
      signature_method: string;
      medmonitor_sync: {
        attempted: boolean;
        created: boolean;
        note_id?: number;
        error?: string;
      };
    }>(`/api/teleconsulta/${tcId}/sign`, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    }),
};

// ============================================================
// Teleconsulta (ADR-023)
// ============================================================
export interface TeleconsultaStartResponse {
  status: "ok";
  room_name: string;
  room_sid: string | null;
  doctor_token: string;
  patient_token: string;
  doctor_url: string;
  patient_url: string;
  ws_url: string;
  expires_at: string;
}

// ---------- Tipos pós-sala (SOAP + Prescrição + Assinatura) -------------
export interface SoapDocument {
  subjective: {
    chief_complaint?: string;
    history_of_present_illness?: string;
    review_of_systems?: Record<string, string>;
    patient_quotes?: string[];
  };
  objective: {
    vital_signs_reported_in_consult?: string;
    physical_exam_findings?: string;
    lab_results_mentioned?: string | null;
  };
  assessment: {
    primary_hypothesis?: {
      description?: string;
      icd10?: string;
      confidence?: string;
    } | null;
    differential_diagnoses?: Array<{
      description: string;
      icd10?: string;
      reasoning?: string;
    }>;
    active_problems_confirmed?: string[];
    new_problems_identified?: string[];
    clinical_reasoning?: string;
  };
  plan: {
    medications?: {
      continued?: string[];
      adjusted?: string[];
      started?: string[];
      suspended?: string[];
    };
    non_pharmacological?: string[];
    diagnostic_tests_requested?: string[];
    referrals?: string[];
    return_follow_up?: {
      when?: string;
      modality?: string;
      trigger_signs?: string[];
    };
    patient_education?: string;
  };
  scribe_confidence?: {
    overall?: "low" | "medium" | "high";
    notes_for_doctor?: string;
  };
  _error?: string;
}

export interface PrescriptionInput {
  medication: string;
  dose?: string;
  schedule?: string;
  duration?: string;
  indication?: string;
}

export interface PrescriptionValidation {
  validation_status: "approved" | "approved_with_warnings" | "rejected";
  severity: "none" | "low" | "moderate" | "high" | "critical";
  issues?: Array<{
    type: "interaction" | "allergy" | "dose" | "contraindication" | "beers_criteria";
    severity: "low" | "moderate" | "high" | "critical";
    description: string;
    involved_medications?: string[];
    recommendation?: string;
    reasoning?: string;
  }>;
  beers_match?: {
    is_potentially_inappropriate?: boolean;
    category?: string;
    justification?: string;
  };
  dose_assessment?: {
    within_usual_range?: boolean;
    geriatric_adjustment_note?: string;
  };
  overall_recommendation?: string;
  _error?: string;
}

export interface PrescriptionItem extends PrescriptionInput {
  id: string;
  added_at: string;
  validation?: PrescriptionValidation;
}

export interface TeleconsultaRecord {
  id: string;
  care_event_id: string | null;
  room_name: string;
  state: string;
  started_at: string | null;
  ended_at: string | null;
  signed_at: string | null;
  patient_id: string;
  patient_full_name: string;
  patient_nickname: string | null;
  patient_birth_date: string | null;
  patient_gender: string | null;
  patient_care_level: string | null;
  patient_conditions: Array<{ code?: string; description: string; severity?: string }> | null;
  patient_medications: Array<{ name: string; schedule: string; dose?: string }> | null;
  patient_allergies: string[] | null;
  doctor_id: string | null;
  doctor_name_snapshot: string | null;
  doctor_crm_snapshot: string | null;
  transcription_full: string | null;
  transcription_duration_seconds: number | null;
  soap: SoapDocument | null;
  prescription: PrescriptionItem[] | null;
  fhir_bundle: Record<string, unknown> | null;
}

// ========== Medication types (Bloco 1) ==========

export interface MedicationSchedule {
  id: string;
  medication_name: string;
  dose: string;
  dose_form?: string;
  schedule_type:
    | "fixed_daily"
    | "fixed_weekly"
    | "fixed_monthly"
    | "cycle"
    | "prn"
    | "custom";
  times_of_day?: string[];
  days_of_week?: number[];
  with_food?: "with" | "without" | "either";
  special_instructions?: string;
  warnings?: string[];
  source_type?: string;
  source_confidence?: number;
  verification_status?:
    | "confirmed"
    | "needs_review"
    | "conflicting"
    | "superseded";
  active?: boolean;
  starts_at?: string;
  ends_at?: string | null;
}

export interface MedicationEvent {
  id: string;
  schedule_id: string;
  medication_name?: string;
  dose?: string;
  scheduled_at: string;
  reminder_sent_at?: string | null;
  confirmed_at?: string | null;
  confirmed_by?: string | null;
  status:
    | "scheduled"
    | "reminder_sent"
    | "taken"
    | "missed"
    | "skipped"
    | "refused"
    | "paused"
    | "cancelled";
  actual_dose_taken?: string | null;
  notes?: string | null;
  special_instructions?: string | null;
  with_food?: string;
  warnings?: string[];
}

export interface MedicationAdherence {
  summary: {
    taken: number;
    missed: number;
    refused: number;
    skipped: number;
    total: number;
    adherence_pct: number | null;
    period_days: number;
  };
  by_medication: Array<{
    medication_name: string;
    dose: string;
    taken: number;
    missed: number;
    refused_skipped: number;
    total: number;
    adherence_pct: number | null;
  }>;
  consecutive_missed: Array<{
    schedule_id: string;
    medication_name: string;
    recent_statuses: string[];
    missed_in_last_n: number;
  }>;
}

export interface ExtractedMedication {
  name: string;
  alternative_names?: string[];
  dose: string;
  dose_form?: string;
  schedule_text?: string;
  parsed_schedule?: {
    times_per_day?: number;
    times_of_day?: string[];
    prn?: boolean;
    days_of_week?: number[];
    interval_hours?: number;
  };
  duration_text?: string;
  duration_days?: number | null;
  indication?: string;
  warnings?: string[];
  with_food?: "with" | "without" | "either";
  field_confidence?: {
    name?: number;
    dose?: number;
    schedule?: number;
  };
}

export interface MedicationImportAnalysis {
  status: string;
  import_id: string;
  analysis_status: "done" | "failed";
  kind:
    | "prescription"
    | "package"
    | "leaflet"
    | "pill_organizer"
    | "not_medication_related"
    | "unclear";
  confidence?: number;
  needs_more_info?: string | null;
  medications?: ExtractedMedication[];
  notes_for_user?: string;
  doctor_info?: { name?: string; crm?: string } | null;
  issue_date?: string | null;
}
