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
 * Phase A 2026-05-02:
 *  - PR #93: QuickRepliesSidebar (Ctrl+1..9)
 *  - PR atual (A1): MessageBubble rico — edit/reply/delete por msg
 *
 * Próximas fases:
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
  User,
  RefreshCw,
  Zap,
  X,
  Reply as ReplyIcon,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";
import { QuickRepliesSidebar } from "@/components/handoff/QuickRepliesSidebar";
import {
  MessageBubble,
  type ChatMessage,
} from "@/components/handoff/MessageBubble";

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

const POLL_INTERVAL_MS = 3000;
const MUTATION_WINDOW_SECONDS = 300; // sincronizado com backend

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
  const [live, setLive] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [text, setText] = useState("");
  const [resolveSummary, setResolveSummary] = useState("");
  const [showResolve, setShowResolve] = useState(false);
  const [showQuickReplies, setShowQuickReplies] = useState(false);
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const canManageQuickReplies = hasRole(user, "super_admin", "admin_tenant");

  const insertQuickReply = useCallback((content: string) => {
    setText((prev) => {
      // Se input vazio: preenche direto. Senão: append com quebra de
      // linha pra preservar o que operador já escreveu.
      if (!prev.trim()) return content;
      return `${prev.trimEnd()}\n${content}`;
    });
    // Devolve foco pro textarea pra operador customizar antes de enviar
    requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

  // Esc fecha sidebar quando aberta (sem afetar outros modais)
  useEffect(() => {
    if (!showQuickReplies) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowQuickReplies(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showQuickReplies]);

  const loadAll = useCallback(async () => {
    if (!handoffId) return;
    try {
      const [hRes, mRes] = await Promise.all([
        api.request<{ handoff: Handoff }>(`/api/admin/handoff/${handoffId}`),
        api.request<{ snapshot: SnapshotMessage[]; live: ChatMessage[] }>(
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

  const buildOutgoingText = useCallback(
    (raw: string, quoted: ChatMessage | null): string => {
      if (!quoted || !quoted.content) return raw;
      // Quote estilo WhatsApp: prefixo "> " em cada linha do original.
      // Limita a 240 chars pra não inundar a mensagem.
      const truncated =
        quoted.content.length > 240
          ? quoted.content.slice(0, 240) + "…"
          : quoted.content;
      const quotedLines = truncated
        .split("\n")
        .map((l) => `> ${l}`)
        .join("\n");
      return `${quotedLines}\n\n${raw}`;
    },
    [],
  );

  const send = async () => {
    if (!handoffId || !text.trim() || sending) return;
    setSending(true);
    const outgoing = buildOutgoingText(text.trim(), replyTo);
    try {
      await api.request(`/api/admin/handoff/${handoffId}/send`, {
        method: "POST",
        body: JSON.stringify({ text: outgoing }),
      });
      setText("");
      setReplyTo(null);
      // Recarrega imediatamente pra ver msg enviada
      await loadAll();
    } catch (e) {
      alert(e instanceof Error ? e.message : "erro enviando");
    } finally {
      setSending(false);
    }
  };

  const handleEditMessage = useCallback(
    async (msg: ChatMessage, newContent: string) => {
      if (!handoffId) return;
      await api.request(
        `/api/admin/handoff/${handoffId}/messages/${msg.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ content: newContent }),
        },
      );
      // Atualização otimista local + revalida no próximo poll
      setLive((prev) =>
        prev.map((m) =>
          m.id === msg.id
            ? {
                ...m,
                content: newContent,
                edited_at: new Date().toISOString(),
                edit_count: (m.edit_count || 0) + 1,
              }
            : m,
        ),
      );
    },
    [handoffId],
  );

  const handleDeleteMessage = useCallback(
    async (msg: ChatMessage) => {
      if (!handoffId) return;
      await api.request(
        `/api/admin/handoff/${handoffId}/messages/${msg.id}`,
        { method: "DELETE" },
      );
      setLive((prev) =>
        prev.map((m) => (m.id === msg.id ? { ...m, deleted: true } : m)),
      );
    },
    [handoffId],
  );

  const handleReplyTo = useCallback((msg: ChatMessage) => {
    setReplyTo(msg);
    requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

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
              onClick={() => setShowQuickReplies((v) => !v)}
              className={`p-1.5 rounded-md hover:bg-muted ${
                showQuickReplies ? "text-amber-500 bg-muted" : ""
              }`}
              title="Respostas rápidas (Ctrl+1..9)"
            >
              <Zap className="h-4 w-4" />
            </button>
          )}
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
          <MessageBubble
            key={m.id}
            msg={m}
            currentUserId={user?.id}
            mutationWindowSeconds={MUTATION_WINDOW_SECONDS}
            onReply={isClaimedByMe ? handleReplyTo : undefined}
            onEdit={isClaimedByMe ? handleEditMessage : undefined}
            onDelete={isClaimedByMe ? handleDeleteMessage : undefined}
          />
        ))}
      </div>

      {/* Reply quoted preview */}
      {replyTo && replyTo.content && isClaimedByMe && (
        <div className="border-t border-border pt-2 px-3">
          <div className="flex items-start gap-2 px-2 py-1.5 rounded-md bg-cyan-500/5 border-l-2 border-cyan-500/50">
            <ReplyIcon className="h-3 w-3 text-cyan-500 mt-1 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-medium text-cyan-500/80">
                Respondendo
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {replyTo.content}
              </p>
            </div>
            <button
              onClick={() => setReplyTo(null)}
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground shrink-0"
              title="Cancelar resposta"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      {/* Composer */}
      {isClaimedByMe ? (
        <div className="border-t border-border pt-3 pb-1">
          <div className="flex items-end gap-2">
            <textarea
              ref={composerRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                } else if (e.key === "Escape" && replyTo) {
                  e.preventDefault();
                  setReplyTo(null);
                }
              }}
              placeholder={
                replyTo
                  ? "Digite sua resposta…"
                  : "Digite a resposta pro lead… (Enter envia, Shift+Enter quebra linha)"
              }
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

      {/* Sidebar de Respostas Rápidas — montada apenas qdo claimed_by_me
          pra hotkeys Ctrl+1..9 não capturarem em modo read-only */}
      {isClaimedByMe && (
        <QuickRepliesSidebar
          isOpen={showQuickReplies}
          onClose={() => setShowQuickReplies(false)}
          onSelect={insertQuickReply}
          canManage={canManageQuickReplies}
          leadName={handoff.phone}
        />
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

// ─── Snapshot bubble (histórico Sofia pré-handoff, sem affordances) ───

function SnapshotBubble({ msg }: { msg: SnapshotMessage }) {
  const botText = msg.bot_message;
  const leadText = msg.lead_message;
  return (
    <>
      {botText && <SimpleBubble role="sofia" content={botText} />}
      {leadText && <SimpleBubble role="user" content={leadText} />}
    </>
  );
}

function SimpleBubble({
  role,
  content,
}: {
  role: "user" | "sofia";
  content: string;
}) {
  const isFromUser = role === "user";
  const align = isFromUser ? "items-start" : "items-end";
  const bgColor = isFromUser
    ? "bg-muted text-foreground"
    : "bg-primary/10 text-foreground border border-primary/20";
  const Icon = isFromUser ? User : Bot;
  const labelColor = isFromUser ? "text-muted-foreground" : "text-primary";
  const label = isFromUser ? "Lead" : "Sofia";

  return (
    <div className={`flex flex-col ${align}`}>
      <div className="flex items-center gap-1.5 mb-1 text-[10px]">
        <Icon className={`h-3 w-3 ${labelColor}`} />
        <span className={`font-medium ${labelColor}`}>{label}</span>
      </div>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${bgColor}`}
      >
        {content}
      </div>
    </div>
  );
}
