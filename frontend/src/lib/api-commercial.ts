/**
 * API client — Commercial Funnel (Phase D).
 *
 * Endpoints em backend/src/handlers/commercial_funnel_routes.py.
 * Reusa `request()` interno do api.ts via re-export pra manter
 * autenticação JWT consistente.
 */

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

import { getToken, clearAuth } from "./auth";
import { ApiError } from "./api";

function buildHeaders(init?: RequestInit): HeadersInit {
  const base: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = getToken();
    if (token) base["Authorization"] = `Bearer ${token}`;
  }
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
    clearAuth();
    if (!window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(
        window.location.pathname + window.location.search,
      );
      window.location.replace(`/login?next=${next}`);
    }
    throw new ApiError(401, "Não autenticado");
  }

  let body: any = null;
  try {
    body = await res.json();
  } catch {
    // resposta sem JSON (raro)
  }

  if (!res.ok) {
    throw new ApiError(
      res.status,
      body?.reason || body?.error || `HTTP ${res.status}`,
      body?.reason,
      body,
    );
  }
  return body as T;
}

// ─── Types ─────────────────────────────────────────────────────────

export interface CommercialPlan {
  id: string;
  sku: string;
  name: string;
  scope: "subscription_b2c" | "commercial_sales";
  target_persona:
    | "individual"
    | "familia"
    | "ilpi"
    | "clinica"
    | "hospital"
    | "parceiro"
    | null;
  target_segment: string | null;
  price_monthly_cents: number | null;
  price_setup_cents: number;
  currency: string;
  billing_period: string;
  max_patients: number | null;
  max_caregivers: number | null;
  max_messages_month: number | null;
  max_voice_minutes_month: number | null;
  daily_calls_count?: number;
  features: any;
  pitch_short: string | null;
  pitch_full: string | null;
  differentials: string[];
  active: boolean;
  public: boolean;
  requires_demo_to_close?: boolean;
  created_at?: string;
  updated_at?: string;
}

export type LeadStatus =
  | "new"
  | "qualified"
  | "demo_scheduled"
  | "in_demo"
  | "proposal_sent"
  | "converted"
  | "lost";

export interface FunnelLead {
  id: string;
  phone: string;
  full_name: string | null;
  organization: string | null;
  role_self_declared: string | null;
  intent: string;
  status: LeadStatus;
  qualification_score: number | null;
  demo_scheduled_at: string | null;
  last_contact_at: string | null;
  created_at: string;
  notes_count: number;
}

export interface FunnelData {
  status: "ok";
  columns: Record<LeadStatus, FunnelLead[]>;
  totals: Record<LeadStatus, number>;
  total: number;
}

export interface LeadDemo {
  id: string;
  scheduled_at: string;
  duration_minutes: number;
  meeting_url: string | null;
  meeting_provider: string | null;
  status: "scheduled" | "confirmed" | "completed" | "no_show" | "cancelled";
  completed_outcome: string | null;
  completed_summary: string | null;
  notes: string | null;
  created_at: string;
}

export interface LeadCall {
  id: string;
  direction: "inbound" | "outbound";
  called_by_actor: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  call_type: string;
  summary: string | null;
  outcome: string | null;
  sentiment: string | null;
  next_action: string | null;
  next_action_at: string | null;
}

export interface LeadProposal {
  id: string;
  plan_id: string;
  plan_sku: string;
  plan_name: string;
  custom_price_monthly_cents: number | null;
  custom_price_setup_cents: number | null;
  discount_percent: number | null;
  valid_until: string;
  proposal_url: string | null;
  sent_via: string | null;
  status: "sent" | "viewed" | "accepted" | "rejected" | "expired" | "withdrawn";
  sent_at: string;
  viewed_at: string | null;
  decided_at: string | null;
  decision_reason: string | null;
}

export interface LeadActivity {
  id: string;
  activity_type: string;
  actor_type: "sofia" | "human" | "system" | "lead";
  actor_name: string | null;
  summary: string;
  details: Record<string, any>;
  related_demo_id: string | null;
  related_call_id: string | null;
  related_proposal_id: string | null;
  importance: "minor" | "normal" | "important" | "critical";
  occurred_at: string;
}

export interface LeadTimeline {
  status: "ok";
  activities: LeadActivity[];
  demos: LeadDemo[];
  calls: LeadCall[];
  proposals: LeadProposal[];
}

export interface UpcomingDemo {
  id: string;
  lead_id: string;
  scheduled_at: string;
  duration_minutes: number;
  status: string;
  meeting_url: string | null;
  meeting_provider: string | null;
  assigned_to_user_id: string | null;
  phone: string;
  full_name: string | null;
  organization: string | null;
  qualification_score: number | null;
}

export interface UpcomingCallback {
  id: string;
  lead_id: string;
  next_action_at: string;
  call_type: string;
  summary: string | null;
  phone: string;
  full_name: string | null;
  organization: string | null;
  qualification_score: number | null;
}

