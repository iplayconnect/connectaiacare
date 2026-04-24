"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  CheckCircle2,
  Delete,
  Phone,
  PhoneOff,
  Sparkles,
  X,
} from "lucide-react";

import type { ClinicalAlert } from "@/hooks/use-alerts";

export type CallLifecycle =
  | { stage: "idle" }
  | { stage: "dialing"; call_id?: string; target?: string; started_at: number }
  | { stage: "connected"; call_id?: string; target?: string; started_at: number }
  | { stage: "ended"; call_id?: string; target?: string; duration_s: number }
  | { stage: "failed"; message: string };

interface Props {
  alert: ClinicalAlert;
  callLifecycle: CallLifecycle;
  onConfirm: (finalPhone: string) => void; // iniciar chamada
  onHangup: () => void;                    // encerrar chamada em curso
  onCancel: () => void;                    // fechar modal (só quando idle ou ended/failed)
}

/**
 * Dialpad + estado de chamada em 1 modal.
 *
 * Lifecycle visual:
 *   idle       → teclado completo + botão verde "Ligar"
 *   dialing    → display animado "Chamando..." + timer + botão vermelho "Encerrar"
 *   connected  → "Em chamada" + timer + botão "Encerrar"
 *   ended      → "Chamada encerrada" + duração + botão "Fechar"
 *   failed     → erro visível + botão "Fechar"
 *
 * Parent (AlertsPanel) gerencia a chamada e atualiza callLifecycle.
 */
export function CallConfirmModal({
  alert,
  callLifecycle,
  onConfirm,
  onHangup,
  onCancel,
}: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const defaultPhone = alert.patient.family_contact?.phone ?? "";
  const [phone, setPhone] = useState<string>(defaultPhone);

  const isActive =
    callLifecycle.stage === "dialing" || callLifecycle.stage === "connected";

  // Lock scroll + Esc (só quando idle/ended/failed)
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isActive) onCancel();
      if (callLifecycle.stage !== "idle") return;
      if (e.key === "Backspace") setPhone((p) => p.slice(0, -1));
      else if (/^[0-9*#+]$/.test(e.key)) setPhone((p) => p + e.key);
      else if (e.key === "Enter" && phone.replace(/\D/g, "").length >= 10) {
        onConfirm(phone.replace(/\D/g, ""));
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", handler);
    };
  }, [onCancel, onConfirm, phone, callLifecycle.stage, isActive]);

  if (!mounted) return null;

  const contact = alert.patient.family_contact;
  const phoneDigits = phone.replace(/\D/g, "");
  const canCall = phoneDigits.length >= 10;
  const phoneDisplay = formatPhone(phoneDigits);

  const pressKey = (k: string) => setPhone((p) => p + k);
  const backspace = () => setPhone((p) => p.slice(0, -1));
  const clearAll = () => setPhone("");

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4"
      style={{ animation: "fade-in 180ms ease" }}
    >
      <div
        onClick={!isActive ? onCancel : undefined}
        className="absolute inset-0 bg-black/60 backdrop-blur-md"
        aria-hidden
      />

      <div
        role="dialog"
        aria-label="Dialpad Sofia Voz"
        aria-modal="true"
        className="relative w-full max-w-[380px] glass-card rounded-3xl shadow-2xl overflow-hidden"
        style={{
          borderColor: borderColorForStage(callLifecycle.stage),
          animation: "slide-in-up 280ms cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        <Header alert={alert} callLifecycle={callLifecycle} onClose={onCancel} isActive={isActive} />

        {/* Corpo muda conforme lifecycle */}
        {callLifecycle.stage === "idle" && (
          <IdleBody
            contact={contact}
            phone={phone}
            phoneDigits={phoneDigits}
            phoneDisplay={phoneDisplay}
            canCall={canCall}
            onPressKey={pressKey}
            onBackspace={backspace}
            onClear={clearAll}
            onCall={() => canCall && onConfirm(phoneDigits)}
            onPhoneChange={setPhone}
          />
        )}

        {(callLifecycle.stage === "dialing" ||
          callLifecycle.stage === "connected") && (
          <ActiveCallBody
            stage={callLifecycle.stage}
            target={callLifecycle.target}
            startedAt={callLifecycle.started_at}
            phoneDisplay={phoneDisplay || defaultPhone}
            onHangup={onHangup}
          />
        )}

        {callLifecycle.stage === "ended" && (
          <EndedBody
            target={callLifecycle.target}
            durationS={callLifecycle.duration_s}
            onClose={onCancel}
          />
        )}

        {callLifecycle.stage === "failed" && (
          <FailedBody message={callLifecycle.message} onClose={onCancel} />
        )}

        {/* Contexto do alerta no rodapé (SEMPRE visível) */}
        <AlertContext alert={alert} />

        <p className="px-5 pb-3 pt-2 text-[10px] text-muted-foreground/60 italic text-center leading-relaxed">
          Sofia Voz via Asterisk + IA contextualizada (Deepgram + ElevenLabs)
        </p>
      </div>
    </div>,
    document.body,
  );
}

