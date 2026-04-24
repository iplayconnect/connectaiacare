/**
 * use-voip — cliente pra voip-service via backend proxy.
 *
 * Backend expõe:
 *   POST /api/voip/call                 — inicia chamada
 *   GET  /api/voip/call/:id/status      — status
 *   POST /api/voip/call/:id/hangup      — encerra
 *   GET  /api/voip/status               — disponibilidade
 *
 * O voip-service roda com Asterisk + Deepgram + ElevenLabs no container
 * voip-service:5010 (network infra_proxy). Ver backend/src/handlers/voip_routes.py.
 */

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export interface VoipCallPayload {
  destination: string; // telefone E.164 sem + (ex: "5511987654321")
  patient_id?: string;
  alert_id?: string;
  care_event_id?: string;
  alert_summary?: string;
  caller_name?: string;
  mode?: "ai_pipeline" | "manual";
}

export interface VoipCallResult {
  status: "ok" | "error";
  call_id?: string;
  call_status?: "initiated" | "dialing" | "connected" | "ended" | "failed";
  message?: string;
  reason?: string;
}

export async function startVoipCall(
  payload: VoipCallPayload,
): Promise<VoipCallResult> {
  try {
    const res = await fetch(`${API_BASE}/api/voip/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return (await res.json()) as VoipCallResult;
  } catch (err) {
    return {
      status: "error",
      message:
        err instanceof Error ? err.message : "Erro desconhecido ao chamar VoIP",
      reason: "network",
    };
  }
}

export async function getVoipCallStatus(callId: string): Promise<VoipCallResult> {
  try {
    const res = await fetch(`${API_BASE}/api/voip/call/${callId}/status`);
    return (await res.json()) as VoipCallResult;
  } catch (err) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Erro ao consultar status",
    };
  }
}

export async function hangupVoipCall(callId: string): Promise<VoipCallResult> {
  try {
    const res = await fetch(`${API_BASE}/api/voip/call/${callId}/hangup`, {
      method: "POST",
    });
    return (await res.json()) as VoipCallResult;
  } catch (err) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Erro ao encerrar",
    };
  }
}

export async function checkVoipAvailable(): Promise<{
  available: boolean;
  sip_registered?: boolean;
  active_calls?: number;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/voip/status`);
    return await res.json();
  } catch {
    return { available: false };
  }
}
