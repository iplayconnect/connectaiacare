/**
 * API client — Wizard de cadastro do paciente.
 *
 * Cobre:
 *   • Sessão de cadastro (start / save / complete)
 *   • Lookups de bases curadas (CID-10, medicamento → classe)
 *   • Cross-validation condição × medicamento (prompts não-bloqueantes)
 *   • Verificação clínica de seções
 *
 * Acesso: super_admin, admin_tenant, medico, enfermeiro, cuidador_pro,
 * familia (para B2C/familiar). Verificação clínica restrita a
 * super_admin / medico / enfermeiro.
 */

import { api } from "./api";

// ─── Types ──────────────────────────────────────────────────────────

export type RegisteredByRole =
  | "paciente_b2c"
  | "familiar_responsavel"
  | "procurador"
  | "gestor_unidade"
  | "enfermeiro"
  | "medico";

export type RegistrationSection =
  | "demographics"
  | "conditions"
  | "medications"
  | "allergies"
  | "functional_baseline"
  | "responsibles";

export type ItemSource =
  | "self_declared"
  | "family_declared"
  | "procurador_declared"
  | "manager_declared"
  | "clinician_validated"
  | "imported_partner"
  | "imported_other";

export interface ClinicalItem {
  name: string;
  source?: ItemSource;
  declared_at?: string;
  declared_by_user_id?: string | null;
  verified_by_clinician_at?: string | null;
  verified_by_user_id?: string | null;
  /** Para condições. */
  cid10_code?: string | null;
  severity?: "leve" | "moderate" | "severe" | string;
  controlled?: boolean;
  /** Para medicamentos. */
  dose?: string;
  schedule?: string;
  therapeutic_class?: string;
  /** Notas livres. */
  notes?: string;
  [k: string]: any;
}

export interface PatientRegistrationState {
  status: "ok";
  patient: {
    id: string;
    full_name: string;
    conditions: ClinicalItem[];
    medications: ClinicalItem[];
    allergies: ClinicalItem[];
    responsible: any;
    completeness: {
      demographics?: "complete" | "partial" | "missing";
      conditions?: "complete" | "partial" | "missing";
      medications?: "complete" | "partial" | "missing";
      allergies?: "complete" | "partial" | "missing";
      responsibles?: "complete" | "partial" | "missing";
      functional_baseline?: "complete" | "partial" | "missing";
      completion_percentage?: number;
      last_updated_at?: string;
    };
    is_self_reporting: boolean | null;
    last_self_review_at: string | null;
  };
  active_session: null | {
    id: string;
    registered_by_user_id: string | null;
    registered_by_role: RegisteredByRole;
    last_completed_step: number;
    total_steps: number;
    status: "in_progress" | "complete" | "abandoned";
    started_at: string;
    completed_at: string | null;
    consent_lgpd_accepted_at: string | null;
  };
}

export interface Cid10SearchResult {
  code: string;
  description_pt: string;
  description_layman: string | null;
  category: string;
}

export interface MedicationLookupResult {
  id: string;
  active_ingredient: string;
  brand_names: string[];
  therapeutic_classes: string[];
  main_indications: string[];
}

export interface CrossValidationPrompt {
  condition_label: string;
  prompt_severity: "low" | "medium" | "high" | "critical";
  prompt_message: string;
  expected_therapeutic_classes: string[];
  found_classes: string[];
  response_options: any;
  clinical_rationale: string | null;
}

export interface CreatedPatient {
  id: string;
  full_name: string;
  nickname: string | null;
  cpf: string | null;
  tenant_id: string;
  created_at: string;
}

// ─── API ────────────────────────────────────────────────────────────

export const patientRegistrationApi = {
  // ── Criação de paciente novo (stub mínimo) ──
  createPatient: (payload: {
    full_name: string;
    nickname?: string;
    cpf?: string;
  }) =>
    api.request<{ status: "ok"; patient: CreatedPatient }>(
      "/api/patients",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // ── Lookups ──
  searchCid10: (q: string, limit = 20) =>
    api.request<{ status: "ok"; count: number; items: Cid10SearchResult[] }>(
      `/api/cid10/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),

  lookupMedication: (name: string) =>
    api.request<{ status: "ok"; match: MedicationLookupResult | null }>(
      `/api/medication-class/lookup?name=${encodeURIComponent(name)}`,
    ),

  validate: (conditions: ClinicalItem[], medications: ClinicalItem[]) =>
    api.request<{
      status: "ok";
      prompts_count: number;
      prompts: CrossValidationPrompt[];
    }>("/api/registration/validate", {
      method: "POST",
      body: JSON.stringify({ conditions, medications }),
    }),

  // ── Sessão ──
  getState: (patientId: string) =>
    api.request<PatientRegistrationState>(
      `/api/patients/${patientId}/registration`,
    ),

  start: (
    patientId: string,
    payload: {
      registered_by_role: RegisteredByRole;
      consent_lgpd_accepted?: boolean;
      consent_lgpd_ip?: string;
    },
  ) =>
    api.request<{ status: "ok"; session_id: string }>(
      `/api/patients/${patientId}/registration/start`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  saveStep: (
    patientId: string,
    payload: {
      section: RegistrationSection;
      data: any;
      step_number?: number;
    },
  ) =>
    api.request<{ status: "ok"; section: RegistrationSection }>(
      `/api/patients/${patientId}/registration/save`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  complete: (patientId: string) =>
    api.request<{ status: "ok" }>(
      `/api/patients/${patientId}/registration/complete`,
      { method: "POST" },
    ),

  // ── Verificação clínica ──
  verifySection: (
    patientId: string,
    section: RegistrationSection,
    notes?: string,
  ) =>
    api.request<{ status: "ok" }>(
      `/api/patients/${patientId}/verify/${section}`,
      { method: "POST", body: JSON.stringify({ notes: notes ?? null }) },
    ),
};

// ─── Helpers de UI ──────────────────────────────────────────────────

export const REGISTERED_BY_ROLE_LABEL: Record<RegisteredByRole, string> = {
  paciente_b2c: "Paciente (auto-declarado)",
  familiar_responsavel: "Familiar responsável",
  procurador: "Procurador legal",
  gestor_unidade: "Gestor da unidade",
  enfermeiro: "Enfermeiro(a)",
  medico: "Médico(a)",
};

export const ITEM_SOURCE_LABEL: Record<string, string> = {
  self_declared: "Auto-declarado",
  family_declared: "Declarado por familiar",
  procurador_declared: "Declarado por procurador",
  manager_declared: "Declarado pela equipe",
  clinician_validated: "Validado por clínico",
  imported_partner: "Importado (parceiro integrador)",
  imported_other: "Importado",
};

export const SEVERITY_BADGE: Record<string, { label: string; className: string }> = {
  low: {
    label: "Sugestão",
    className: "border-classification-routine/30 bg-classification-routine/10 text-classification-routine",
  },
  medium: {
    label: "Atenção",
    className: "border-classification-attention/30 bg-classification-attention/10 text-classification-attention",
  },
  high: {
    label: "Importante",
    className: "border-classification-urgent/30 bg-classification-urgent/10 text-classification-urgent",
  },
  critical: {
    label: "Crítico",
    className: "border-classification-critical/30 bg-classification-critical/10 text-classification-critical",
  },
};
