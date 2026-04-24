"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Delete, Phone, Sparkles, X } from "lucide-react";

import type { ClinicalAlert } from "@/hooks/use-alerts";

interface Props {
  alert: ClinicalAlert;
  onConfirm: (finalPhone: string) => void;
  onCancel: () => void;
}

/**
 * Dialpad — teclado visual de discagem antes de ligar via VoIP.
 *
 * Abre pré-populado com o phone do family_contact (se houver).
 * User pode editar teclando nos botões ou no input direto.
 * Só dispara chamada quando clica no botão verde "Ligar".
 *
 * Estilo: iPhone/softphone clássico — display grande + grid 3×4 + CTA.
 */
export function CallConfirmModal({ alert, onConfirm, onCancel }: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const defaultPhone = alert.patient.family_contact?.phone ?? "";
  const [phone, setPhone] = useState<string>(defaultPhone);

  // Lock scroll + Esc fecha + teclado digital
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Backspace") {
        setPhone((p) => p.slice(0, -1));
      } else if (/^[0-9*#+]$/.test(e.key)) {
        setPhone((p) => p + e.key);
      } else if (e.key === "Enter" && phone.replace(/\D/g, "").length >= 10) {
        onConfirm(phone.replace(/\D/g, ""));
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", handler);
    };
  }, [onCancel, onConfirm, phone]);

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
      {/* Overlay */}
      <div
        onClick={onCancel}
        className="absolute inset-0 bg-black/60 backdrop-blur-md"
        aria-hidden
      />

      {/* Dialpad modal */}
      <div
        role="dialog"
        aria-label="Dialpad — ligar para família"
        aria-modal="true"
        className="relative w-full max-w-[380px] glass-card rounded-3xl shadow-2xl overflow-hidden"
        style={{
          borderColor: "rgba(251, 146, 60, 0.35)",
          animation: "slide-in-up 280ms cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        {/* Header */}
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-white/10 bg-gradient-to-b from-classification-urgent/10 to-transparent">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-classification-urgent font-bold">
              Sofia Voz · Família
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5 truncate max-w-[220px]">
              {alert.patient.name}
            </div>
          </div>
          <button
            onClick={onCancel}
            aria-label="Fechar dialpad"
            className="w-8 h-8 rounded-lg border border-white/10 bg-white/5 text-foreground/80 grid place-items-center hover:bg-white/10 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </header>

        {/* Display do número */}
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
              <div className="text-3xl font-bold font-mono tabular text-foreground tracking-tight break-all">
                {phoneDisplay}
              </div>
            )}
          </div>

          {phoneDigits.length > 0 && phoneDigits.length < 10 && (
            <div className="text-[11px] text-muted-foreground mt-1">
              Faltam {10 - phoneDigits.length} dígito
              {10 - phoneDigits.length > 1 ? "s" : ""} (DDD + número)
            </div>
          )}
        </div>

        {/* Dialpad — grid 3×4 */}
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
                onClick={() => pressKey(d)}
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

          {/* Controles auxiliares */}
          <div className="grid grid-cols-3 gap-2 mt-2">
            <button
              onClick={clearAll}
              disabled={phoneDigits.length === 0}
              className="py-2 rounded-xl text-[11px] font-semibold uppercase tracking-wider border border-white/5 bg-white/[0.02] text-foreground/60 hover:bg-white/5 disabled:opacity-30 transition-colors"
            >
              Limpar
            </button>

            {/* Botão verde GRANDE ligar */}
            <button
              onClick={() => canCall && onConfirm(phoneDigits)}
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
              onClick={backspace}
              disabled={phoneDigits.length === 0}
              className="py-2 rounded-xl text-foreground/60 hover:text-foreground hover:bg-white/5 disabled:opacity-30 transition-colors flex items-center justify-center"
              aria-label="Apagar último dígito"
            >
              <Delete className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Contexto do alerta (compacto) */}
        <div className="px-5 py-3 bg-[hsl(222,30%,10%)]/60 border-t border-white/5">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
            Alerta
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

        {/* Disclaimer */}
        <p className="px-5 pb-3 pt-2 text-[10px] text-muted-foreground/60 italic text-center leading-relaxed">
          Sofia Voz disca via Asterisk + IA contextualizada (Deepgram + ElevenLabs)
        </p>
      </div>
    </div>,
    document.body,
  );
}

// ══════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════

function formatPhone(digits: string): string {
  // E.164 BR: +55 11 98765-4321 (13 dígitos)
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
