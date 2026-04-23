/**
 * use-onboarding-web — hook do handshake Web → WhatsApp.
 *
 * Conecta no backend POST /api/onboarding/start-from-web criado na Onda B.
 *
 * Uso (Client Component, `'use client'`):
 *
 *   const { submit, status, result } = useOnboardingWeb();
 *
 *   async function onSubmit(formData) {
 *     const r = await submit(formData);
 *     if (r.status === 'ok') {
 *       // redirect pro whatsapp
 *       window.location.href = r.whatsapp_url;
 *     }
 *   }
 */

export interface WebOnboardingPayload {
  full_name: string;
  email: string;
  phone: string; // com ou sem DDI (backend normaliza)
  plan_sku: "essencial" | "familia" | "premium" | "premium_device";
  role?: "self" | "family" | "caregiver";
  utm_source?: string;
  utm_campaign?: string;
  utm_medium?: string;
  referrer?: string;
}

export interface WebOnboardingSuccess {
  status: "ok";
  session_id: string;
  whatsapp_url: string;
  whatsapp_message_preview: string;
  state: "collect_payer_cpf";
  plan_sku: string;
  plan_label: string;
}

export interface WebOnboardingError {
  status: "error";
  field?: string;
  message: string;
}

export type WebOnboardingResult = WebOnboardingSuccess | WebOnboardingError;

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export async function startOnboardingFromWeb(
  payload: WebOnboardingPayload,
): Promise<WebOnboardingResult> {
  try {
    const res = await fetch(`${API_BASE}/api/onboarding/start-from-web`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await res.json()) as WebOnboardingResult;
    return body;
  } catch (err) {
    return {
      status: "error",
      message:
        err instanceof Error ? err.message : "Erro desconhecido ao processar cadastro",
    };
  }
}

export async function getOnboardingSessionStatus(
  sessionId: string,
): Promise<{
  status: "ok" | "error";
  session_id?: string;
  state?: string;
  is_completed?: boolean;
  completed_at?: string | null;
  plan_sku?: string | null;
  last_activity_at?: string | null;
  message?: string;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/onboarding/session/${sessionId}`, {
      cache: "no-store",
    });
    return await res.json();
  } catch (err) {
    return {
      status: "error",
      message:
        err instanceof Error ? err.message : "Erro consultando sessão",
    };
  }
}

/**
 * Helper: extrai UTMs da URL atual (client-side) pra enriquecer o payload.
 */
export function extractUtmFromCurrentUrl(): Partial<WebOnboardingPayload> {
  if (typeof window === "undefined") return {};
  const params = new URLSearchParams(window.location.search);
  return {
    utm_source: params.get("utm_source") || undefined,
    utm_campaign: params.get("utm_campaign") || undefined,
    utm_medium: params.get("utm_medium") || undefined,
    referrer: document.referrer || undefined,
  };
}