// ─── API ────────────────────────────────────────────────────────────

export const commercialApi = {
  // ─── Plans ───
  listPlans: (params?: {
    scope?: "subscription_b2c" | "commercial_sales" | "all";
    target_persona?: string;
    active?: boolean;
    public_only?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params?.scope) qs.set("scope", params.scope);
    if (params?.target_persona) qs.set("target_persona", params.target_persona);
    if (params?.active !== undefined)
      qs.set("active", String(params.active));
    if (params?.public_only !== undefined)
      qs.set("public_only", String(params.public_only));
    const query = qs.toString();
    return request<{
      status: "ok";
      count: number;
      items: CommercialPlan[];
    }>(`/api/admin/plans${query ? `?${query}` : ""}`);
  },

  createPlan: (payload: Partial<CommercialPlan>) =>
    request<{ status: "ok"; id: string }>("/api/admin/plans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updatePlan: (planId: string, payload: Partial<CommercialPlan>) =>
    request<{ status: "ok" }>(`/api/admin/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ─── Funnel ───
  funnelKanban: (days = 60) =>
    request<FunnelData>(`/api/admin/leads/funnel?days=${days}`),

  // ─── Lead detail / timeline ───
  leadTimeline: (leadId: string) =>
    request<LeadTimeline>(`/api/admin/leads/${leadId}/timeline`),

  // ─── Update lead (drag-drop kanban, etc.) ───
  updateLead: (
    leadId: string,
    payload: Partial<{
      status: LeadStatus;
      qualification_score: number;
      demo_scheduled_at: string;
      demo_link: string;
      lost_reason: string;
      full_name: string;
      email: string;
      organization: string;
      role_self_declared: string;
      intent: string;
      last_contact_at: string;
    }>,
  ) =>
    request<{ status: "ok" }>(`/api/admin/leads/${leadId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  createLeadManual: (payload: {
    phone: string;
    full_name?: string;
    email?: string;
    organization?: string;
    role_self_declared?: string;
    intent?: string;
    source_channel?: string;
    qualification_score?: number;
    status?: string;
  }) =>
    request<{ status: "ok"; id: string }>("/api/admin/leads", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ─── Demos ───
  createDemo: (
    leadId: string,
    payload: {
      scheduled_at: string;
      duration_minutes?: number;
      timezone?: string;
      meeting_url?: string;
      meeting_provider?: string;
      plan_focus_id?: string;
      notes?: string;
      assigned_to_user_id?: string;
    },
  ) =>
    request<{ status: "ok"; id: string }>(
      `/api/admin/leads/${leadId}/demos`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  updateDemo: (
    demoId: string,
    payload: Partial<{
      scheduled_at: string;
      duration_minutes: number;
      meeting_url: string;
      meeting_provider: string;
      plan_focus_id: string;
      notes: string;
      status: string;
      completed_outcome: string;
      completed_summary: string;
      follow_up_at: string;
      assigned_to_user_id: string;
    }>,
  ) =>
    request<{ status: "ok" }>(`/api/admin/lead-demos/${demoId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ─── Calls ───
  registerCall: (
    leadId: string,
    payload: {
      direction?: "inbound" | "outbound";
      called_by_actor?: string;
      started_at: string;
      ended_at?: string;
      duration_seconds?: number;
      call_type?: string;
      transcript?: string;
      summary?: string;
      outcome?: string;
      sentiment?: string;
      next_action?: string;
      next_action_at?: string;
      recording_url?: string;
      recording_consent?: boolean;
    },
  ) =>
    request<{ status: "ok"; id: string }>(
      `/api/admin/leads/${leadId}/calls`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // ─── Proposals ───
  createProposal: (
    leadId: string,
    payload: {
      plan_id?: string;
      plan_sku?: string;
      custom_price_monthly_cents?: number;
      custom_price_setup_cents?: number;
      custom_features?: any;
      discount_percent?: number;
      valid_until?: string;
      proposal_url?: string;
      proposal_html?: string;
      sent_via?: string;
    },
  ) =>
    request<{ status: "ok"; id: string }>(
      `/api/admin/leads/${leadId}/proposals`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  updateProposal: (
    proposalId: string,
    payload: {
      status?: LeadProposal["status"];
      decision_reason?: string;
      viewed_at?: string;
      decided_at?: string;
      converted_to_tenant_id?: string;
    },
  ) =>
    request<{ status: "ok" }>(`/api/admin/lead-proposals/${proposalId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ─── Agenda ───
  upcomingDemos: (days = 14) =>
    request<{ status: "ok"; count: number; items: UpcomingDemo[] }>(
      `/api/admin/leads/upcoming-demos?days=${days}`,
    ),

  upcomingCallbacks: (days = 7) =>
    request<{ status: "ok"; count: number; items: UpcomingCallback[] }>(
      `/api/admin/leads/upcoming-callbacks?days=${days}`,
    ),
};
