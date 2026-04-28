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
    | "vital_constraint"
    | "time_separation_required"
    | "time_separation_ok";
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

export interface ClinicalAlertIssue {
  code: string;
  severity?: "low" | "medium" | "high" | "critical";
  message: string;
  details?: Record<string, unknown>;
}

export interface ClinicalAlertRow {
  id: string;
  level: "low" | "medium" | "high" | "critical";
  title: string;
  description: string | null;
  recommended_actions: string[];
  status: "open" | "acknowledged" | "resolved";
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string | null;
  patient_id: string | null;
  patient_name: string | null;
  patient_nickname: string | null;
  patient_unit: string | null;
  patient_room: string | null;
  kinds: string[];
  validation: {
    issues?: ClinicalAlertIssue[];
    medication_name?: string;
    dose?: string;
    [k: string]: unknown;
  } | null;
}

export interface CallScenario {
  id: string;
  code: string;
  label: string;
  direction: "outbound" | "inbound";
  persona: string;
  description: string | null;
  system_prompt?: string;
  voice: string;
  allowed_tools: string[];
  post_call_actions: string[];
  pre_call_context_sql?: string | null;
  max_duration_seconds: number;
  active: boolean;
  updated_at: string | null;
}

export interface CallHistoryItem {
  id: string;
  persona: string;
  user_id: string | null;
  patient_id: string | null;
  phone: string | null;
  created_at: string | null;
  last_active_at: string | null;
  closed_at: string | null;
  duration_seconds: number | null;
  patient_name: string | null;
  patient_nickname: string | null;
  caller_name: string | null;
  message_count: number;
}

export interface TranscriptMessage {
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  created_at: string | null;
  tool_name: string | null;
}

// ───────── Safety Guardrail types ─────────
export type SafetyActionType =
  | "informative"
  | "register_history"
  | "invoke_attendant"
  | "emergency_realtime"
  | "modify_prescription";

export type SafetySeverity = "info" | "attention" | "urgent" | "critical";

export type SafetyQueueStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "auto_executed"
  | "expired"
  | "cancelled";

export interface SafetyQueueItem {
  id: string;
  tenant_id: string;
  action_type: SafetyActionType;
  severity: SafetySeverity;
  summary: string;
  patient_id: string | null;
  patient_name?: string | null;
  sofia_session_id: string | null;
  triggered_by_tool: string | null;
  triggered_by_persona: string | null;
  sofia_confidence: number | null;
  details: Record<string, unknown> | null;
  status: SafetyQueueStatus;
  created_at: string;
  auto_execute_after: string | null;
  decided_at: string | null;
  decided_by_user_id: string | null;
  decision_notes: string | null;
}

export interface SafetyCircuitState {
  status: "ok";
  state: "closed" | "open" | "half_open";
  tenant_id: string;
  open_until?: string | null;
  opened_at?: string | null;
  open_reason?: string | null;
  recent_action_count?: number;
  recent_queued_count?: number;
}

// ───────── Patient Risk Scoring types ─────────
export interface PatientRiskRow {
  patient_id: string;
  patient_name?: string;
  score: number;
  level: "low" | "moderate" | "high" | "critical";
  complaints_7d: number;
  adherence_pct: number | null;
  urgent_events_7d: number;
  trend: string | null;
  breakdown: Record<string, unknown>;
  computed_at: string;
  // Fase 2 — baseline individual
  has_baseline?: boolean;
  baseline_complaints_z?: number | null;
  baseline_adherence_z?: number | null;
  baseline_urgent_z?: number | null;
  baseline_deviation_score?: number | null;
  combined_score?: number | null;
  combined_level?: "low" | "moderate" | "high" | "critical" | null;
}

export interface PatientBaseline {
  patient_id: string;
  tenant_id: string;
  period_days: number;
  weeks_observed: number;
  complaints_median: number | null;
  complaints_mad: number | null;
  complaints_history: number[];
  adherence_median: number | null;
  adherence_mad: number | null;
  adherence_history: number[];
  urgent_median: number | null;
  urgent_mad: number | null;
  urgent_history: number[];
  has_sufficient_data: boolean;
  insufficient_reason: string | null;
  last_computed_at: string;
}

