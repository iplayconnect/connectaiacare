"use client";

/**
 * MessageBubble — bolha de mensagem do chat handoff.
 *
 * Roles renderizados:
 *   - lead (role=user)        — bolha cinza alinhada à esquerda
 *   - sofia (role=assistant)  — bolha primária alinhada à direita
 *   - human (role=assistant + actor=human) — bolha cyan alinhada à direita
 *   - tool (role=tool)        — bolha amber centralizada (info/diagnóstico)
 *
 * Affordances disponíveis no hover (apenas msgs do operador atual,
 * dentro da janela de mutação 5min):
 *   - Reply  → callback onReply(msg)  (parent monta quoted block no composer)
 *   - Edit   → entra em edit mode inline (textarea + Save/Cancel)
 *   - Delete → callback onDelete(msg) com confirm 2-cliques
 *
 * Status:
 *   - sending=true → Loader2 ao lado do timestamp
 *   - msg.deleted  → "[mensagem apagada]"
 *   - msg.edited_at → label "(editado)"
 */
import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Check,
  CheckCheck,
  Headphones,
  Loader2,
  Pencil,
  Reply as ReplyIcon,
  Trash2,
  User,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

export interface ChatMessage {
  id: number;
  role: string; // 'user' | 'assistant' | 'tool' | 'system'
  content: string | null;
  created_at: string;
  actor?: string; // 'human' | 'sofia' (presente quando role=assistant)
  operator_user_id?: string;
  deleted?: boolean;
  edited_at?: string;
  edit_count?: number;
}

interface Props {
  msg: ChatMessage;
  /** ID do user atual; usado pra detectar msgs do próprio operador. */
  currentUserId?: string;
  /** True enquanto a msg ainda está sendo enviada (não persistida). */
  sending?: boolean;
  /** Janela em segundos pra editar/deletar. Default 300 (5min). */
  mutationWindowSeconds?: number;
  onReply?: (msg: ChatMessage) => void;
  onEdit?: (msg: ChatMessage, newContent: string) => Promise<void>;
  onDelete?: (msg: ChatMessage) => Promise<void>;
}

