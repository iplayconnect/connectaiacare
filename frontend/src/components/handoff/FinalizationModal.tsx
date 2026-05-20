"use client";

/**
 * FinalizationModal — desfecho estruturado pra fechar handoff.
 *
 * Substitui o modal inline antigo (textarea simples). Captura:
 *   - resolution_summary (texto livre — auditoria, obrigatório)
 *   - outcome_category   (radio — categoria do desfecho)
 *   - outcome_tags       (multi-select — issues comuns)
 *   - outcome_rating     (1-5 estrelas — auto-avaliação operador)
 *
 * Preview "próxima ação automatizada" muda conforme categoria pra dar
 * visibilidade do que vai acontecer pós-resolução (Sofia volta a
 * atender? Cria followup? Arquiva?).
 *
 * Backend: POST /api/admin/handoff/<id>/resolve com payload completo.
 * Migrations: 064_handoff_outcome_fields.sql.
 */
import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Star,
  X,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Whitelists espelham backend (admin_handoff_routes.py) ───────

interface CategoryOption {
  value: string;
  label: string;
  description: string;
  /** O que vai acontecer automaticamente após salvar. */
  nextAction: string;
  tone: "emerald" | "sky" | "amber" | "rose" | "slate";
}

const CATEGORIES: CategoryOption[] = [
  {
    value: "resolved_by_phone",
    label: "Resolvido com o lead",
    description: "Demanda atendida no chat / telefone, lead satisfeito.",
    nextAction:
      "Handoff arquivado. Sofia volta a atender o phone se houver nova mensagem.",
    tone: "emerald",
  },
  {
    value: "escalated_to_specialist",
    label: "Escalado pra especialista",
    description: "Caso passou pra médico / clínico / outra equipe.",
    nextAction:
      "Handoff arquivado. Vai criar followup_schedule pro especialista designado contatar lead.",
    tone: "sky",
  },
  {
    value: "lead_lost",
    label: "Lead perdido",
    description: "Lead não respondeu ou desistiu.",
    nextAction:
      "Handoff arquivado sem follow-up. Sofia continua em modo passivo se reaparecer.",
    tone: "amber",
  },
  {
    value: "closed_by_lead",
    label: "Encerrado pelo lead",
    description: "Lead pediu pra encerrar o atendimento explicitamente.",
    nextAction:
      "Handoff arquivado. Sofia respeita pedido e não inicia outreach proativo no phone.",
    tone: "slate",
  },
  {
    value: "system_error",
    label: "Falha do sistema",
    description: "Sofia bugou, voz caiu, integração falhou — operador resolveu manualmente.",
    nextAction:
      "Handoff arquivado + flag interna pra revisão técnica. Time de eng revisa o trace_id.",
    tone: "rose",
  },
  {
    value: "other",
    label: "Outro",
    description: "Desfecho fora dos padrões — explica no resumo.",
    nextAction: "Handoff arquivado. Sem ação automatizada — depende do resumo.",
    tone: "slate",
  },
];

interface TagOption {
  value: string;
  label: string;
}

const TAGS: TagOption[] = [
  { value: "urgencia_real", label: "Urgência real" },
  { value: "falso_positivo", label: "Falso positivo (Sofia errou triagem)" },
  { value: "medicacao_alterada", label: "Medicação alterada" },
  { value: "paciente_internado", label: "Paciente internado" },
  { value: "familia_orientada", label: "Família orientada" },
  { value: "agendamento_marcado", label: "Agendamento marcado" },
  { value: "reembolso_solicitado", label: "Reembolso solicitado" },
  { value: "fora_de_escopo", label: "Fora de escopo" },
];

const TONE_CLASSES: Record<CategoryOption["tone"], string> = {
  emerald: "bg-emerald-500/10 border-emerald-500/40 text-emerald-600",
  sky: "bg-sky-500/10 border-sky-500/40 text-sky-600",
  amber: "bg-amber-500/10 border-amber-500/40 text-amber-600",
  rose: "bg-rose-500/10 border-rose-500/40 text-rose-500",
  slate: "bg-slate-500/10 border-slate-500/40 text-slate-500",
};

interface Props {
  handoffId: string;
  isOpen: boolean;
  onClose: () => void;
  /** Callback após resolve com sucesso. Parent navega. */
  onResolved: () => void;
}