// ───────── Drug Cascades types ─────────
export type CascadeSeverity = "contraindicated" | "major" | "moderate" | "minor";

export interface DrugCascade {
  id: string;
  name: string;
  severity: CascadeSeverity;
  match_pattern: "a_and_c" | "a_b_and_c";
  drug_a_principles: string[];
  drug_a_classes: string[];
  drug_b_principles: string[];
  drug_b_classes: string[];
  drug_c_principles: string[];
  drug_c_classes: string[];
  adverse_effect: string;
  cascade_explanation: string;
  recommendation: string;
  alternative: string | null;
  exclusion_conditions: Record<string, unknown> | null;
  source: string;
  source_ref: string | null;
  confidence: number;
  active: boolean;
}

export interface CascadeMatchedDrug {
  schedule_id: string;
  medication_name: string;
  principle: string;
  class: string | null;
}

export interface CascadeDetectionResult {
  cascade_id: string;
  name: string;
  severity: CascadeSeverity;
  match_pattern: "a_and_c" | "a_b_and_c";
  adverse_effect: string;
  explanation: string;
  recommendation: string;
  alternative: string | null;
  matched_drugs: {
    a: CascadeMatchedDrug[];
    b: CascadeMatchedDrug[] | null;
    c: CascadeMatchedDrug[];
  };
  source: string;
  source_ref: string | null;
  confidence: number;
}

// ───────── Proactive Caller types ─────────
export type ProactiveDecision =
  | "will_call"
  | "skip_disabled"
  | "skip_dnd"
  | "skip_outside_window"
  | "skip_too_soon"
  | "skip_low_score"
  | "skip_no_phone"
  | "skip_no_scenario"
  | "skip_circuit_open"
  | "failed_dispatch";

export interface ProactiveDecisionRow {
  id: string;
  tenant_id: string;
  patient_id: string;
  patient_name: string | null;
  patient_nickname: string | null;
  evaluated_at: string;
  decision: ProactiveDecision;
  trigger_score: number;
  breakdown: Record<string, unknown>;
  call_id: string | null;
  error: string | null;
  notes: string | null;
}

export interface PatientCallSettings {
  id: string;
  full_name?: string;
  sofia_proactive_calls_enabled: boolean;
  preferred_call_window_start: string;
  preferred_call_window_end: string;
  min_hours_between_calls: number;
  do_not_disturb_until: string | null;
  proactive_call_phone: string | null;
  proactive_scenario_code: string | null;
  proactive_call_timezone: string;
}

// ───────── Scenario Versioning types ─────────
export type ScenarioVersionStatus =
  | "draft"
  | "testing"
  | "published"
  | "archived";

export interface ScenarioVersion {
  id: string;
  scenario_id: string;
  version_number: number;
  status: ScenarioVersionStatus;
  label: string;
  description: string | null;
  system_prompt: string;
  voice: string;
  allowed_tools: string[];
  post_call_actions: string[];
  pre_call_context_sql: string | null;
  max_duration_seconds: number;
  golden_test_results: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  created_by_user_id: string | null;
  published_at: string | null;
  published_by_user_id: string | null;
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

