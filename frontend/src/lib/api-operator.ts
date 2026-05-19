/**
 * API client — Painel da Central 24/7 (Operador ATENT).
 *
 * Reusa o request() do api.ts pra autenticação JWT.
 */

import { api } from "./api";

// ─── Types ─────────────────────────────────────────────────────────

export interface OperatorState {
  user_id: string;
  is_online: boolean;
  last_heartbeat_at: string | null;
  current_shift_id: string | null;
  current_handoff_id: string | null;
  handoffs_handled_today: number;
  notes: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface OperatorShift {
  id: string;
  started_at: string;
  ended_at: string | null;
  handoffs_handled: number;
  duration_seconds: number | null;
}

export interface QueueItem {
  id: string;
  trace_id: string | null;
  phone: string;
  tenant_id: string | null;
  channel: string;
  reason: string;
  context_summary: string;
  triggered_by: string;
  priority: "P1" | "P2" | "P3";
  status: "pending" | "claimed" | "resolved" | "expired";
  handoff_type: "commercial" | "clinical" | "support" | "operator";
  patient_id: string | null;
  caregiver_id: string | null;
  claimed_at: string | null;
  claimed_by_user_id: string | null;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
  sla_target_seconds: number | null;
  sla_breached_at: string | null;
  notified_central_at: string | null;
  created_at: string;
  waiting_seconds: number;
}

export interface QueueStats {
  queue: {
    pending: number;
    claimed: number;
    p1_open: number;
    sla_breached: number;
    resolved_24h: number;
  };
  by_type: Record<string, number>;
  operators_online: number;
}

export interface PatientRecord {
  id: string;
  full_name: string | null;
  nickname: string | null;
  cpf: string | null;
  birth_date: string | null;
  gender: string | null;
  care_unit: string | null;
  room_number: string | null;
  care_level: string | null;
  conditions: any;
  medications: any;
  allergies: any;
  responsible: any;
  preferred_form_of_address: string | null;
  is_self_reporting: boolean | null;
  external_partner_patient_id: number | null;
  photo_url: string | null;
  notes: string | null;
}

export interface RecentEvent {
  id: string;
  event_type: string;
  current_classification: string;
  summary: string | null;
  reasoning: string | null;
  status: string;
  opened_at: string;
  resolved_at: string | null;
  caregiver_phone: string | null;
  event_tags: string[] | null;
}

export interface RecentVitalSign {
  id: string;
  vital_type: string;
  value_numeric: number | null;
  value_secondary: number | null;
  unit: string;
  status: string;
  source: string;
  measured_at: string;
  notes: string | null;
}

export interface CaregiverRef {
  id: string;
  full_name: string | null;
  phone: string;
  role: string | null;
  created_at: string;
}

export interface PatientContextResponse {
  status: "ok";
  handoff: QueueItem;
  patient: PatientRecord | null;
  recent_events: RecentEvent[];
  recent_vital_signs: RecentVitalSign[];
  caregivers: CaregiverRef[];
}

export interface HandoffMessage {
  id: string;
  direction: "inbound" | "outbound";
  text: string;
  author_user_id: string | null;
  author_name: string | null;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
}

// ─── API ────────────────────────────────────────────────────────────

export const operatorApi = {
  // ── State / shift ──
  getMe: () =>
    api.request<{
      status: "ok";
      operator: OperatorState;
      shift: OperatorShift | null;
      current_handoff: QueueItem | null;
    }>("/api/operator/me"),

  goOnline: () =>
    api.request<{ status: "ok"; shift_id: string }>("/api/operator/online", {
      method: "POST",
    }),

  goOffline: () =>
    api.request<{ status: "ok" }>("/api/operator/offline", { method: "POST" }),

  heartbeat: () =>
    api.request<{ status: "ok"; at: string }>("/api/operator/heartbeat", {
      method: "POST",
    }),

  // ── Queue ──
  getQueue: (params?: {
    status?: string;
    type?: string;
    priority?: string;
    mine?: boolean;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.type) qs.set("type", params.type);
    if (params?.priority) qs.set("priority", params.priority);
    if (params?.mine) qs.set("mine", "true");
    qs.set("limit", String(params?.limit ?? 50));
    return api.request<{
      status: "ok";
      count: number;
      items: QueueItem[];
    }>(`/api/operator/queue?${qs.toString()}`);
  },

  getQueueStats: () =>
    api.request<QueueStats & { status: "ok" }>("/api/operator/queue/stats"),

  // ── Handoff actions (cross-route — operator usa endpoints admin com role) ──
  claim: (handoffId: string) =>
    api.request<{ status: "ok" }>(
      `/api/admin/handoff/${handoffId}/claim`,
      { method: "POST" },
    ),

  resolve: (
    handoffId: string,
    payload: {
      outcome_category?: string;
      outcome_tags?: string[];
      resolution_summary?: string;
    },
  ) =>
    api.request<{ status: "ok" }>(
      `/api/admin/handoff/${handoffId}/resolve`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // ── Messages ──
  getMessages: (handoffId: string) =>
    api.request<{
      status: "ok";
      count: number;
      items: HandoffMessage[];
    }>(`/api/admin/handoff/${handoffId}/messages`),

  sendMessage: (handoffId: string, text: string) =>
    api.request<{ status: "ok"; id: string }>(
      `/api/admin/handoff/${handoffId}/send`,
      { method: "POST", body: JSON.stringify({ text }) },
    ),

  // ── Patient context (leitura privilegiada do paciente do handoff) ──
  getPatientContext: (handoffId: string) =>
    api.request<PatientContextResponse>(
      `/api/operator/handoff/${handoffId}/patient-context`,
    ),

  // ── Escalation ──
  escalateClinical: (
    handoffId: string,
    payload: { reason?: string; urgency?: "P1" | "P2" | "P3" },
  ) =>
    api.request<{
      status: "ok";
      from_handoff_id: string;
      to_handoff_id: string;
      urgency: string;
    }>(`/api/operator/handoff/${handoffId}/escalate-clinical`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
