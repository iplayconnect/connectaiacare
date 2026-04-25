"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, MicOff, Sparkles, Square, X } from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api, ApiError } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// FAB Sofia Voz — flutuante no canto inferior direito de todas as
// páginas com chrome (sidebar). Ao clicar, abre painel pequeno que:
//  1. Toca saudação TTS (Gemini Flash) personalizada com nome do user.
//  2. Permite gravar áudio (MediaRecorder) → enviar pra Sofia → tocar
//     resposta TTS.
//
// STT do áudio do usuário ainda usa Deepgram via /api/sofia/transcribe
// (não trocar pra Gemini sem shadow mode — ADR-028).
// Sofia.4 implementa o ciclo de gravação completo. Por enquanto FAB
// entrega saudação + abertura de chat texto rápido.
// ═══════════════════════════════════════════════════════════════

type Mode = "idle" | "greeting" | "listening" | "thinking" | "speaking" | "error";

export function SofiaVoiceFab() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("idle");
  const [transcript, setTranscript] = useState("");
  const [response, setResponse] = useState("");
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Greeting tocada ao abrir o painel pela primeira vez
  useEffect(() => {
    if (open && mode === "idle") {
      void playGreeting();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!user) return null;
  // FAB não aparece pra paciente_b2c na tela web — eles usam WhatsApp.
  if (user.role === "paciente_b2c") return null;

  async function playGreeting() {
    setError(null);
    setMode("greeting");
    try {
      const greet = await api.sofiaGreeting();
      setResponse(greet.text);
      const tts = await api.sofiaTTS(greet.text);
      await playAudioBase64(tts.audioBase64, tts.mimeType);
    } catch (err) {
      const msg = err instanceof ApiError ? err.reason || err.message : "Falha";
      setError(`Não consegui cumprimentar (${msg}).`);
      setMode("error");
      return;
    }
    setMode("idle");
  }

  async function playAudioBase64(b64: string, mime: string) {
    return new Promise<void>((resolve, reject) => {
      const audio = new Audio(`data:${mime};base64,${b64}`);
      audioRef.current = audio;
      audio.onended = () => {
        setMode("idle");
        resolve();
      };
      audio.onerror = () => reject(new Error("audio_play_failed"));
      setMode("speaking");
      audio.play().catch(reject);
    });
  }

  async function handleQuickAsk(text: string) {
    setError(null);
    setMode("thinking");
    setTranscript(text);
    try {
      const res = await api.sofiaChat(text);
      setResponse(res.text);
      if (res.text) {
        const tts = await api.sofiaTTS(res.text);
        await playAudioBase64(tts.audioBase64, tts.mimeType);
      } else {
        setMode("idle");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha");
      setMode("error");
    }
  }

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    setMode("idle");
  }

  return (
    <>
      {/* Painel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-80 rounded-2xl border border-accent-cyan/30 bg-[hsl(225,80%,8%)]/95 backdrop-blur-xl shadow-[0_8px_48px_rgba(49,225,255,0.20)] overflow-hidden animate-fade-up">
          <header className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-gradient-to-r from-accent-cyan/10 to-transparent">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent-cyan" />
              <span className="text-sm font-semibold">Sofia Voz</span>
              <ModePill mode={mode} />
            </div>
            <button
              onClick={() => {
                stopAudio();
                setOpen(false);
              }}
              className="p-1 rounded hover:bg-white/[0.05]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </header>

          <div className="px-4 py-3 space-y-3 max-h-72 overflow-y-auto text-xs">
            {transcript && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Você
                </div>
                <div className="bg-accent-cyan/10 border border-accent-cyan/20 rounded-lg px-3 py-2 text-foreground leading-relaxed">
                  {transcript}
                </div>
              </div>
            )}
            {response && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
                  Sofia
                </div>
                <div className="bg-white/[0.04] border border-white/[0.06] rounded-lg px-3 py-2 leading-relaxed">
                  {response}
                </div>
              </div>
            )}
            {error && (
              <div className="text-classification-attention">{error}</div>
            )}
            {mode === "idle" && !transcript && !response && (
              <div className="text-muted-foreground text-center py-2">
                Sofia tá te ouvindo. Diga algo ou use um atalho:
              </div>
            )}
          </div>

          {/* Quick prompts */}
          <div className="px-4 pb-3 flex flex-wrap gap-1.5">
            {QUICK_PROMPTS_FOR_ROLE[user.role]?.map((p, i) => (
              <button
                key={i}
                onClick={() => handleQuickAsk(p)}
                disabled={mode !== "idle"}
                className="text-[10px] px-2 py-1 rounded-full bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] disabled:opacity-50"
              >
                {p}
              </button>
            ))}
          </div>

          {/* Mic placeholder (Sofia.4 ativa MediaRecorder real) */}
          <div className="border-t border-white/[0.04] px-4 py-3 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
            {mode === "speaking" ? (
              <button
                onClick={stopAudio}
                className="flex items-center gap-1.5 text-classification-attention"
              >
                <Square className="h-3 w-3 fill-current" /> parar fala
              </button>
            ) : (
              <span className="flex items-center gap-1.5">
                <MicOff className="h-3 w-3" />
                gravação por voz chega na próxima atualização
              </span>
            )}
            <span>{mode}</span>
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
        {mode === "thinking" ? (
          <Loader2 className="h-6 w-6 animate-spin" />
        ) : mode === "speaking" ? (
          <Mic className="h-6 w-6 animate-pulse" />
        ) : (
          <Sparkles className="h-6 w-6" />
        )}
      </button>
    </>
  );
}

function ModePill({ mode }: { mode: Mode }) {
  if (mode === "idle") return null;
  const map: Record<Mode, { label: string; color: string }> = {
    idle: { label: "", color: "" },
    greeting: { label: "cumprimentando", color: "text-accent-cyan" },
    listening: { label: "ouvindo", color: "text-classification-routine" },
    thinking: { label: "pensando", color: "text-classification-attention" },
    speaking: { label: "falando", color: "text-accent-cyan" },
    error: { label: "erro", color: "text-classification-attention" },
  };
  const cur = map[mode];
  if (!cur.label) return null;
  return (
    <span className={`text-[10px] uppercase tracking-wider ${cur.color}`}>
      · {cur.label}
    </span>
  );
}

const QUICK_PROMPTS_FOR_ROLE: Record<string, string[]> = {
  super_admin: ["Quantos pacientes ativos?", "Quais alertas estão abertos?"],
  admin_tenant: ["Quais alertas estão abertos?", "Como cadastro um paciente?"],
  medico: ["Quais pacientes têm alerta crítico?", "Resumo do paciente mais recente"],
  enfermeiro: ["Quais alertas requerem atenção?", "Quem precisa de medicação agora?"],
  cuidador_pro: ["Que medicação posso dar agora?", "Status do paciente"],
  familia: ["Como tá meu familiar?", "Posso agendar uma teleconsulta?"],
  parceiro: ["Status dos meus pacientes liberados"],
  paciente_b2c: [], // FAB não aparece pra B2C
};