  // ─── Comunicações (Sofia VoIP outbound) ────
  communicationsScenarios: () =>
    request<{ status: "ok"; scenarios: CallScenario[] }>(
      "/api/communications/scenarios",
    ),
  communicationsScenarioGet: (id: string) =>
    request<{ status: "ok"; scenario: CallScenario }>(
      `/api/communications/scenarios/${id}`,
    ),
  communicationsScenarioCreate: (body: Partial<CallScenario>) =>
    request<{ status: "ok"; scenario: CallScenario }>(
      "/api/communications/scenarios",
      { method: "POST", body: JSON.stringify(body) },
    ),
  communicationsScenarioUpdate: (id: string, body: Partial<CallScenario>) =>
    request<{ status: "ok"; scenario: CallScenario }>(
      `/api/communications/scenarios/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  communicationsScenarioDelete: (id: string) =>
    request<{ status: "ok" }>(
      `/api/communications/scenarios/${id}`,
      { method: "DELETE" },
    ),
  communicationsDial: (body: {
    scenario_code?: string;
    scenario_id?: string;
    destination: string;
    patient_id?: string;
    user_id?: string;
    full_name?: string;
    extra_context?: Record<string, unknown>;
  }) =>
    request<{ status: "ok"; call_id: string; scenario_code?: string }>(
      "/api/communications/dial",
      { method: "POST", body: JSON.stringify(body) },
    ),
  communicationsHangup: (call_id: string) =>
    request<{ status: "ok" }>("/api/communications/hangup", {
      method: "POST",
      body: JSON.stringify({ call_id }),
    }),
  communicationsActiveCalls: () =>
    request<{ status: string; active_count: number; calls: string[] }>(
      "/api/communications/active-calls",
    ),
  communicationsHistory: (params?: { patient_id?: string; user_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.patient_id) qs.set("patient_id", params.patient_id);
    if (params?.user_id) qs.set("user_id", params.user_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{ status: "ok"; count: number; history: CallHistoryItem[] }>(
      `/api/communications/history${q ? `?${q}` : ""}`,
    );
  },
  communicationsTranscript: (session_id: string) =>
    request<{ status: "ok"; transcript: TranscriptMessage[] }>(
      `/api/communications/history/${session_id}/transcript`,
    ),

  // ─── Alertas clínicos (dose validator + cruzamentos) ────
  listClinicalAlerts: (params?: {
    level?: string;
    status?: "open" | "acknowledged" | "resolved" | "active" | "all";
    kind?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.level) qs.set("level", params.level);
    if (params?.status) qs.set("status", params.status);
    if (params?.kind) qs.set("kind", params.kind);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{
      status: "ok";
      alerts: ClinicalAlertRow[];
      count: number;
    }>(`/api/alerts/clinical${q ? `?${q}` : ""}`);
  },
  acknowledgeClinicalAlert: (id: string, by?: string) =>
    request<{ status: "ok" }>(`/api/alerts/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ by: by || null }),
    }),
  resolveClinicalAlert: (id: string) =>
    request<{ status: "ok" }>(`/api/alerts/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  // ─── Regras Clínicas (motor de cruzamentos) ────
  clinicalRulesStats: () =>
    request<{ status: "ok"; stats: Record<string, number> }>(
      "/api/clinical-rules/stats",
    ),
  clinicalRulesList: (table: string) =>
    request<{ status: "ok"; items: any[] }>(
      `/api/clinical-rules/${table}`,
    ),
  doseLimitCreate: (body: any) =>
    request<{ status: "ok"; item: any }>(
      "/api/clinical-rules/dose-limits",
      { method: "POST", body: JSON.stringify(body) },
    ),
  doseLimitUpdate: (id: string, body: any) =>
    request<{ status: "ok"; item: any }>(
      `/api/clinical-rules/dose-limits/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  doseLimitDelete: (id: string) =>
    request<{ status: "ok" }>(
      `/api/clinical-rules/dose-limits/${id}`,
      { method: "DELETE" },
    ),
  aliasCreate: (body: any) =>
    request<{ status: "ok"; item: any }>(
      "/api/clinical-rules/aliases",
      { method: "POST", body: JSON.stringify(body) },
    ),
  aliasDelete: (id: string) =>
    request<{ status: "ok" }>(
      `/api/clinical-rules/aliases/${id}`,
      { method: "DELETE" },
    ),
  interactionCreate: (body: any) =>
    request<{ status: "ok"; item: any }>(
      "/api/clinical-rules/interactions",
      { method: "POST", body: JSON.stringify(body) },
    ),
  interactionUpdate: (id: string, body: any) =>
    request<{ status: "ok"; item: any }>(
      `/api/clinical-rules/interactions/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  interactionDelete: (id: string) =>
    request<{ status: "ok" }>(
      `/api/clinical-rules/interactions/${id}`,
      { method: "DELETE" },
    ),

  // ─── Revisão Clínica (regras auto_pending) ─────
  clinicalReviewPending: () =>
    request<{
      status: "ok";
      total_pending: number;
      by_table: Record<string, {
        label: string;
        table: string;
        count: number;
        items: any[];
      }>;
    }>("/api/clinical-rules/review/pending"),
  clinicalReviewApprove: (slug: string, rowId: string, notes?: string) =>
    request<{ status: "ok"; table: string; row_id: string }>(
      `/api/clinical-rules/review/${slug}/${rowId}/approve`,
      {
        method: "POST",
        body: JSON.stringify(notes ? { notes } : {}),
      },
    ),
  clinicalReviewReject: (slug: string, rowId: string, reason: string) =>
    request<{ status: "ok"; table: string; row_id: string }>(
      `/api/clinical-rules/review/${slug}/${rowId}/reject`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),

  // ─── Biometria de voz ────────────────────────────
  voiceCoverage: () =>
    request<{
      status: "ok";
      tenant_id: string;
      coverage: Record<string, {
        people_enrolled: number;
        samples_total: number;
        avg_quality?: number;
        last_enrollment?: string;
      }>;
    }>("/api/voice/coverage"),
  voiceListEnrollments: () =>
    request<{
      status: "ok";
      items: Array<{
        person_id: string;
        person_type: "caregiver" | "patient";
        full_name: string;
        sample_count: number;
        avg_quality: number | null;
        last_enrollment: string | null;
      }>;
    }>("/api/voice/enrollments"),
  voiceCaregiverEnroll: (body: {
    caregiver_id: string;
    audio_base64: string;
    sample_label?: string;
    sample_rate?: number;
  }) =>
    request<{
      success: boolean;
      message?: string;
      samples_count?: number;
      enrollment_complete?: boolean;
      quality_score?: number;
    }>("/api/voice/enroll", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  voiceCaregiverStatus: (caregiverId: string) =>
    request<{
      enrolled: boolean;
      sample_count: number;
      enrollment_complete: boolean;
      avg_quality?: number;
    }>(`/api/voice/enrollment/${caregiverId}`),
  voiceCaregiverDelete: (caregiverId: string) =>
    request<{ success: boolean; deleted_count?: number }>(
      `/api/voice/enrollment/${caregiverId}`,
      { method: "DELETE" },
    ),
  voicePatientEnroll: (body: {
    patient_id: string;
    audio_base64: string;
    sample_label?: string;
    sample_rate?: number;
  }) =>
    request<{
      success: boolean;
      message?: string;
      samples_count?: number;
      enrollment_complete?: boolean;
      quality_score?: number;
      person_type?: "patient";
    }>("/api/voice/patient/enroll", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  voicePatientStatus: (patientId: string) =>
    request<{
      enrolled: boolean;
      sample_count: number;
      enrollment_complete: boolean;
      person_type: "patient";
      avg_quality?: number;
    }>(`/api/voice/patient/enrollment/${patientId}`),
  voicePatientDelete: (patientId: string) =>
    request<{ success: boolean; deleted_count?: number }>(
      `/api/voice/patient/enrollment/${patientId}`,
      { method: "DELETE" },
    ),
  voiceListCaregivers: () =>
    request<{ caregivers: Array<{ id: string; full_name: string; phone?: string }> }>(
      "/api/caregivers",
    ),

  // ─── Plantões + phone_type ────────────────────
  shiftsList: () =>
    request<{
      status: "ok";
      shifts: Array<{
        id: string;
        caregiver_id: string;
        full_name: string;
        phone?: string;
        phone_type: "personal" | "shared" | "unknown";
        shift_name: string;
        starts_at: string;
        ends_at: string;
        weekdays: number[];
        active: boolean;
        notes?: string;
      }>;
    }>("/api/shifts"),
  shiftCreate: (body: {
    caregiver_id: string;
    shift_name: string;
    starts_at: string;
    ends_at: string;
    weekdays?: number[];
    notes?: string;
  }) =>
    request<{ status: "ok"; id: string }>("/api/shifts", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  shiftUpdate: (id: string, body: Record<string, any>) =>
    request<{ status: "ok" }>(`/api/shifts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  shiftDelete: (id: string) =>
    request<{ status: "ok" }>(`/api/shifts/${id}`, { method: "DELETE" }),
  caregiverPhoneType: (caregiverId: string, phoneType: "personal" | "shared" | "unknown") =>
    request<{ status: "ok"; phone_type: string }>(
      `/api/caregivers/${caregiverId}/phone-type`,
      { method: "PATCH", body: JSON.stringify({ phone_type: phoneType }) },
    ),
  shiftsCurrent: () =>
    request<{
      status: "ok";
      tenant_id: string;
      current_shift_name: string | null;
      active_caregivers: Array<{
        caregiver_id: string;
        full_name: string;
        phone?: string;
        phone_type: string;
        shift_name: string;
        source: "scheduled" | "override";
      }>;
      active_overrides: any[];
      pool_size: number;
    }>("/api/shifts/current"),
  shiftOverridesList: () =>
    request<{ status: "ok"; overrides: any[] }>("/api/shifts/overrides"),
  shiftOverrideCreate: (body: {
    caregiver_id: string;
    shift_name: string;
    valid_from: string;
    valid_until: string;
    reason?: string;
    created_by?: string;
  }) =>
    request<{ status: "ok"; override_id: string }>(
      "/api/shifts/overrides",
      { method: "POST", body: JSON.stringify(body) },
    ),

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

  // ───────── Safety Guardrail Layer ─────────
  safetyListQueue: (limit = 50) =>
    request<{
      status: "ok";
      count: number;
      items: SafetyQueueItem[];
    }>(`/api/safety/queue?limit=${limit}`),

  safetyDecideQueueItem: (
    qid: string,
    decision: "approved" | "rejected",
    notes?: string,
  ) =>
    request<{ status: "ok"; ok: boolean }>(
      `/api/safety/queue/${qid}/decide`,
      {
        method: "POST",
        body: JSON.stringify({ decision, notes: notes || null }),
      },
    ),

  safetyCircuitStatus: (tenantId?: string) =>
    request<SafetyCircuitState>(
      `/api/safety/circuit-breaker${tenantId ? `?tenant_id=${tenantId}` : ""}`,
    ),

  safetyCircuitReset: (tenantId?: string, reason?: string) =>
    request<{ status: "ok"; tenant_id: string }>(
      `/api/safety/circuit-breaker/reset`,
      {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId || null,
          reason: reason || null,
        }),
      },
    ),

  safetyStats: () =>
    request<{
      status: "ok";
      tenant_id: string;
      stats: {
        pending: number;
        approved: number;
        rejected: number;
        auto_executed: number;
        expired: number;
        last_24h: number;
        total: number;
      };
    }>(`/api/safety/stats`),

  // ───────── Patient Risk Scoring ─────────
  riskScoreGet: (patientId: string) =>
    request<{
      status: "ok";
      score?: number;
      level?: "low" | "moderate" | "high" | "critical";
      patient_id?: string;
      message?: string;
      breakdown?: Record<string, unknown>;
      complaints_7d?: number;
      adherence_pct?: number | null;
      urgent_events_7d?: number;
      trend?: string | null;
      computed_at?: string;
    }>(`/api/safety/risk-score/${patientId}`),

  riskScoreCompute: (patientId: string) =>
    request<{
      status: "ok";
      patient_id: string;
      score: number;
      level: string;
      breakdown: Record<string, unknown>;
    }>(`/api/safety/risk-score/${patientId}/compute`, { method: "POST" }),

  riskScoreHigh: (limit = 20) =>
    request<{
      status: "ok";
      count: number;
      items: PatientRiskRow[];
    }>(`/api/safety/risk-score/high?limit=${limit}`),

  riskScoreRecomputeAll: () =>
    request<{
      status: "ok";
      processed: number;
      by_level: { low: number; moderate: number; high: number; critical: number };
    }>(`/api/safety/risk-score/recompute-all`, { method: "POST" }),

  // Fase 2 — baseline individual
  riskBaselineGet: (patientId: string) =>
    request<{
      status: "ok";
      has_baseline: boolean;
      baseline?: PatientBaseline;
      message?: string;
    }>(`/api/safety/risk-score/${patientId}/baseline`),

  riskBaselineCompute: (patientId: string, periodDays?: number) =>
    request<{
      status: "ok";
      ok: boolean;
      patient_id: string;
      weeks_observed: number;
      has_sufficient_data: boolean;
      insufficient_reason: string | null;
      complaints: { median: number | null; mad: number | null; n: number };
      adherence: { median: number | null; mad: number | null; n: number };
      urgent: { median: number | null; mad: number | null; n: number };
    }>(`/api/safety/risk-score/${patientId}/baseline/compute`, {
      method: "POST",
      body: JSON.stringify(periodDays ? { period_days: periodDays } : {}),
    }),

  riskBaselineRecomputeAll: () =>
    request<{
      status: "ok";
      ok: boolean;
      processed: number;
      with_sufficient_data: number;
    }>(`/api/safety/risk-score/baseline/recompute-all`, { method: "POST" }),

  // ───────── Prompt versioning (cenários Sofia) ─────────
  scenarioVersionsList: (scenarioId: string) =>
    request<{
      status: "ok";
      count: number;
      items: ScenarioVersion[];
      current_version_id?: string | null;
    }>(`/api/communications/scenarios/${scenarioId}/versions`),

  scenarioVersionCreateDraft: (
    scenarioId: string,
    payload: {
      label?: string;
      description?: string | null;
      system_prompt: string;
      voice?: string;
      allowed_tools?: string[];
      post_call_actions?: string[];
      pre_call_context_sql?: string | null;
      max_duration_seconds?: number;
      notes?: string | null;
    },
  ) =>
    request<{ status: "ok"; version: ScenarioVersion }>(
      `/api/communications/scenarios/${scenarioId}/versions`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  scenarioVersionPromote: (
    scenarioId: string,
    versionId: string,
    target: "testing" | "published" | "archived",
  ) =>
    request<{ status: "ok"; version: ScenarioVersion }>(
      `/api/communications/scenarios/${scenarioId}/versions/${versionId}/promote`,
      { method: "POST", body: JSON.stringify({ target }) },
    ),

  // ───────── Drug Cascades (motor dim 13) ─────────
  cascadesList: () =>
    request<{ status: "ok"; count: number; items: DrugCascade[] }>(
      `/api/clinical-rules/cascades`,
    ),

  cascadesDetectForPatient: (patientId: string) =>
    request<{
      status: "ok";
      ok: boolean;
      patient_id: string;
      meds_count: number;
      cascades_detected: CascadeDetectionResult[];
    }>(`/api/patients/${patientId}/cascades`),

  // ───────── Proactive Caller ─────────
  proactiveCallerListDecisions: (params?: {
    patient_id?: string;
    decision?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.patient_id) qs.set("patient_id", params.patient_id);
    if (params?.decision) qs.set("decision", params.decision);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return request<{
      status: "ok";
      count: number;
      items: ProactiveDecisionRow[];
    }>(`/api/proactive-caller/decisions${q ? `?${q}` : ""}`);
  },

  proactiveCallerStats: () =>
    request<{
      status: "ok";
      tenant_id: string;
      stats: {
        total: number;
        will_call: number;
        failed: number;
        skipped: number;
        avg_score_called: number | null;
        avg_score_skipped: number | null;
      };
    }>(`/api/proactive-caller/stats`),

  proactiveCallerTriggerForPatient: (patientId: string, force = false) =>
    request<{ status: "ok"; decision: string }>(
      `/api/proactive-caller/trigger/${patientId}`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),

  proactiveCallerGetPatientSettings: (patientId: string) =>
    request<{ status: "ok"; settings: PatientCallSettings }>(
      `/api/proactive-caller/patient/${patientId}/settings`,
    ),

  proactiveCallerUpdatePatientSettings: (
    patientId: string,
    payload: Partial<Omit<PatientCallSettings, "id" | "full_name">>,
  ) =>
    request<{ status: "ok"; settings: PatientCallSettings }>(
      `/api/proactive-caller/patient/${patientId}/settings`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),
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
