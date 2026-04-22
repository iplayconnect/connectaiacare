"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Heart, Loader2, Lock, ShieldCheck } from "lucide-react";

import { PortalContent } from "./portal-content";

type PortalData = {
  status: "ok";
  teleconsulta: {
    id: string;
    patient_full_name: string;
    patient_nickname: string | null;
    doctor_name: string | null;
    doctor_crm: string | null;
    signed_at: string | null;
    prescription: Array<{
      id: string;
      medication: string;
      dose?: string;
      schedule?: string;
      duration?: string;
      indication?: string;
    }>;
  };
  summary: {
    greeting?: string;
    what_happened?: string;
    main_findings?: string[];
    what_to_do_now?: Array<{ action: string; detail: string }>;
    medications_explained?: Array<{
      name: string;
      why: string;
      how_to_take: string;
      important?: string;
    }>;
    warning_signs?: string[];
    next_appointment?: string;
    supportive_message?: string;
  };
  prices: {
    results?: Array<{
      medication: string;
      offers: Array<{
        name: string;
        price_brl: number | null;
        pharmacy: string;
        url: string | null;
        notes: string;
      }>;
      confidence: string;
      notes_for_patient?: string;
      source?: string;
      source_url?: string;
    }>;
    error?: string;
  };
};

type State =
  | { phase: "pin" }
  | { phase: "validating" }
  | { phase: "locked" }
  | { phase: "expired" }
  | { phase: "revoked" }
  | { phase: "not_found" }
  | { phase: "ok"; data: PortalData };

const apiBase =
  (typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL
    : process.env.NEXT_PUBLIC_API_URL) || "";

export function PatientPortal({ teleconsultaId }: { teleconsultaId: string }) {
  const [state, setState] = useState<State>({ phase: "pin" });
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [attemptsLeft, setAttemptsLeft] = useState<number | null>(null);

  const submit = useCallback(
    async (pinValue: string) => {
      setError(null);
      setState({ phase: "validating" });
      try {
        const res = await fetch(
          `${apiBase}/api/patient-portal/${teleconsultaId}/access`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pin: pinValue }),
          },
        );
        const data = await res.json();

        if (res.ok && data.status === "ok") {
          setState({ phase: "ok", data });
          return;
        }
        const s = data.status;
        if (s === "invalid_pin") {
          setAttemptsLeft(data.attempts_remaining ?? null);
          setError(
            data.attempts_remaining != null
              ? `Código incorreto. ${data.attempts_remaining} tentativa${data.attempts_remaining === 1 ? "" : "s"} restante${data.attempts_remaining === 1 ? "" : "s"}.`
              : "Código incorreto.",
          );
          setPin("");
          setState({ phase: "pin" });
          return;
        }
        if (s === "locked") {
          setState({ phase: "locked" });
          return;
        }
        if (s === "expired") {
          setState({ phase: "expired" });
          return;
        }
        if (s === "revoked") {
          setState({ phase: "revoked" });
          return;
        }
        if (s === "not_found") {
          setState({ phase: "not_found" });
          return;
        }
        setError("Erro ao validar. Tente novamente em instantes.");
        setState({ phase: "pin" });
      } catch {
        setError("Erro de conexão. Verifique sua internet e tente novamente.");
        setState({ phase: "pin" });
      }
    },
    [teleconsultaId],
  );

  // ==============================================================
  // Render
  // ==============================================================
  if (state.phase === "ok") {
    return <PortalContent data={state.data} teleconsultaId={teleconsultaId} pin={pin} />;
  }

  if (state.phase === "locked") {
    return (
      <MessageScreen
        icon={<Lock className="h-10 w-10 text-classification-critical" />}
        title="Acesso temporariamente bloqueado"
        message="Foram feitas muitas tentativas com código incorreto. Entre em contato com a central de cuidadores para receber um novo código."
        tone="critical"
      />
    );
  }
  if (state.phase === "expired") {
    return (
      <MessageScreen
        icon={<AlertTriangle className="h-10 w-10 text-classification-attention" />}
        title="Link expirado"
        message="Este link ficou disponível por 24 horas. Para acessar o resumo da consulta novamente, entre em contato com a central de cuidadores."
        tone="attention"
      />
    );
  }
  if (state.phase === "revoked") {
    return (
      <MessageScreen
        icon={<AlertTriangle className="h-10 w-10 text-classification-attention" />}
        title="Acesso substituído"
        message="Um novo código foi enviado. Use a mensagem mais recente do WhatsApp para acessar."
        tone="attention"
      />
    );
  }
  if (state.phase === "not_found") {
    return (
      <MessageScreen
        icon={<AlertTriangle className="h-10 w-10 text-muted-foreground" />}
        title="Consulta não encontrada"
        message="O link que você usou parece estar incorreto. Verifique a mensagem enviada pelo WhatsApp."
        tone="neutral"
      />
    );
  }

  return (
    <PinScreen
      pin={pin}
      setPin={setPin}
      onSubmit={submit}
      validating={state.phase === "validating"}
      error={error}
      attemptsLeft={attemptsLeft}
    />
  );
}

