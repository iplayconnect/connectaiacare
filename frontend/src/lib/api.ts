/**
 * API client para ConnectaIACare backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

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
  patient_name?: string;
  patient_photo?: string;
  patient_room?: string;
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

export const api = {
  listPatients: () => request<{ patients: Patient[] }>("/api/patients"),
  getPatient: (id: string) =>
    request<{ patient: Patient; reports: Report[] }>(`/api/patients/${id}`),
  listReports: (limit = 50) =>
    request<{ reports: Report[] }>(`/api/reports?limit=${limit}`),
  getReport: (id: string) => request<{ report: Report }>(`/api/reports/${id}`),
  dashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),
};
