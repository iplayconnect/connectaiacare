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
 */

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
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

export const api = {
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
