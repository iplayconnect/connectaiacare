"use client";

import { useState } from "react";
import {
  AlertCircle,
  Loader2,
  Mic,
  MicOff,
  PhoneOff,
  Sparkles,
  Volume2,
  Wrench,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { useSofiaVoice } from "@/hooks/use-sofia-voice";

// ═══════════════════════════════════════════════════════════════
// FAB Sofia Voz — sessão Live API bidirecional (Sofia.4)
//
// Fluxo:
//   Click FAB → painel abre
//   Click "Falar" → permissão mic → WS sofia-voice → Live API
//   Conversa contínua: usuário fala, Sofia responde por voz, tools chamam
//   Click "Encerrar" → cleanup full
//
// FAB não aparece pra paciente_b2c (eles usam WhatsApp).
// ═══════════════════════════════════════════════════════════════

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  idle: { label: "", color: "" },
  requesting_permission: { label: "pedindo mic...", color: "text-classification-attention" },
  connecting: { label: "conectando...", color: "text-classification-attention" },
  ready: { label: "pronta", color: "text-accent-cyan" },
  listening: { label: "ouvindo", color: "text-classification-routine" },
  thinking: { label: "pensando", color: "text-classification-attention" },
  speaking: { label: "falando", color: "text-accent-cyan" },
  interrupted: { label: "pausada", color: "text-muted-foreground" },
  error: { label: "erro", color: "text-classification-attention" },
};

export function SofiaVoiceFab() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const voice = useSofiaVoice();

  if (!user) return null;
  // FAB não aparece pra paciente_b2c na tela web — eles usam WhatsApp.
  if (user.role === "paciente_b2c") return null;

  const handleClose = () => {
    voice.stop();
    setOpen(false);
  };

  return (
    <>
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-80 rounded-2xl border border-accent-cyan/30 bg-[hsl(225,80%,8%)]/95 backdrop-blur-xl shadow-[0_8px_48px_rgba(49,225,255,0.20)] overflow-hidden animate-fade-up">
          <header className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-gradient-to-r from-accent-cyan/10 to-transparent">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent-cyan" />
              <span className="text-sm font-semibold">Sofia Voz</span>
              <StatusPill status={voice.status} />
            </div>
            <button
              onClick={handleClose}
              className="p-1 rounded hover:bg-white/[0.05]"
              title="Fechar"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </header>

          {/* Transcripts */}
          <div className="px-4 py-3 max-h-64 overflow-y-auto text-xs space-y-2">
            {voice.transcripts.length === 0 && voice.status === "idle" && (
              <div className="text-muted-foreground text-center py-3 leading-relaxed">
                Toque no botão abaixo pra começar a falar com a Sofia. Ela vai
                te cumprimentar e responder em tempo real.
              </div>
            )}
            {voice.transcripts.length === 0 && voice.status !== "idle" && (
              <div className="text-muted-foreground text-center py-3 italic">
                {voice.status === "listening"
                  ? "Pode falar..."
                  : "Aguarda um instante..."}
              </div>
            )}
            {voice.transcripts.map((t, i) => (
              <TranscriptBubble key={i} t={t} />
            ))}
            {voice.toolEvents.length > 0 && (
              <div className="pt-2 border-t border-white/[0.04] space-y-1">
                {voice.toolEvents.map((e, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-1.5 text-[10px] text-muted-foreground"
                  >
                    <Wrench className="h-2.5 w-2.5" />
                    {e.name}
                    <span
                      className={
                        e.ok
                          ? "text-classification-routine"
                          : "text-classification-attention"
                      }
                    >
                      {e.ok ? "ok" : "falhou"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {voice.error && (
            <div className="px-4 py-2 text-[11px] text-classification-attention border-t border-classification-attention/20 bg-classification-attention/5 flex items-start gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>{voice.error}</span>
            </div>
          )}

          {/* Controles */}
          <div className="border-t border-white/[0.04] px-4 py-3 flex items-center gap-2">
            {!voice.isActive ? (
              <button
                onClick={voice.start}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium shadow-glow-cyan hover:brightness-110"
              >
                <Mic className="h-4 w-4" />
                Falar com a Sofia
              </button>
            ) : (
              <>
                <button
                  onClick={voice.interrupt}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/[0.05] hover:bg-white/[0.08] text-xs border border-white/[0.06]"
                  title="Interromper Sofia"
                >
                  <MicOff className="h-3.5 w-3.5" />
                  Pausar
                </button>
                <button
                  onClick={voice.stop}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-classification-attention/15 hover:bg-classification-attention/25 text-classification-attention text-sm font-medium border border-classification-attention/30"
                >
                  <PhoneOff className="h-4 w-4" />
                  Encerrar
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* FAB */}
      <button
        onClick={() => setOpen((v) => !v)}
        className={`
          fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full
          accent-gradient text-slate-900 font-bold
          shadow-glow-cyan hover:brightness-110 transition-all
          flex items-center justify-center
          ${open ? "ring-2 ring-accent-cyan/50" : ""}
        `}
        title="Sofia Voz"
      >
        {voice.status === "speaking" ? (
          <Volume2 className="h-6 w-6 animate-pulse" />
        ) : voice.status === "listening" ? (
          <Mic className="h-6 w-6" />
        ) : voice.status === "thinking" || voice.status === "connecting" ? (
          <Loader2 className="h-6 w-6 animate-spin" />
        ) : (
          <Sparkles className="h-6 w-6" />
        )}
      </button>
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  const cur = STATUS_LABEL[status];
  if (!cur || !cur.label) return null;
  return (
    <span className={`text-[10px] uppercase tracking-wider ${cur.color}`}>
      · {cur.label}
    </span>
  );
}

function TranscriptBubble({
  t,
}: {
  t: { role: "user" | "assistant"; text: string };
}) {
  const isUser = t.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`
          max-w-[85%] rounded-xl px-2.5 py-1.5 leading-snug
          ${isUser
            ? "bg-accent-cyan/15 border border-accent-cyan/20"
            : "bg-white/[0.04] border border-white/[0.06]"}
        `}
      >
        {t.text}
      </div>
    </div>
  );
}
