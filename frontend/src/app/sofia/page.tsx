"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Loader2,
  Send,
  Sparkles,
  Wrench,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api, ApiError, type SofiaMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════
// /sofia — chat persona-aware com Gemini 3.1 Flash
// Substitui /demo/onboarding (era um demo de fluxo, agora é a Sofia real)
// ═══════════════════════════════════════════════════════════════

type LocalMessage = {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  agent?: string;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  toolCalls?: number;
  createdAt: string;
  toolEvents?: { name: string; ok: boolean }[];
};

export default function SofiaChatPage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<{ messages: number; tokensIn: number; tokensOut: number } | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const personaLabel = useMemo(
    () => (user ? ROLE_LABEL[user.role] || user.role : ""),
    [user],
  );

  useEffect(() => {
    // Greeting inicial vinda do agent_runner sem chamar LLM (template)
    if (!user) return;
    api.sofiaGreeting()
      .then((res) => {
        setMessages([
          {
            role: "assistant",
            content: res.text,
            createdAt: new Date().toISOString(),
          },
        ]);
      })
      .catch(() => {
        setMessages([
          {
            role: "assistant",
            content: `Oi ${user.fullName.split(" ")[0]}! Como posso te ajudar?`,
            createdAt: new Date().toISOString(),
          },
        ]);
      });
    api.sofiaUsage()
      .then((res) => setUsage(res.usage))
      .catch(() => {});
  }, [user?.id, user?.fullName, user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function handleSend(e?: React.FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    setError(null);
    const now = new Date().toISOString();
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text, createdAt: now },
      { role: "assistant", content: "", pending: true, createdAt: now },
    ]);
    setInput("");
    setSending(true);

    try {
      const res = await api.sofiaChat(text, "web");
      setMessages((prev) => {
        const out = [...prev];
        const idx = out.findIndex((m) => m.pending);
        if (idx >= 0) {
          out[idx] = {
            role: "assistant",
            content: res.text || (res.blocked ? "" : "(sem resposta)"),
            pending: false,
            agent: res.agent,
            model: res.model,
            tokensIn: res.tokensIn,
            tokensOut: res.tokensOut,
            toolCalls: res.toolCalls,
            createdAt: new Date().toISOString(),
          };
        }
        return out;
      });
      // Atualiza consumo silenciosamente
      api.sofiaUsage().then((u) => setUsage(u.usage)).catch(() => {});
    } catch (err) {
      setMessages((prev) => prev.filter((m) => !m.pending));
      const reason = err instanceof ApiError ? err.reason : null;
      if (reason === "sofia_unavailable") {
        setError("Sofia tá fora do ar agora. Tenta de novo em alguns segundos.");
      } else {
        setError(err instanceof Error ? err.message : "Falha ao enviar.");
      }
    } finally {
      setSending(false);
    }
  }

  if (!user) {
    return (
      <div className="text-muted-foreground text-sm">Carregando sessão...</div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] max-w-4xl">
      {/* Header */}
      <header className="flex items-end justify-between gap-4 mb-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-accent-cyan" />
            Sofia Chat
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Conversa contextualizada — você é{" "}
            <span className="text-accent-cyan">{personaLabel}</span>. Sofia
            adapta o tom, ferramentas e segurança conforme seu perfil.
          </p>
        </div>
        {usage && (
          <UsageBadge
            messages={usage.messages}
            tokensIn={usage.tokensIn}
            tokensOut={usage.tokensOut}
          />
        )}
      </header>

      {/* Conversation */}
      <div
        ref={scrollerRef}
        className="flex-1 overflow-y-auto rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4"
      >
        {messages.map((m, i) => (
          <Bubble key={i} m={m} />
        ))}
      </div>

      {error && (
        <div className="mt-3 flex items-start gap-2 p-3 rounded-lg bg-classification-attention/10 border border-classification-attention/20 text-xs text-classification-attention">
          <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={handleSend}
        className="mt-3 flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={
            user.role === "paciente_b2c"
              ? "Conta pra Sofia como você tá hoje..."
              : user.role === "cuidador_pro"
              ? "Faça um relato, pergunte sobre medicação ou peça status de paciente..."
              : "Pergunte qualquer coisa sobre paciente, evento, plataforma..."
          }
          rows={2}
          disabled={sending}
          className="input flex-1 resize-none font-normal"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg accent-gradient text-slate-900 font-medium text-sm shadow-glow-cyan hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Enviar
        </button>
      </form>
      <p className="text-[10px] text-muted-foreground mt-2 px-1 leading-relaxed">
        Sofia é uma assistente, não substitui parecer médico (CFM 2.314/2022).
        Em emergência ligue 192 (SAMU). Conversas são registradas para auditoria
        LGPD.
      </p>
    </div>
  );
}

// ─── Components ──────────────────────────────────────

function Bubble({ m }: { m: LocalMessage }) {
  const isUser = m.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`
          max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed
          ${isUser
            ? "bg-accent-cyan/15 border border-accent-cyan/30 text-foreground"
            : "bg-white/[0.04] border border-white/[0.06] text-foreground"}
        `}
      >
        {m.pending ? (
          <span className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Sofia está pensando...
          </span>
        ) : (
          <>
            <div className="whitespace-pre-wrap">{m.content || <em className="text-muted-foreground">(sem texto)</em>}</div>
            {!isUser && (m.agent || m.toolCalls) && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground border-t border-white/[0.04] pt-1.5">
                {m.agent && <span className="px-1.5 py-0.5 rounded bg-white/[0.04]">{m.agent}</span>}
                {m.model && <span>{m.model}</span>}
                {m.toolCalls != null && m.toolCalls > 0 && (
                  <span className="flex items-center gap-1">
                    <Wrench className="h-2.5 w-2.5" />
                    {m.toolCalls} tool{m.toolCalls === 1 ? "" : "s"}
                  </span>
                )}
                {m.tokensIn != null && m.tokensOut != null && (
                  <span className="font-mono">
                    {m.tokensIn}↗ {m.tokensOut}↘
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function UsageBadge({
  messages,
  tokensIn,
  tokensOut,
}: {
  messages: number;
  tokensIn: number;
  tokensOut: number;
}) {
  const fmt = (n: number) =>
    n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000 ? `${(n / 1_000).toFixed(1)}k`
    : `${n}`;
  return (
    <div className="text-[10px] text-muted-foreground bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-1.5">
      <div className="font-medium text-foreground mb-0.5">Consumo do mês</div>
      <div className="flex items-center gap-2.5">
        <span>{messages} msgs</span>
        <span>·</span>
        <span className="font-mono">{fmt(tokensIn + tokensOut)} tokens</span>
      </div>
    </div>
  );
}
