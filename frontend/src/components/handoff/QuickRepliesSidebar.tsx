"use client";

/**
 * Sidebar de respostas rápidas pré-aprovadas.
 *
 * Usada no chat handoff (`/admin/system/operations/handoff/[id]/chat`)
 * pra operador 24/7 responder rápido em emergencia/medicacao/rotina/
 * fechamento.
 *
 * Backend: aia_health_quick_replies (migration 063). API em
 * /api/admin/quick-replies (ver admin_quick_replies_routes.py).
 *
 * Hotkeys: Ctrl+1..Ctrl+9 ativam as 9 mais usadas (sempre ativos
 * enquanto o componente estiver montado, mesmo sidebar fechada).
 *
 * `canManage`: se true, mostra create/edit/delete UI inline (admin
 * only no backend). Operadores comuns só visualizam e usam.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Loader2,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
  X,
  Zap,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface QuickReply {
  id: string;
  category: string;
  shortcut: string;
  label: string;
  content: string;
  hotkey: string | null;
  usage_count: number;
  active: boolean;
  last_used_at: string | null;
}

const CATEGORY_LABELS: Record<string, string> = {
  emergencia: "Emergência",
  medicacao: "Medicação",
  rotina: "Rotina",
  fechamento: "Fechamento",
  geral: "Geral",
};

const CATEGORY_COLORS: Record<string, string> = {
  emergencia: "bg-rose-500/15 text-rose-500 border-rose-500/30",
  medicacao: "bg-amber-500/15 text-amber-500 border-amber-500/30",
  rotina: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  fechamento: "bg-sky-500/15 text-sky-500 border-sky-500/30",
  geral: "bg-muted text-muted-foreground border-border",
};

const VALID_CATEGORIES = ["emergencia", "medicacao", "rotina", "fechamento", "geral"];

type ViewMode = "list" | "create" | "edit";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  /** Callback quando user clica numa quick reply ou aciona hotkey. */
  onSelect: (content: string) => void;
  /** Se true, exibe botões de CRUD inline (admin/super_admin). */
  canManage?: boolean;
  /** Nome do lead — substitui placeholder {nome} no content. */
  leadName?: string;
}

