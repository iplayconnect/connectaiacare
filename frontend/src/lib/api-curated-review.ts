/**
 * API client — Revisão das bases curadas (CIDs / Medicamentos / Cross-validation).
 *
 * Acesso: super_admin, admin_tenant, clinical_reviewer, medico, farmaceutico.
 */

import { api } from "./api";

// ─── Types ──────────────────────────────────────────────────────────

export type ReviewStatus = "draft" | "under_review" | "approved";
export type PromptSeverity = "low" | "medium" | "high" | "critical";

export interface CuratedStats {
  status: "ok";
  tables: {
    cid10: { total: number; draft: number; under_review: number; approved: number };
    medications: { total: number; draft: number; under_review: number; approved: number };
    expectations: { total: number; draft: number; under_review: number; approved: number };
  };
}

export interface Cid10Entry {
  code: string;
  description_pt: string;
  description_layman: string | null;
  description_en: string | null;
  category: string;
  review_status: ReviewStatus;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  reviewer_notes: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface MedicationEntry {
  id: string;
  active_ingredient: string;
  brand_names: string[];
  match_patterns: string[];
  therapeutic_classes: string[];
  main_indications: string[];
  notes: string | null;
  review_status: ReviewStatus;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  reviewer_notes: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ExpectationEntry {
  id: string;
  condition_label: string;
  cid10_code: string | null;
  condition_match_patterns: string[];
  expected_therapeutic_classes: string[];
  prompt_severity: PromptSeverity;
  prompt_message: string;
  response_options: any;
  clinical_rationale: string | null;
  active: boolean;
  review_status: ReviewStatus;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  reviewer_notes: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

// ─── API ────────────────────────────────────────────────────────────

export const curatedReviewApi = {
  stats: () => api.request<CuratedStats>("/api/admin/curated/stats"),

  // ── CID-10 ──
  listCid10: (params?: { status?: ReviewStatus; category?: string; q?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.category) qs.set("category", params.category);
    if (params?.q) qs.set("q", params.q);
    qs.set("limit", String(params?.limit ?? 200));
    return api.request<{ status: "ok"; count: number; items: Cid10Entry[] }>(
      `/api/admin/curated/cid10?${qs.toString()}`,
    );
  },

  updateCid10: (
    code: string,
    payload: Partial<{
      review_status: ReviewStatus;
      description_pt: string;
      description_layman: string;
      description_en: string;
      category: string;
      reviewer_notes: string;
    }>,
  ) =>
    api.request<{ status: "ok" }>(`/api/admin/curated/cid10/${code}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  cid10Categories: () =>
    api.request<{
      status: "ok";
      categories: { category: string; count: number }[];
    }>("/api/admin/curated/cid10/categories"),

  // ── Medications ──
  listMedications: (params?: {
    status?: ReviewStatus;
    q?: string;
    therapeutic_class?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.q) qs.set("q", params.q);
    if (params?.therapeutic_class) qs.set("therapeutic_class", params.therapeutic_class);
    qs.set("limit", String(params?.limit ?? 200));
    return api.request<{ status: "ok"; count: number; items: MedicationEntry[] }>(
      `/api/admin/curated/medications?${qs.toString()}`,
    );
  },

  updateMedication: (
    medId: string,
    payload: Partial<{
      review_status: ReviewStatus;
      active_ingredient: string;
      brand_names: string[];
      match_patterns: string[];
      therapeutic_classes: string[];
      main_indications: string[];
      notes: string;
      reviewer_notes: string;
    }>,
  ) =>
    api.request<{ status: "ok" }>(`/api/admin/curated/medications/${medId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  therapeuticClasses: () =>
    api.request<{
      status: "ok";
      classes: { class: string; count: number }[];
    }>("/api/admin/curated/medications/therapeutic-classes"),

  // ── Expectations (cross-validation) ──
  listExpectations: (params?: {
    status?: ReviewStatus;
    severity?: PromptSeverity;
    active?: boolean;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.active !== undefined) qs.set("active", String(params.active));
    qs.set("limit", String(params?.limit ?? 200));
    return api.request<{ status: "ok"; count: number; items: ExpectationEntry[] }>(
      `/api/admin/curated/expectations?${qs.toString()}`,
    );
  },

  updateExpectation: (
    expId: string,
    payload: Partial<{
      review_status: ReviewStatus;
      condition_label: string;
      cid10_code: string | null;
      condition_match_patterns: string[];
      expected_therapeutic_classes: string[];
      prompt_severity: PromptSeverity;
      prompt_message: string;
      response_options: any;
      clinical_rationale: string;
      active: boolean;
      reviewer_notes: string;
    }>,
  ) =>
    api.request<{ status: "ok" }>(`/api/admin/curated/expectations/${expId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