// ══════════════════════════════════════════════════════════════════
// Header (muda por estágio)
// ══════════════════════════════════════════════════════════════════

function Header({
  alert,
  callLifecycle,
  onClose,
  isActive,
}: {
  alert: ClinicalAlert;
  callLifecycle: CallLifecycle;
  onClose: () => void;
  isActive: boolean;
}) {
  const header = headerLabelForStage(callLifecycle.stage);

  return (
    <header className={`flex items-center justify-between px-5 py-3.5 border-b border-white/10 bg-gradient-to-b ${headerBgForStage(callLifecycle.stage)}`}>
      <div className="min-w-0 flex-1">
        <div
          className={`text-[10px] uppercase tracking-[0.16em] font-bold ${header.color}`}
        >
          {header.title}
        </div>
        <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
          {alert.patient.name}
        </div>
      </div>
      <button
        onClick={onClose}
        disabled={isActive}
        aria-label="Fechar"
        title={isActive ? "Encerre a chamada antes de fechar" : "Fechar"}
        className="w-8 h-8 rounded-lg border border-white/10 bg-white/5 text-foreground/80 grid place-items-center hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </header>
  );
}

function headerLabelForStage(stage: CallLifecycle["stage"]): { title: string; color: string } {
  switch (stage) {
    case "dialing":
      return { title: "Chamando Sofia Voz…", color: "text-classification-urgent" };
    case "connected":
      return { title: "Chamada em andamento", color: "text-classification-routine" };
    case "ended":
      return { title: "Chamada encerrada", color: "text-muted-foreground" };
    case "failed":
      return { title: "Falha na chamada", color: "text-classification-critical" };
    default:
      return { title: "Sofia Voz · Família", color: "text-classification-urgent" };
  }
}

function headerBgForStage(stage: CallLifecycle["stage"]): string {
  switch (stage) {
    case "dialing":
      return "from-classification-urgent/12 to-transparent";
    case "connected":
      return "from-classification-routine/12 to-transparent";
    case "ended":
      return "from-white/5 to-transparent";
    case "failed":
      return "from-classification-critical/10 to-transparent";
    default:
      return "from-classification-urgent/10 to-transparent";
  }
}

function borderColorForStage(stage: CallLifecycle["stage"]): string {
  switch (stage) {
    case "dialing":
      return "rgba(251, 146, 60, 0.55)";
    case "connected":
      return "rgba(52, 211, 153, 0.55)";
    case "ended":
      return "rgba(148, 163, 184, 0.25)";
    case "failed":
      return "rgba(239, 68, 68, 0.55)";
    default:
      return "rgba(251, 146, 60, 0.35)";
  }
}

// ══════════════════════════════════════════════════════════════════
// IdleBody — dialpad completo (pré-chamada)
// ══════════════════════════════════════════════════════════════════