export function FinalizationModal({
  handoffId,
  isOpen,
  onClose,
  onResolved,
}: Props) {
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState<string>("");
  const [tags, setTags] = useState<Set<string>>(new Set());
  const [rating, setRating] = useState<number>(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset quando modal abre
  useEffect(() => {
    if (isOpen) {
      setSummary("");
      setCategory("");
      setTags(new Set());
      setRating(0);
      setError(null);
    }
  }, [isOpen]);

  // Esc fecha
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose, submitting]);

  const selectedCategory = useMemo(
    () => CATEGORIES.find((c) => c.value === category) || null,
    [category],
  );

  const toggleTag = (tag: string) => {
    setTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  const submit = async () => {
    if (!summary.trim()) {
      setError("Resumo do desfecho é obrigatório.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.request(`/api/admin/handoff/${handoffId}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolution_summary: summary.trim(),
          outcome_category: category || null,
          outcome_tags: tags.size > 0 ? Array.from(tags) : null,
          outcome_rating: rating > 0 ? rating : null,
        }),
      });
      onResolved();
    } catch (e) {
      const reason =
        e instanceof ApiError ? e.body?.reason || e.message : String(e);
      setError(reason);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4 py-8 overflow-y-auto">
      <div className="bg-background border border-border rounded-lg max-w-xl w-full p-5 my-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="font-semibold text-base flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Resolver handoff
            </h3>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Captura o desfecho pra coaching e analytics.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title="Fechar (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 1. Categoria (radio) */}
        <section className="mb-4">
          <label className="text-[11px] font-medium text-muted-foreground mb-2 block">
            Categoria do desfecho
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {CATEGORIES.map((c) => {
              const selected = c.value === category;
              return (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setCategory(c.value)}
                  disabled={submitting}
                  className={cn(
                    "text-left px-2.5 py-2 rounded-md border text-xs transition",
                    selected
                      ? TONE_CLASSES[c.tone]
                      : "border-border hover:border-border/80 hover:bg-muted/30 text-foreground",
                  )}
                >
                  <div className="font-medium">{c.label}</div>
                  <div
                    className={cn(
                      "text-[10px] mt-0.5",
                      selected ? "opacity-80" : "text-muted-foreground/70",
                    )}
                  >
                    {c.description}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* 2. Tags (multi-select) */}
        <section className="mb-4">
          <label className="text-[11px] font-medium text-muted-foreground mb-2 block">
            Tags (opcional)
          </label>
          <div className="flex flex-wrap gap-1.5">
            {TAGS.map((t) => {
              const selected = tags.has(t.value);
              return (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => toggleTag(t.value)}
                  disabled={submitting}
                  className={cn(
                    "px-2 py-1 rounded-full text-[10px] border transition",
                    selected
                      ? "bg-primary/15 text-primary border-primary/40"
                      : "bg-background text-muted-foreground border-border hover:border-border/80",
                  )}
                >
                  {t.label}
                </button>
              );
            })}
          </div>
        </section>

        {/* 3. Rating */}
        <section className="mb-4">
          <label className="text-[11px] font-medium text-muted-foreground mb-2 block">
            Como você avalia este atendimento?
          </label>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRating(rating === n ? 0 : n)}
                disabled={submitting}
                title={`${n} estrela${n > 1 ? "s" : ""}`}
                className="p-1 rounded hover:bg-muted transition"
              >
                <Star
                  className={cn(
                    "h-5 w-5 transition",
                    n <= rating
                      ? "fill-amber-400 text-amber-400"
                      : "text-muted-foreground/40",
                  )}
                />
              </button>
            ))}
            {rating > 0 && (
              <button
                type="button"
                onClick={() => setRating(0)}
                disabled={submitting}
                className="ml-2 text-[10px] text-muted-foreground hover:text-foreground"
              >
                Limpar
              </button>
            )}
          </div>
        </section>

        {/* 4. Resumo (obrigatório) */}
        <section className="mb-4">
          <label className="text-[11px] font-medium text-muted-foreground mb-1 block">
            Resumo do desfecho *
          </label>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={3}
            placeholder="Ex: 'Confirmei dose com farmacêutico, orientei família a aguardar 2h e me chamar de novo se piorar.'"
            disabled={submitting}
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            autoFocus
          />
          <p className="text-[10px] text-muted-foreground/70 mt-0.5">
            Vai pro audit log + prontuário. Seja específico — outros operadores podem retomar caso similar.
          </p>
        </section>

        {/* Preview da próxima ação automatizada */}
        {selectedCategory && (
          <div
            className={cn(
              "px-3 py-2 rounded-md border text-[11px] mb-4",
              TONE_CLASSES[selectedCategory.tone],
            )}
          >
            <p className="font-medium mb-0.5">Próxima ação automatizada</p>
            <p className="opacity-90">{selectedCategory.nextAction}</p>
          </div>
        )}

        {/* Erro */}
        {error && (
          <div className="px-3 py-2 rounded-md bg-rose-500/10 text-rose-500 text-xs border border-rose-500/30 mb-3">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 text-xs rounded-md hover:bg-muted text-muted-foreground"
          >
            Cancelar
          </button>
          <button
            onClick={submit}
            disabled={submitting || !summary.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
          >
            {submitting && <Loader2 className="h-3 w-3 animate-spin" />}
            Confirmar e arquivar
          </button>
        </div>
      </div>
    </div>
  );
}