export function QuickRepliesSidebar({
  isOpen,
  onClose,
  onSelect,
  canManage = false,
  leadName,
}: Props) {
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [editing, setEditing] = useState<QuickReply | null>(null);

  // Form state (create/edit)
  const [formCategory, setFormCategory] = useState("rotina");
  const [formShortcut, setFormShortcut] = useState("");
  const [formLabel, setFormLabel] = useState("");
  const [formContent, setFormContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Mantém última versão do callback sem rebind do listener
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // ── Fetch ───────────────────────────────────────────────────
  const loadReplies = useCallback(async () => {
    try {
      const res = await api.request<{ items: QuickReply[] }>(
        "/api/admin/quick-replies",
      );
      setReplies(res.items || []);
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.body?.reason || e.message
          : "erro carregando",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReplies();
  }, [loadReplies]);

  // ── Substituição de placeholder {nome} ──────────────────────
  const resolveContent = useCallback(
    (raw: string) => {
      if (!leadName || !raw.includes("{nome}")) return raw;
      return raw.replaceAll("{nome}", leadName);
    },
    [leadName],
  );

  // ── Tracking de uso (best-effort) ───────────────────────────
  const trackUse = useCallback((replyId: string) => {
    api
      .request(`/api/admin/quick-replies/${replyId}/use`, { method: "POST" })
      .catch(() => {
        /* silencia — não bloquear operador */
      });
    // Atualiza local sem refetch (otimista)
    setReplies((prev) =>
      prev.map((r) =>
        r.id === replyId ? { ...r, usage_count: r.usage_count + 1 } : r,
      ),
    );
  }, []);

  const handleSelect = useCallback(
    (reply: QuickReply) => {
      const text = resolveContent(reply.content);
      onSelectRef.current(text);
      trackUse(reply.id);
    },
    [resolveContent, trackUse],
  );

  // ── Hotkeys Ctrl+1..Ctrl+9 (top 9 mais usados) ──────────────
  // Top 9 derivado da própria lista replies (já vem ordenada DESC
  // por usage_count do backend).
  const top9 = useMemo(() => replies.slice(0, 9), [replies]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Aceita Ctrl ou Cmd + 1..9. Não dispara se foco em <input>
      // tipo password/file/checkbox que tenham comportamento próprio.
      if (!(e.ctrlKey || e.metaKey)) return;
      const num = parseInt(e.key, 10);
      if (!num || num < 1 || num > 9) return;
      const reply = top9[num - 1];
      if (!reply) return;
      e.preventDefault();
      handleSelect(reply);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [top9, handleSelect]);

  // ── Filtro de exibição ──────────────────────────────────────
  const categories = useMemo(() => {
    return Array.from(new Set(replies.map((r) => r.category))).sort();
  }, [replies]);

  const filtered = useMemo(() => {
    let out = [...replies];
    if (selectedCategory) {
      out = out.filter((r) => r.category === selectedCategory);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      out = out.filter(
        (r) =>
          r.shortcut.toLowerCase().includes(q) ||
          r.label.toLowerCase().includes(q) ||
          r.content.toLowerCase().includes(q),
      );
    }
    return out;
  }, [replies, search, selectedCategory]);

  // ── CRUD ────────────────────────────────────────────────────
  const resetForm = useCallback(() => {
    setFormCategory("rotina");
    setFormShortcut("");
    setFormLabel("");
    setFormContent("");
    setFormError(null);
    setEditing(null);
  }, []);

  const startCreate = () => {
    resetForm();
    setViewMode("create");
  };

  const startEdit = (e: React.MouseEvent, reply: QuickReply) => {
    e.stopPropagation();
    setEditing(reply);
    setFormCategory(reply.category);
    setFormShortcut(reply.shortcut);
    setFormLabel(reply.label);
    setFormContent(reply.content);
    setFormError(null);
    setViewMode("edit");
  };

  const backToList = () => {
    resetForm();
    setViewMode("list");
  };

  const save = async () => {
    if (!formShortcut.trim() || !formLabel.trim() || !formContent.trim()) {
      setFormError("Atalho, título e mensagem são obrigatórios");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const payload = {
        category: formCategory,
        shortcut: formShortcut.trim().toLowerCase().replace(/\s+/g, "_"),
        label: formLabel.trim(),
        content: formContent.trim(),
      };
      if (viewMode === "edit" && editing) {
        await api.request(`/api/admin/quick-replies/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await api.request("/api/admin/quick-replies", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      await loadReplies();
      backToList();
    } catch (e) {
      const reason =
        e instanceof ApiError ? e.body?.reason || e.message : String(e);
      if (reason === "shortcut_already_exists") {
        setFormError("Esse atalho já existe. Escolha outro.");
      } else if (reason === "invalid_shortcut") {
        setFormError(
          "Atalho inválido — use apenas letras minúsculas, números e _ (2 a 40 caracteres).",
        );
      } else {
        setFormError(reason);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, reply: QuickReply) => {
    e.stopPropagation();
    if (deletingId === reply.id) {
      // segundo clique = confirma
      try {
        await api.request(`/api/admin/quick-replies/${reply.id}`, {
          method: "DELETE",
        });
        setDeletingId(null);
        await loadReplies();
      } catch (err) {
        setDeletingId(null);
        alert(
          err instanceof ApiError
            ? `Erro: ${err.body?.reason || err.message}`
            : "erro excluindo",
        );
      }
    } else {
      setDeletingId(reply.id);
      setTimeout(() => setDeletingId((curr) => (curr === reply.id ? null : curr)), 3000);
    }
  };

  // ── UI ──────────────────────────────────────────────────────
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-96 bg-background border-l border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {viewMode !== "list" && (
            <button
              onClick={backToList}
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
              title="Voltar"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <Zap className="h-4 w-4 text-amber-500 shrink-0" />
          <h3 className="font-semibold text-sm truncate">
            {viewMode === "create"
              ? "Nova resposta"
              : viewMode === "edit"
              ? "Editar resposta"
              : "Respostas rápidas"}
          </h3>
          {viewMode === "list" && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
              {filtered.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {viewMode === "list" && canManage && (
            <button
              onClick={startCreate}
              className="p-1.5 rounded hover:bg-primary/10 text-primary"
              title="Criar nova resposta"
            >
              <Plus className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title="Fechar (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* CREATE / EDIT FORM */}
      {viewMode !== "list" && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <div>
            <label className="text-[11px] font-medium text-muted-foreground mb-1 block">
              Categoria *
            </label>
            <select
              value={formCategory}
              onChange={(e) => setFormCategory(e.target.value)}
              className="w-full h-9 px-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {VALID_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c] || c}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[11px] font-medium text-muted-foreground mb-1 block">
              Atalho (slug) *
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">
                /
              </span>
              <input
                value={formShortcut}
                onChange={(e) =>
                  setFormShortcut(
                    e.target.value.replace(/\s+/g, "_").toLowerCase(),
                  )
                }
                placeholder="samu_acionado"
                className="w-full h-9 pl-6 pr-2 text-sm font-mono rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-medium text-muted-foreground mb-1 block">
              Título *
            </label>
            <input
              value={formLabel}
              onChange={(e) => setFormLabel(e.target.value)}
              placeholder="SAMU acionado"
              className="w-full h-9 px-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="text-[11px] font-medium text-muted-foreground mb-1 block">
              Mensagem *
            </label>
            <textarea
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              placeholder="Texto que será enviado pro lead..."
              rows={5}
              className="w-full px-2 py-2 text-sm rounded-md border border-border bg-background resize-y focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              Use <code className="bg-muted px-1 rounded">{"{nome}"}</code> pra
              inserir o nome do lead.
            </p>
          </div>

          {formError && (
            <div className="px-3 py-2 rounded-md bg-rose-500/10 text-rose-500 text-xs border border-rose-500/30">
              {formError}
            </div>
          )}

          {formContent.trim() && (
            <div className="p-3 rounded-md bg-muted/40 border border-border/50">
              <p className="text-[10px] font-medium text-muted-foreground mb-1">
                Preview:
              </p>
              <p className="text-xs whitespace-pre-wrap">
                {resolveContent(formContent)}
              </p>
            </div>
          )}

          <button
            onClick={save}
            disabled={
              saving ||
              !formShortcut.trim() ||
              !formLabel.trim() ||
              !formContent.trim()
            }
            className={cn(
              "w-full h-10 rounded-md font-medium text-sm flex items-center justify-center gap-2 transition",
              saving || !formShortcut.trim() || !formLabel.trim() || !formContent.trim()
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bg-primary text-primary-foreground hover:bg-primary/90",
            )}
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {viewMode === "edit" ? "Salvar alterações" : "Criar resposta"}
          </button>
        </div>
      )}

      {/* LIST VIEW */}
      {viewMode === "list" && (
        <>
          {/* Search */}
          <div className="px-4 py-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar atalho, título ou texto…"
                className="w-full h-9 pl-9 pr-3 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {/* Categorias */}
          {categories.length > 0 && (
            <div className="px-4 py-2 border-b border-border bg-muted/20 overflow-x-auto">
              <div className="flex gap-1.5">
                <button
                  onClick={() => setSelectedCategory(null)}
                  className={cn(
                    "px-2.5 py-1 rounded text-[11px] font-medium transition whitespace-nowrap",
                    selectedCategory === null
                      ? "bg-primary text-primary-foreground"
                      : "bg-background hover:bg-muted text-muted-foreground border border-border",
                  )}
                >
                  Todas
                </button>
                {categories.map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setSelectedCategory(cat)}
                    className={cn(
                      "px-2.5 py-1 rounded text-[11px] font-medium transition whitespace-nowrap",
                      selectedCategory === cat
                        ? "bg-primary text-primary-foreground"
                        : "bg-background hover:bg-muted text-muted-foreground border border-border",
                    )}
                  >
                    {CATEGORY_LABELS[cat] || cat}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Lista */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading && (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <Loader2 className="h-5 w-5 animate-spin inline" />
              </div>
            )}
            {error && (
              <div className="px-3 py-2 rounded-md bg-rose-500/10 text-rose-500 text-xs border border-rose-500/30">
                {error}
              </div>
            )}
            {!loading && !error && filtered.length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                <Zap className="h-8 w-8 inline opacity-30 mb-2" />
                <p className="text-sm">
                  {replies.length === 0
                    ? "Nenhuma resposta cadastrada ainda."
                    : "Nada encontrado."}
                </p>
                {replies.length === 0 && canManage && (
                  <button
                    onClick={startCreate}
                    className="mt-3 px-3 py-1.5 text-xs rounded-md accent-gradient text-slate-900 font-medium inline-flex items-center gap-1.5"
                  >
                    <Plus className="h-3 w-3" /> Criar primeira
                  </button>
                )}
              </div>
            )}
            {!loading &&
              !error &&
              filtered.map((reply) => {
                const positionInTop9 = top9.findIndex((r) => r.id === reply.id);
                const hotkeyHint =
                  positionInTop9 >= 0 && positionInTop9 < 9
                    ? `Ctrl+${positionInTop9 + 1}`
                    : null;
                return (
                  <div
                    key={reply.id}
                    onClick={() => handleSelect(reply)}
                    className="group p-2.5 rounded-md border border-border hover:border-primary/50 hover:bg-accent/30 cursor-pointer transition relative"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <span
                          className={cn(
                            "px-1.5 py-0.5 rounded text-[9px] font-bold border shrink-0",
                            CATEGORY_COLORS[reply.category] ||
                              CATEGORY_COLORS.geral,
                          )}
                        >
                          {(CATEGORY_LABELS[reply.category] || reply.category)
                            .slice(0, 4)
                            .toUpperCase()}
                        </span>
                        <span className="text-sm font-medium truncate">
                          {reply.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0">
                        {hotkeyHint && (
                          <span className="text-[9px] text-muted-foreground/70 font-mono px-1">
                            {hotkeyHint}
                          </span>
                        )}
                        {canManage && (
                          <div className="opacity-0 group-hover:opacity-100 transition flex items-center">
                            <button
                              onClick={(e) => startEdit(e, reply)}
                              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
                              title="Editar"
                            >
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button
                              onClick={(e) => handleDelete(e, reply)}
                              className={cn(
                                "p-1 rounded transition",
                                deletingId === reply.id
                                  ? "bg-rose-500/20 text-rose-500"
                                  : "hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500",
                              )}
                              title={
                                deletingId === reply.id
                                  ? "Clique novamente pra confirmar"
                                  : "Excluir"
                              }
                            >
                              {deletingId === reply.id ? (
                                <Check className="h-3 w-3" />
                              ) : (
                                <Trash2 className="h-3 w-3" />
                              )}
                            </button>
                          </div>
                        )}
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary transition" />
                      </div>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2 pl-1">
                      {reply.content}
                    </p>
                    <div className="flex items-center justify-between pl-1 mt-1.5">
                      <code className="text-[9px] text-muted-foreground/70 font-mono">
                        /{reply.shortcut}
                      </code>
                      {reply.usage_count > 0 && (
                        <span className="text-[9px] text-muted-foreground/70">
                          {reply.usage_count}× usado
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>

          {/* Footer */}
          <div className="px-3 py-2 border-t border-border bg-muted/20 text-center">
            <p className="text-[10px] text-muted-foreground">
              Ctrl + 1..9 dispara as 9 mais usadas
            </p>
          </div>
        </>
      )}
    </div>
  );
}