function IdleBody({
  contact,
  phone,
  phoneDigits,
  phoneDisplay,
  canCall,
  onPressKey,
  onBackspace,
  onClear,
  onCall,
  onPhoneChange,
}: {
  contact?: ClinicalAlert["patient"]["family_contact"];
  phone: string;
  phoneDigits: string;
  phoneDisplay: string;
  canCall: boolean;
  onPressKey: (k: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  onCall: () => void;
  onPhoneChange: (v: string) => void;
}) {
  return (
    <>
      <div className="px-5 pt-6 pb-4 text-center">
        {contact && (
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
            {contact.name}
          </div>
        )}
        <div className="min-h-[52px] flex items-center justify-center">
          {phoneDigits.length === 0 ? (
            <div className="text-2xl text-muted-foreground/40 font-mono tabular italic">
              Digite o número
            </div>
          ) : (
            <input
              type="tel"
              value={phoneDisplay || phone}
              onChange={(e) => onPhoneChange(e.target.value)}
              className="bg-transparent text-3xl font-bold font-mono tabular text-foreground tracking-tight text-center w-full outline-none"
            />
          )}
        </div>
        {phoneDigits.length > 0 && phoneDigits.length < 10 && (
          <div className="text-[11px] text-muted-foreground mt-1">
            Faltam {10 - phoneDigits.length} dígito{10 - phoneDigits.length > 1 ? "s" : ""}
          </div>
        )}
      </div>

      <div className="px-5 pb-3">
        <div className="grid grid-cols-3 gap-2">
          {([
            { d: "1", l: "" },
            { d: "2", l: "ABC" },
            { d: "3", l: "DEF" },
            { d: "4", l: "GHI" },
            { d: "5", l: "JKL" },
            { d: "6", l: "MNO" },
            { d: "7", l: "PQRS" },
            { d: "8", l: "TUV" },
            { d: "9", l: "WXYZ" },
            { d: "*", l: "" },
            { d: "0", l: "+" },
            { d: "#", l: "" },
          ] as const).map(({ d, l }) => (
            <button
              key={d}
              onClick={() => onPressKey(d)}
              className="aspect-square rounded-xl bg-white/5 hover:bg-white/10 active:bg-accent-cyan/15 active:scale-95 border border-white/5 transition-all flex flex-col items-center justify-center"
              aria-label={`Tecla ${d}`}
            >
              <span className="text-2xl font-bold font-mono">{d}</span>
              {l && (
                <span className="text-[9px] text-muted-foreground/70 uppercase tracking-[0.15em] mt-0.5 font-semibold">
                  {l}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-2 mt-2">
          <button
            onClick={onClear}
            disabled={phoneDigits.length === 0}
            className="py-2 rounded-xl text-[11px] font-semibold uppercase tracking-wider border border-white/5 bg-white/[0.02] text-foreground/60 hover:bg-white/5 disabled:opacity-30 transition-colors"
          >
            Limpar
          </button>
          <button
            onClick={onCall}
            disabled={!canCall}
            className="py-2.5 rounded-xl font-bold transition-all flex items-center justify-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              background: canCall
                ? "linear-gradient(135deg, #34d399 0%, #14b8a6 100%)"
                : "rgba(52, 211, 153, 0.15)",
              color: canCall ? "#050b1f" : "rgba(52, 211, 153, 0.5)",
              boxShadow: canCall ? "0 0 24px rgba(52, 211, 153, 0.45)" : "none",
            }}
            aria-label="Ligar"
          >
            <Phone className="h-4 w-4" strokeWidth={2.5} />
            <span className="text-sm">Ligar</span>
          </button>
          <button
            onClick={onBackspace}
            disabled={phoneDigits.length === 0}
            className="py-2 rounded-xl text-foreground/60 hover:text-foreground hover:bg-white/5 disabled:opacity-30 transition-colors flex items-center justify-center"
            aria-label="Apagar último dígito"
          >
            <Delete className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════
// ActiveCallBody — chamada em andamento
// ══════════════════════════════════════════════════════════════════

function ActiveCallBody({
  stage,
  target,
  startedAt,
  phoneDisplay,
  onHangup,
}: {
  stage: "dialing" | "connected";
  target?: string;
  startedAt: number;
  phoneDisplay: string;
  onHangup: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    intervalRef.current = setInterval(tick, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [startedAt]);

  const isDialing = stage === "dialing";
  const color = isDialing ? "#fb923c" : "#34d399";
  const label = isDialing ? "Chamando" : "Em chamada";

  return (
    <div className="px-5 py-8 text-center">
      {/* Avatar animado */}
      <div className="relative w-24 h-24 mx-auto mb-4">
        {/* Ondas */}
        {isDialing && (
          <>
            <span
              className="absolute inset-0 rounded-full"
              style={{
                border: `2px solid ${color}`,
                animation: "ring-pulse 1.8s ease-out infinite",
                opacity: 0.4,
              }}
            />
            <span
              className="absolute inset-0 rounded-full"
              style={{
                border: `2px solid ${color}`,
                animation: "ring-pulse 1.8s ease-out infinite",
                animationDelay: "0.6s",
                opacity: 0.3,
              }}
            />
          </>
        )}
        <div
          className="relative w-24 h-24 rounded-full flex items-center justify-center"
          style={{
            background: `radial-gradient(circle, ${color}33 0%, transparent 70%)`,
            boxShadow: `0 0 40px ${color}55`,
          }}
        >
          <Phone
            className="h-10 w-10"
            strokeWidth={2.5}
            style={{ color }}
          />
        </div>
      </div>

      {/* Label */}
      <div
        className="text-[10px] uppercase tracking-[0.2em] font-bold mb-1"
        style={{ color }}
      >
        {label}
      </div>

      {/* Nome do contato */}
      <div className="text-lg font-bold text-foreground truncate">
        {target || phoneDisplay || "Família"}
      </div>

      {/* Telefone */}
      <div className="text-sm font-mono tabular text-muted-foreground mt-0.5">
        {phoneDisplay}
      </div>

      {/* Timer */}
      <div className="mt-4 text-3xl font-bold tabular" style={{ color }}>
        {formatDuration(elapsed)}
      </div>

      {/* Botão encerrar */}
      <button
        onClick={onHangup}
        className="mt-6 inline-flex items-center gap-2 px-5 py-3 rounded-xl font-bold text-sm transition-all hover:scale-105"
        style={{
          background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
          color: "#fff",
          boxShadow: "0 0 24px rgba(239, 68, 68, 0.4)",
        }}
      >
        <PhoneOff className="h-4 w-4" strokeWidth={2.5} />
        Encerrar chamada
      </button>

      {/* Status live */}
      <div className="mt-3 flex items-center justify-center gap-1.5 text-[10px] text-muted-foreground">
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse"
          style={{ background: color }}
        />
        <span>
          {isDialing
            ? "Conectando via Asterisk…"
            : "Sofia + paciente em linha"}
        </span>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// EndedBody — chamada terminou
// ══════════════════════════════════════════════════════════════════

function EndedBody({
  target,
  durationS,
  onClose,
}: {
  target?: string;
  durationS: number;
  onClose: () => void;
}) {
  return (
    <div className="px-5 py-6 text-center">
      <div className="w-16 h-16 rounded-full mx-auto mb-3 bg-classification-routine/15 border border-classification-routine/30 flex items-center justify-center">
        <CheckCircle2 className="h-8 w-8 text-classification-routine" strokeWidth={2.5} />
      </div>
      <div className="text-base font-bold">Chamada encerrada</div>
      {target && (
        <div className="text-sm text-muted-foreground mt-0.5">{target}</div>
      )}
      <div className="mt-3 text-2xl font-bold font-mono tabular text-foreground">
        {formatDuration(durationS)}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
        Duração total
      </div>
      <button
        onClick={onClose}
        className="mt-5 w-full py-2.5 rounded-xl font-semibold text-sm border border-white/10 bg-white/5 hover:bg-white/10 transition-colors"
      >
        Fechar
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// FailedBody — erro
// ══════════════════════════════════════════════════════════════════

function FailedBody({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="px-5 py-6 text-center">
      <div className="w-16 h-16 rounded-full mx-auto mb-3 bg-classification-critical/15 border border-classification-critical/30 flex items-center justify-center">
        <PhoneOff className="h-8 w-8 text-classification-critical" strokeWidth={2.5} />
      </div>
      <div className="text-base font-bold">Não foi possível completar</div>
      <div className="text-xs text-muted-foreground mt-1 px-4">{message}</div>
      <button
        onClick={onClose}
        className="mt-5 w-full py-2.5 rounded-xl font-semibold text-sm border border-white/10 bg-white/5 hover:bg-white/10 transition-colors"
      >
        Fechar
      </button>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// AlertContext — rodapé SEMPRE visível
// ══════════════════════════════════════════════════════════════════

function AlertContext({ alert }: { alert: ClinicalAlert }) {
  return (
    <div className="px-5 py-3 bg-[hsl(222,30%,10%)]/60 border-t border-white/5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
        Contexto
      </div>
      <p className="text-xs text-foreground/80 leading-snug line-clamp-2">
        {alert.excerpt}
      </p>
      {alert.ai_reason && (
        <p className="text-[11px] text-accent-cyan/80 flex items-start gap-1 mt-1.5 leading-snug">
          <Sparkles className="h-2.5 w-2.5 flex-shrink-0 mt-0.5" />
          <span className="line-clamp-1">{alert.ai_reason}</span>
        </p>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════

function formatPhone(digits: string): string {
  if (digits.length === 13 && digits.startsWith("55")) {
    return `+${digits.slice(0, 2)} (${digits.slice(2, 4)}) ${digits.slice(4, 9)}-${digits.slice(9)}`;
  }
  if (digits.length === 12 && digits.startsWith("55")) {
    return `+${digits.slice(0, 2)} (${digits.slice(2, 4)}) ${digits.slice(4, 8)}-${digits.slice(8)}`;
  }
  if (digits.length === 11) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  }
  return digits;
}

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
