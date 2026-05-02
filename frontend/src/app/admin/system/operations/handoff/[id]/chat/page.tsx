"use client";

/**
 * Chat handoff — operador atende lead em tempo real após reivindicar.
 *
 * Fluxo:
 *  1. Operador clicou "Reivindicar" na fila → handoff.status='claimed'
 *     + redirect pra esta página.
 *  2. Backend bypassa Sofia pra mensagens do phone (ver
 *     super_sofia_orchestrator: handoff_bypass_check) — msgs do lead
 *     vão pra aia_health_sofia_messages mas NÃO acionam Sofia.
 *  3. Esta página faz polling 3s em /messages e renderiza histórico
 *     (snapshot pré-handoff + live durante atendimento).
 *  4. Operador escreve no input → POST /send → Evolution → lead recebe
 *     no WhatsApp.
 *  5. Quando resolver, click "Marcar resolvido" → handoff.status=resolved,
 *     bypass desativa, Sofia volta a atender.
 *
 * Phase D 2026-05-02 — esqueleto inicial. Próxima sessão:
 *  - WebSocket pra real-time (hoje é polling)
 *  - Notificações de "lead respondeu" enquanto operador tá em outra aba
 *  - Multi-operador (handoff transferido entre operadores)
 *  - SLA timer visual
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Send,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Bot,
  Headphones,
  User,
  RefreshCw,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

interface Handoff {
  id: string;
  phone: string;
  reason: string;
  context_summary: string;
  priority: string;
  status: string;
  created_at: string;
  claimed_at: string | null;
  claimed_by_user_id: string | null;
  resolution_summary: string | null;
}

interface SnapshotMessage {
  ts?: number | string;
  role?: string;
  bot_message?: string;
  lead_message?: string;
  bot_intent?: string;
}

interface LiveMessage {
  id: number;
  role: string; // 'user' | 'assistant' | 'tool' | 'system'
  content: string | null;
  created_at: string;
  actor?: string; // 'human' | 'sofia' (presente quando role=assistant)
}

const POLL_INTERVAL_MS = 3000;

const PRIORITY_COLORS: Record<string, string> = {
  P1: "#ef4444",
  P2: "#f59e0b",
  P3: "#94a3b8",
};

export default function HandoffChatPage() {
  const { user } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const handoffId = params?.id;
  const allowed = hasRole(
    user, "super_admin", "admin_tenant", "medico", "enfermeiro",
  );

  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotMessage[]>([]);
  const [live, setLive] = useState<LiveMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [text, setText] = useState("");
  const [resolveSummary, setResolveSummary] = useState("");
  const [showResolve, setShowResolve] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  const loadAll = useCallback(async () => {
    if (!handoffId) return;
    try {
      const [hRes, mRes] = await Promise.all([
        api.request<{ handoff: Handoff }>(`/api/admin/handoff/${handoffId}`),
        api.request<{ snapshot: SnapshotMessage[]; live: LiveMessage[] }>(
          `/api/admin/handoff/${handoffId}/messages`,
        ),
      ]);
      setHandoff(hRes.handoff);
      setSnapshot(mRes.snapshot || []);
      setLive(mRes.live || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "erro carregando");
    } finally {
      setLoading(false);
    }
  }, [handoffId]);

  // Initial + polling
  useEffect(() => {
    if (!allowed || !handoffId) return;
    loadAll();
    const t = setInterval(loadAll, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [allowed, handoffId, loadAll]);

  // Auto-scroll quando mudou tamanho da lista live
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [live.length]);

  const send = async () => {
    if (!handoffId || !text.trim() || sending) return;
    setSending(true);
    try {
      await api.request(`/api/admin/handoff/${handoffId}/send`, {
        method: "POST",
        body: JSON.stringify({ text: text.trim() }),
      });
      setText("");
      // Recarrega imediatamente pra ver msg enviada
      await loadAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : "erro enviando");
    } finally {
      setSending(false);
    }
  };

  const resolve = async () => {
    if (!handoffId || !resolveSummary.trim() || resolving) return;
    setResolving(true);
    try {
      await api.request(`/api/admin/handoff/${handoffId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution_summary: resolveSummary.trim() }),
      });
      router.push("/admin/system/operations/handoff");
    } catch (e) {
      alert(e instanceof Error ? e.message : "erro resolvendo");
    } finally {
      setResolving(false);
    }
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Sem acesso.
      </div>
    );
  }

  if (loading && !handoff) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <Loader2 className="h-6 w-6 animate-spin inline" />
      </div>
    );
  }

  if (error || !handoff) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-rose-500">
        <AlertTriangle className="inline mr-2 h-4 w-4" />
        {error || "handoff não encontrado"}
      </div>
    );
  }

  const isClaimedByMe =
    handoff.status === "claimed" &&
    String(handoff.claimed_by_user_id || "") === String(user?.id || "");

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-[1100px] mx-auto px-4 py-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => router.push("/admin/system/operations/handoff")}
            className="p-1.5 rounded-md hover:bg-muted shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span
                className="px-1.5 py-0.5 rounded text-xs font-bold text-white shrink-0"
                style={{
                  backgroundColor:
                    PRIORITY_COLORS[handoff.priority] || "#94a3b8",
                }}
              >
                {handoff.priority}
              </span>
              <h1 className="text-base font-semibold truncate">
                Atendimento · {handoff.phone}
              </h1>
            </div>
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {handoff.reason}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={loadAll}
            className="p-1.5 rounded-md hover:bg-muted"
            title="Atualizar"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          {isClaimedByMe && (
            <button
              onClick={() => setShowResolve(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-classification-routine/40 text-classification-routine hover:bg-classification-routine/10"
            >
              <CheckCircle2 className="h-3 w-3" />
              Marcar resolvido
            </button>
          )}
          {handoff.status === "resolved" && (
            <span className="text-xs text-muted-foreground">
              ✓ Resolvido
            </span>
          )}
        </div>
      </div>

      {/* Context summary */}
      {handoff.context_summary && (
        <div className="my-3 px-3 py-2 rounded-md bg-amber-500/5 border border-amber-500/20 text-xs">
          <span className="font-medium">Contexto do escalate:</span>{" "}
          <span className="text-muted-foreground">
            {handoff.context_summary}
          </span>
        </div>
      )}

      {/* Mensagens — snapshot + live */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto space-y-2 px-1 py-2 min-h-0"
      >
        {snapshot.length > 0 && (
          <>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-2 py-1">
              Histórico Sofia (pré-handoff)
            </div>
            {snapshot.map((m, i) => (
              <SnapshotBubble key={`s-${i}`} msg={m} />
            ))}
            <div className="border-t border-dashed border-border/40 my-3" />
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground/60 px-2 py-1">
              Atendimento humano
            </div>
          </>
        )}
        {live.length === 0 && snapshot.length === 0 && (
          <div className="text-center text-sm text-muted-foreground py-12">
            Nenhuma mensagem ainda.
          </div>
        )}
        {live.map((m) => (
          <LiveBubble key={m.id} msg={m} />
        ))}
      </div>

      {/* Composer */}
      {isClaimedByMe ? (
        <div className="border-t border-border pt-3 pb-1">
          <div className="flex items-end gap-2">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Digite a resposta pro lead… (Enter envia, Shift+Enter quebra linha)"
              rows={2}
              className="flex-1 resize-none px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              disabled={sending}
            />
            <button
              onClick={send}
              disabled={sending || !text.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50 shrink-0"
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Enviar
            </button>
          </div>
        </div>
      ) : (
        <div className="border-t border-border pt-3 pb-1 text-xs text-center text-muted-foreground">
          {handoff.status === "claimed"
            ? "Esse handoff está reivindicado por outro operador. Você pode acompanhar mas não enviar mensagens."
            : handoff.status === "resolved"
            ? "Esse handoff foi resolvido. Apenas leitura."
            : "Reivindique o handoff na fila pra começar a atender."}
        </div>
      )}

      {/* Modal Resolver */}
      {showResolve && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4">
          <div className="bg-background border border-border rounded-lg max-w-md w-full p-5">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Resolver handoff
            </h3>
            <textarea
              value={resolveSummary}
              onChange={(e) => setResolveSummary(e.target.value)}
              rows={4}
              placeholder="Resumo do desfecho (ex: 'Conectei lead com Murilo, agendei demo dia 15')"
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary mb-3"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setShowResolve(false);
                  setResolveSummary("");
                }}
                disabled={resolving}
                className="px-3 py-1.5 text-xs rounded-md hover:bg-muted"
              >
                Cancelar
              </button>
              <button
                onClick={resolve}
                disabled={resolving || !resolveSummary.trim()}
                className="px-3 py-1.5 text-xs rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
              >
                {resolving && (
                  <Loader2 className="h-3 w-3 animate-spin inline mr-1" />
                )}
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sub-componentes ───────────────────────────────────────────

function SnapshotBubble({ msg }: { msg: SnapshotMessage }) {
  const botText = msg.bot_message;
  const leadText = msg.lead_message;
  return (
    <>
      {botText && <Bubble role="sofia" content={botText} />}
      {leadText && <Bubble role="user" content={leadText} />}
    </>
  );
}

function LiveBubble({ msg }: { msg: LiveMessage }) {
  if (!msg.content) return null;
  // role + actor → quem mandou
  let who: "user" | "sofia" | "human" | "tool" = "user";
  if (msg.role === "assistant") {
    who = msg.actor === "human" ? "human" : "sofia";
  } else if (msg.role === "tool") {
    who = "tool";
  } else if (msg.role === "user") {
    who = "user";
  }
  return <Bubble role={who} content={msg.content} ts={msg.created_at} />;
}

function Bubble({
  role,
  content,
  ts,
}: {
  role: "user" | "sofia" | "human" | "tool";
  content: string;
  ts?: string;
}) {
  const isFromUser = role === "user";
  const align = isFromUser ? "items-start" : "items-end";
  const bgColor =
    role === "user"
      ? "bg-muted text-foreground"
      : role === "human"
      ? "bg-cyan-500/15 text-foreground border border-cyan-500/30"
      : role === "sofia"
      ? "bg-primary/10 text-foreground border border-primary/20"
      : "bg-amber-500/10 text-foreground border border-amber-500/20";
  const Icon = isFromUser ? User : role === "human" ? Headphones : Bot;
  const labelColor =
    role === "human"
      ? "text-cyan-500"
      : role === "sofia"
      ? "text-primary"
      : role === "tool"
      ? "text-amber-500"
      : "text-muted-foreground";
  const label =
    role === "user"
      ? "Lead"
      : role === "human"
      ? "Você"
      : role === "sofia"
      ? "Sofia"
      : "Tool";

  return (
    <div className={`flex flex-col ${align}`}>
      <div className="flex items-center gap-1.5 mb-1 text-[10px]">
        <Icon className={`h-3 w-3 ${labelColor}`} />
        <span className={`font-medium ${labelColor}`}>{label}</span>
        {ts && (
          <span className="text-muted-foreground/60">
            {new Date(ts).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        )}
      </div>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${bgColor}`}
      >
        {content}
      </div>
    </div>
  );
}
