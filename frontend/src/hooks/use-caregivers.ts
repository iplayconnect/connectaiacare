/**
 * use-caregivers — cliente pros endpoints /api/caregivers.
 */

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export type CaregiverRole =
  | "cuidador"
  | "enfermagem"
  | "tecnico"
  | "coordenador"
  | "medico";

export type CaregiverShift =
  | "manha"
  | "tarde"
  | "noite"
  | "12x36"
  | "24h"
  | "plantao"
  | "flexivel";

export interface Caregiver {
  id: string;
  full_name: string;
  cpf: string | null;
  phone: string | null;
  role: CaregiverRole;
  shift: CaregiverShift | null;
  active: boolean;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CreateCaregiverPayload {
  full_name: string;
  cpf?: string;
  phone?: string;
  role?: CaregiverRole;
  shift?: CaregiverShift;
  metadata?: Record<string, unknown>;
}

export async function listCaregivers(params?: {
  role?: CaregiverRole;
  shift?: CaregiverShift;
  active?: boolean;
  q?: string;
}): Promise<{ caregivers: Caregiver[]; total: number }> {
  const qs = new URLSearchParams();
  if (params?.role) qs.set("role", params.role);
  if (params?.shift) qs.set("shift", params.shift);
  if (params?.active !== undefined) qs.set("active", String(params.active));
  if (params?.q) qs.set("q", params.q);

  const url = `${API_BASE}/api/caregivers${qs.toString() ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) return { caregivers: [], total: 0 };
  return res.json();
}

export async function createCaregiver(
  payload: CreateCaregiverPayload,
): Promise<{ status: "ok" | "error"; caregiver?: Caregiver; field?: string; message?: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/caregivers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (err) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Erro de rede",
    };
  }
}

export async function deactivateCaregiver(id: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/caregivers/${id}`, {
      method: "DELETE",
    });
    return res.ok;
  } catch {
    return false;
  }
}