export function MessageBubble({
  msg,
  currentUserId,
  sending = false,
  mutationWindowSeconds = 300,
  onReply,
  onEdit,
  onDelete,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const editRef = useRef<HTMLTextAreaElement>(null);

  // ── Determinação de quem mandou ──────────────────────────────
  let who: "user" | "sofia" | "human" | "tool" | "system" = "user";
  if (msg.role === "assistant") {
    who = msg.actor === "human" ? "human" : "sofia";
  } else if (msg.role === "tool") {
    who = "tool";
  } else if (msg.role === "user") {
    who = "user";
  } else if (msg.role === "system") {
    who = "system";
  }

  const isMine =
    who === "human" &&
    !!currentUserId &&
    String(msg.operator_user_id || "") === String(currentUserId);

  // ── Janela de edição (client-side hint; backend valida) ────────
  const ageSec = msg.created_at
    ? Math.floor((Date.now() - new Date(msg.created_at).getTime()) / 1000)
    : Infinity;
  const inMutationWindow = ageSec < mutationWindowSeconds;
  const canMutate = isMine && !msg.deleted && !sending && inMutationWindow;

  // ── Edit mode ─────────────────────────────────────────────────
  useEffect(() => {
    if (editing && editRef.current) {
      editRef.current.focus();
      const len = editRef.current.value.length;
      editRef.current.setSelectionRange(len, len);
    }
  }, [editing]);

  const startEdit = () => {
    setError(null);
    setEditContent(msg.content || "");
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setEditContent("");
    setError(null);
  };

  const saveEdit = async () => {
    if (!onEdit) return;
    const trimmed = editContent.trim();
    if (!trimmed) {
      setError("Mensagem vazia.");
      return;
    }
    if (trimmed === msg.content) {
      cancelEdit();
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onEdit(msg, trimmed);
      setEditing(false);
      setEditContent("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  // ── Delete (2-clicks confirm) ─────────────────────────────────
  const handleDelete = async () => {
    if (!onDelete) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    try {
      await onDelete(msg);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erro ao apagar");
    } finally {
      setConfirmDelete(false);
    }
  };

  // ── Estilo por role ────────────────────────────────────────────
  const align =
    who === "user"
      ? "items-start"
      : who === "tool" || who === "system"
      ? "items-center"
      : "items-end";

  const bubbleColor =
    who === "user"
      ? "bg-muted text-foreground"
      : who === "human"
      ? "bg-cyan-500/15 text-foreground border border-cyan-500/30"
      : who === "sofia"
      ? "bg-primary/10 text-foreground border border-primary/20"
      : who === "tool"
      ? "bg-amber-500/10 text-foreground border border-amber-500/20 italic"
      : "bg-slate-500/10 text-muted-foreground border border-slate-500/20 italic";

  const labelColor =
    who === "human"
      ? "text-cyan-500"
      : who === "sofia"
      ? "text-primary"
      : who === "tool"
      ? "text-amber-500"
      : who === "system"
      ? "text-slate-500"
      : "text-muted-foreground";

  const Icon =
    who === "user"
      ? User
      : who === "human"
      ? Headphones
      : who === "tool"
      ? Bot
      : Bot;

  const label =
    who === "user"
      ? "Lead"
      : who === "human"
      ? isMine
        ? "Você"
        : "Operador"
      : who === "sofia"
      ? "Sofia"
      : who === "tool"
      ? "Ferramenta"
      : "Sistema";

  if (!msg.content && !msg.deleted) return null;

  return (
    <div className={cn("flex flex-col group", align)}>
      <div className="flex items-center gap-1.5 mb-1 text-[10px]">
        <Icon className={cn("h-3 w-3", labelColor)} />
        <span className={cn("font-medium", labelColor)}>{label}</span>
        {msg.created_at && (
          <span className="text-muted-foreground/60">
            {new Date(msg.created_at).toLocaleTimeString("pt-BR", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        )}
        {msg.edited_at && !msg.deleted && (
          <span
            className="text-muted-foreground/60 italic"
            title={`Editada ${msg.edit_count || 1}× — última em ${new Date(
              msg.edited_at,
            ).toLocaleString("pt-BR")}`}
          >
            (editado)
          </span>
        )}
        {sending && <Loader2 className="h-3 w-3 animate-spin opacity-60" />}
        {!sending && isMine && !msg.deleted && (
          <CheckCheck className="h-3 w-3 text-cyan-500/70" />
        )}
      </div>

      {/* Bolha (ou edit form) */}
      {editing ? (
        <div className="max-w-[80%] w-full sm:w-[420px] flex flex-col gap-1.5">
          <textarea
            ref={editRef}
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                cancelEdit();
              } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                saveEdit();
              }
            }}
            rows={3}
            disabled={saving}
            className="resize-y px-3 py-2 text-sm rounded-md border border-cyan-500/40 bg-background focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />
          {error && (
            <p className="text-[11px] text-rose-500">{error}</p>
          )}
          <div className="flex items-center justify-end gap-1">
            <span className="text-[10px] text-muted-foreground/60 mr-2">
              Esc cancela · Ctrl+Enter salva
            </span>
            <button
              onClick={cancelEdit}
              disabled={saving}
              className="px-2 py-1 text-[11px] rounded-md hover:bg-muted text-muted-foreground"
            >
              Cancelar
            </button>
            <button
              onClick={saveEdit}
              disabled={saving || !editContent.trim()}
              className="flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-md bg-cyan-500/15 text-cyan-600 border border-cyan-500/30 hover:bg-cyan-500/25 disabled:opacity-50"
            >
              {saving && <Loader2 className="h-3 w-3 animate-spin" />}
              Salvar
            </button>
          </div>
        </div>
      ) : (
        <div className="relative max-w-[80%]">
          <div
            className={cn(
              "px-3 py-2 rounded-lg text-sm whitespace-pre-wrap",
              bubbleColor,
              msg.deleted && "italic opacity-60",
            )}
          >
            {msg.deleted ? "[mensagem apagada]" : msg.content}
          </div>

          {/* Action toolbar — hover desktop, sempre visível mobile */}
          {(onReply || canMutate) && !msg.deleted && (
            <div
              className={cn(
                "absolute top-1 flex items-center gap-0.5 transition opacity-0 group-hover:opacity-100",
                "rounded-md bg-background/95 border border-border shadow-sm px-1 py-0.5",
                who === "user" ? "right-0 -translate-y-full" : "left-0 -translate-y-full",
              )}
            >
              {onReply && (
                <button
                  onClick={() => onReply(msg)}
                  className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                  title="Responder"
                >
                  <ReplyIcon className="h-3 w-3" />
                </button>
              )}
              {canMutate && onEdit && (
                <button
                  onClick={startEdit}
                  className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                  title="Editar"
                >
                  <Pencil className="h-3 w-3" />
                </button>
              )}
              {canMutate && onDelete && (
                <button
                  onClick={handleDelete}
                  className={cn(
                    "p-1 rounded transition",
                    confirmDelete
                      ? "bg-rose-500/20 text-rose-500"
                      : "hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500",
                  )}
                  title={confirmDelete ? "Clique novamente pra confirmar" : "Apagar"}
                >
                  {confirmDelete ? (
                    <X className="h-3 w-3" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Hint janela expirada */}
      {isMine && !msg.deleted && !inMutationWindow && (
        <span className="text-[9px] text-muted-foreground/40 mt-0.5">
          Janela de edição expirada
        </span>
      )}
    </div>
  );
}