// ═══════════════════════════════════════════════════════════════════
// PIN screen
// ═══════════════════════════════════════════════════════════════════

function PinScreen({
  pin,
  setPin,
  onSubmit,
  validating,
  error,
}: {
  pin: string;
  setPin: (v: string) => void;
  onSubmit: (p: string) => void;
  validating: boolean;
  error: string | null;
  attemptsLeft: number | null;
}) {
  const canSubmit = pin.length === 6 && !validating;

  return (
    <div className="min-h-screen flex items-center justify-center p-5 bg-gradient-to-br from-[#050b1f] via-[#0a1028] to-[#0d1f2b]">
      <div className="w-full max-w-sm">
        {/* Header de marca */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/15 border border-accent-cyan/30 flex items-center justify-center">
              <Heart className="h-5 w-5 text-accent-cyan" strokeWidth={2.5} />
            </div>
          </div>
          <h1 className="text-xl font-semibold mb-1">ConnectaIACare</h1>
          <p className="text-[13px] text-foreground/70">
            Portal do paciente e família
          </p>
        </div>

        <div className="glass-card rounded-2xl p-6 border border-white/[0.08]">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="h-5 w-5 text-accent-cyan" />
            <h2 className="text-base font-semibold">Acesso seguro</h2>
          </div>
          <p className="text-[13px] text-foreground/75 mb-5 leading-relaxed">
            Digite o código de 6 dígitos que chegou pelo WhatsApp para ver o
            resumo da consulta, a receita médica e os preços dos medicamentos.
          </p>

          <div className="mb-4">
            <label className="text-[12px] uppercase tracking-[0.1em] text-accent-cyan/80 font-semibold mb-2 block">
              Código de acesso
            </label>
            <input
              autoFocus
              value={pin}
              onChange={(e) =>
                setPin(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) onSubmit(pin);
              }}
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="000 000"
              className="w-full rounded-xl bg-black/40 border border-white/[0.08] px-4 py-4 text-2xl font-mono tracking-[0.3em] text-center focus:outline-none focus:border-accent-cyan/50 transition-colors"
              maxLength={6}
              disabled={validating}
            />
          </div>

          {error && (
            <div className="mb-4 text-[12px] text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-lg px-3 py-2 flex items-start gap-2">
              <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            onClick={() => onSubmit(pin)}
            disabled={!canSubmit}
            className="w-full px-4 py-3 rounded-xl bg-accent-cyan text-slate-900 text-sm font-semibold hover:bg-accent-teal transition-colors disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2 shadow-glow-cyan"
          >
            {validating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Verificando…
              </>
            ) : (
              <>
                <ShieldCheck className="h-4 w-4" />
                Acessar
              </>
            )}
          </button>

          <p className="text-[11px] text-foreground/55 mt-5 italic leading-relaxed text-center">
            O link expira em 24 horas. Sem o código, o acesso é bloqueado.
          </p>
        </div>

        <p className="text-[11px] text-foreground/50 mt-6 text-center">
          LGPD · CFM 2.314/2022 · Acesso auditado
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Mensagens de erro genéricas
// ═══════════════════════════════════════════════════════════════════

function MessageScreen({
  icon,
  title,
  message,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  message: string;
  tone: "critical" | "attention" | "neutral";
}) {
  const borderMap = {
    critical: "border-classification-critical/30",
    attention: "border-classification-attention/30",
    neutral: "border-white/[0.08]",
  };
  return (
    <div className="min-h-screen flex items-center justify-center p-5 bg-gradient-to-br from-[#050b1f] via-[#0a1028] to-[#0d1f2b]">
      <div
        className={`glass-card rounded-2xl p-6 max-w-sm text-center border ${borderMap[tone]}`}
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.04] mb-4">
          {icon}
        </div>
        <h2 className="text-lg font-semibold mb-2">{title}</h2>
        <p className="text-[13px] text-foreground/75 leading-relaxed">{message}</p>
      </div>
    </div>
  );
}
