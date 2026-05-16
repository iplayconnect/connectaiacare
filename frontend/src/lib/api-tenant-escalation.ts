/**
 * Cliente API — Contatos de escalação por tenant.
 *
 * Backend: backend/src/handlers/tenant_escalation_routes.py (migration 080)
 * Quem usa: admin_tenant (próprio tenant), super_admin (qualquer).
 */

import { api } from "./api";

export type EscalationPriority = "P1" | "P2" | "P3";

export type EscalationRole =
  | "plantonista_l1"
  | "plantonista_l2"
  | "medico_responsavel"
  | "enfermeiro_chefe"
  | "gestor_unidade"
  | "admin_tenant"
  | "outro";

export const ESCALATION_ROLE_LABEL: Record<EscalationRole, string> = {
  plantonista_l1: "Plantonista L1 (triagem técnica)",
  plantonista_l2: "Plantonista L2 (clínico)",
  medico_responsavel: "Médico responsável",
  enfermeiro_chefe: "Enfermeiro(a) chefe",
  gestor_unidade: "Gestor da unidade",
  admin_tenant: "Admin do tenant",
  outro: "Outro",
};

export interface EscalationContact {
  id: string;
  tenant_id: string;
  phone: string;
  contact_name: string;
  role: EscalationRole;
  priorities: EscalationPriority[];
  active: boolean;
  schedule_weekdays: number[] | null;
  schedule_start: string | null; // "HH:MM:SS"
  schedule_end: string | null;
  notes: string | null;
  created_at: string;
  created_by_user_id: string | null;
  updated_at: string;
  updated_by_user_id: string | null;
  deactivated_at: string | null;
  deactivated_by_user_id: string | null;
}

export interface CreateEscalationContactPayload {
  phone: string;
  contact_name: string;
  role: EscalationRole;
  priorities: EscalationPriority[];
  notes?: string | null;
  schedule_weekdays?: number[] | null;
  schedule_start?: string | null;
  schedule_end?: string | null;
}

export type UpdateEscalationContactPayload = Partial<
  CreateEscalationContactPayload & { active: boolean }
>;

export const tenantEscalationApi = {
  list: (tenantId: string, opts?: { include_inactive?: boolean }) => {
    const qs = opts?.include_inactive ? "?include_inactive=true" : "";
    return api.request<{
      status: "ok";
      tenant_id: string;
      count: number;
      contacts: EscalationContact[];
    }>(`/api/admin/tenants/${tenantId}/escalation-contacts${qs}`);
  },

  create: (tenantId: string, payload: CreateEscalationContactPayload) =>
    api.request<{ status: "ok"; contact: EscalationContact }>(
      `/api/admin/tenants/${tenantId}/escalation-contacts`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  update: (
    tenantId: string,
    contactId: string,
    payload: UpdateEscalationContactPayload,
  ) =>
    api.request<{ status: "ok"; contact: EscalationContact }>(
      `/api/admin/tenants/${tenantId}/escalation-contacts/${contactId}`,
      { method: "PATCH", body: JSON.stringify(payload) },
    ),

  deactivate: (tenantId: string, contactId: string) =>
    api.request<{ status: "ok" }>(
      `/api/admin/tenants/${tenantId}/escalation-contacts/${contactId}`,
      { method: "DELETE" },
    ),
};

// ─── Helpers UI ─────────────────────────────────────────────────────

/**
 * Phone E.164 sem '+' (5551992345678) → "+55 (51) 99234-5678".
 * Aceita 12 ou 13 dígitos (com ou sem o 9 do celular).
 */
export function formatPhoneBR(raw: string): string {
  const d = (raw || "").replace(/\D/g, "");
  if (d.length === 13) {
    return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 9)}-${d.slice(9)}`;
  }
  if (d.length === 12) {
    return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 8)}-${d.slice(8)}`;
  }
  return raw;
}

/**
 * Máscara live enquanto user digita (formato display).
 * Sem o '+', porque é mais natural.
 */
export function maskPhoneInput(raw: string): string {
  const d = (raw || "").replace(/\D/g, "").slice(0, 13);
  if (d.length === 0) return "";
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)} (${d.slice(2)}`;
  if (d.length <= 9) return `${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4)}`;
  return `${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 9)}-${d.slice(9)}`;
}

const WEEKDAY_SHORT = ["", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

export function formatSchedule(c: EscalationContact): string {
  const hasTime = c.schedule_start && c.schedule_end;
  const hasDays = c.schedule_weekdays && c.schedule_weekdays.length > 0;
  if (!hasTime && !hasDays) return "24/7";
  const days = hasDays
    ? c.schedule_weekdays!
        .slice()
        .sort()
        .map((d) => WEEKDAY_SHORT[d] || `?${d}`)
        .join(", ")
    : "Todos os dias";
  const time = hasTime ? `${c.schedule_start!.slice(0, 5)}–${c.schedule_end!.slice(0, 5)}` : "24h";
  return `${days} · ${time}`;
}
