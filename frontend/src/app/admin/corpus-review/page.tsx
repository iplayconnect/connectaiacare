"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Sparkles,
  CheckCircle2,
  SkipForward,
  Loader2,
  Send,
  Heart,
  Droplet,
  Pill,
  Activity,
  AlertTriangle,
  Stethoscope,
  HandHeart,
  MessageSquare,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// /admin/corpus-review — revisão clínica do gold-standard.
// Um caso por vez, 8 botões, campo de nota opcional. Otimizada
// pra mobile (alvo: Henrique revisar do celular no café).
// ═══════════════════════════════════════════════════════════════

const EVENT_TYPES: {
  code: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { code: "relato_geral", label: "Relato geral", hint: "informativo, sem ação clínica", icon: MessageSquare },
  { code: "cuidado_higiene", label: "Higiene/cuidado", hint: "banho, fralda, curativo, troca", icon: Heart },
  { code: "alimentacao_hidratacao", label: "Alimentação/Hidratação", hint: "comeu, bebeu, recusou", icon: Droplet },
  { code: "medicacao", label: "Medicação", hint: "tomou, não tomou, reagiu", icon: Pill },
  { code: "sinal_vital", label: "Sinal vital", hint: "PA, FC, FR, SpO2, glicemia, temp", icon: Activity },
  { code: "intercorrencia", label: "Intercorrência", hint: "queda, perda de consciência, evento agudo", icon: AlertTriangle },
  { code: "sintoma_novo", label: "Sintoma novo", hint: "queixa, mal-estar, mudança de comportamento", icon: Stethoscope },
  { code: "apoio_emocional", label: "Apoio emocional", hint: "tristeza, exaustão, ansiedade", icon: HandHeart },
];

const CLASSIFICATIONS = [
  { code: "routine", label: "Rotina", color: "#34d399" },
  { code: "attention", label: "Atenção", color: "#fbbf24" },
  { code: "urgent", label: "Urgente", color: "#fb923c" },
  { code: "critical", label: "Crítico", color: "#ef4444" },
];

interface CorpusCase {
  id: string;
  case_code: string;
  transcript: string;
  llm_suggested_event_type: string;
  llm_suggested_classification: string | null;
  llm_rationale: string | null;
  difficulty: string | null;
  source: string | null;
}

interface Stats {
  totals: { total_cases: number; reviewed: number; pending: number };
  agreement: { reviews_total: number; agreed: number };
  my_remaining: number;
}

export default function CorpusReviewPage() {
  const { user } = useAuth();
  const allowed = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "clinical_reviewer",
    "medico",
  );

  const [current, setCurrent] = useState<CorpusCase | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  const [chosenEventType, setChosenEventType] = useState<string | null>(null);
  const [chosenClassification, setChosenClassification] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [skipQueue, setSkipQueue] = useState<string[]>([]);

  const loadStats = useCallback(async () => {
    try {
      const s = await api.request<Stats & { status: string }>(
        "/api/admin/corpus-review/stats",
      );
      setStats(s);
    } catch {
      // silencioso — stats não é bloqueante
    }
  }, []);

  const loadNext = useCallback(
    async (skipIds: string[] = []) => {
      setError(null);
      setChosenEventType(null);
      setChosenClassification(null);
      setNote("");
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (skipIds.length > 0) params.set("skip_id", skipIds[skipIds.length - 1]);
        const path = `/api/admin/corpus-review/next${
          params.toString() ? `?${params.toString()}` : ""
        }`;
        const res = await api.request<{
          status: string;
          case: CorpusCase | null;
          done?: boolean;
        }>(path);
        if (res.case) {
          setCurrent(res.case);
          setDone(false);
          // Preset: começa com a sugestão do LLM. Revisor confirma OU
          // muda — reduz cliques nos casos óbvios.
          setChosenEventType(res.case.llm_suggested_event_type);
          setChosenClassification(res.case.llm_suggested_classification);
        } else {
          setCurrent(null);
          setDone(true);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro carregando caso");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!allowed) return;
    loadNext();
    loadStats();
  }, [allowed, loadNext, loadStats]);

  const submit = async () => {
    if (!current || !chosenEventType) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.request(`/api/admin/corpus-review/${current.id}`, {
        method: "POST",
        body: JSON.stringify({
          expected_event_type: chosenEventType,
          expected_classification: chosenClassification,
          note: note || undefined,
        }),
      });
      await loadStats();
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro salvando");
    } finally {
      setSubmitting(false);
    }
  };

  const skip = async () => {
    if (!current) return;
    const newSkip = [...skipQueue, current.id];
    setSkipQueue(newSkip);
    await loadNext(newSkip);
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Sem acesso. Esta página é para revisores clínicos.
      </div>
    );
  }

  return (
    <div className="max-w-[760px] mx-auto px-4 sm:px-6 py-6 space-y-5">
      <header>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-accent-cyan" />
          Revisão clínica · Corpus
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Você lê o relato, escolhe a categoria que faz sentido clínico,
          e (opcionalmente) anota sua justificativa.
        </p>
      </header>

      {stats && (
        <div className="flex items-center gap-3 flex-wrap text-xs">
          <Pill2 label="Você ainda tem" value={stats.my_remaining} />
          <Pill2
            label="Revisados (total)"
            value={`${stats.totals.reviewed}/${stats.totals.total_cases}`}
          />
          {stats.agreement.reviews_total > 0 && (
            <Pill2
              label="Concordância LLM"
              value={`${Math.round(
                (100 * stats.agreement.agreed) / stats.agreement.reviews_total,
              )}%`}
            />
          )}
        </div>
      )}

      {loading && (
        <div className="text-center py-16">
          <Loader2 className="h-6 w-6 animate-spin mx-auto" />
        </div>
      )}

      {!loading && done && (
        <div className="rounded-xl border border-classification-routine/30 bg-classification-routine/5 p-8 text-center">
          <CheckCircle2 className="h-10 w-10 mx-auto text-classification-routine" />
          <h2 className="text-lg font-semibold mt-3">
            Pronto — você revisou tudo!
          </h2>
          <p className="text-sm text-muted-foreground mt-2">
            Não há mais casos pendentes pra você no momento. Quando o
            corpus crescer, eles aparecem aqui automaticamente.
          </p>
        </div>
      )}

      {!loading && !done && current && (
        <>
          {/* Caso atual */}
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 sm:p-5 space-y-3">
            <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
              <div className="flex items-center gap-2 font-mono truncate">
                {current.case_code}
                {current.difficulty && (
                  <span className="px-1.5 py-0.5 rounded-full bg-white/[0.04] capitalize">
                    {current.difficulty}
                  </span>
                )}
                {current.source === "seed" && (
                  <span className="px-1.5 py-0.5 rounded-full bg-accent-cyan/10 text-accent-cyan">
                    seed
                  </span>
                )}
              </div>
            </div>
            <blockquote className="text-base sm:text-lg leading-relaxed border-l-2 border-accent-cyan/40 pl-4 py-1">
              {current.transcript}
            </blockquote>
            {current.llm_rationale && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">
                  Sugestão do LLM (clique pra abrir)
                </summary>
                <div className="mt-2 pl-3 border-l border-white/10 space-y-1">
                  <div>
                    <span className="text-muted-foreground/70">categoria:</span>{" "}
                    <span className="font-medium">
                      {current.llm_suggested_event_type}
                    </span>
                  </div>
                  {current.llm_suggested_classification && (
                    <div>
                      <span className="text-muted-foreground/70">severidade:</span>{" "}
                      <span className="font-medium">
                        {current.llm_suggested_classification}
                      </span>
                    </div>
                  )}
                  <div className="italic">{current.llm_rationale}</div>
                </div>
              </details>
            )}
          </div>

          {/* Categorias */}
          <div>
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 px-1">
              Categoria (8 opções)
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-2 gap-2">
              {EVENT_TYPES.map((et) => {
                const Icon = et.icon;
                const active = chosenEventType === et.code;
                const llmSuggested = current.llm_suggested_event_type === et.code;
                return (
                  <button
                    key={et.code}
                    onClick={() => setChosenEventType(et.code)}
                    className={`text-left p-3 rounded-lg border transition-colors ${
                      active
                        ? "bg-accent-cyan/10 border-accent-cyan/40 text-foreground"
                        : "bg-white/[0.02] border-white/10 hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <Icon
                        className={`h-4 w-4 flex-shrink-0 mt-0.5 ${
                          active ? "text-accent-cyan" : "text-muted-foreground"
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium flex items-center gap-1.5">
                          {et.label}
                          {llmSuggested && (
                            <span
                              className="text-[9px] px-1 rounded bg-accent-cyan/10 text-accent-cyan"
                              title="Sugestão do LLM"
                            >
                              LLM
                            </span>
                          )}
                        </div>
                        <div className="text-[10.5px] text-muted-foreground leading-tight mt-0.5">
                          {et.hint}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Severidade (opcional) */}
          <div>
            <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 px-1">
              Severidade <span className="normal-case opacity-60">(opcional)</span>
            </h3>
            <div className="flex gap-1.5 flex-wrap">
              {CLASSIFICATIONS.map((cls) => {
                const active = chosenClassification === cls.code;
                return (
                  <button
                    key={cls.code}
                    onClick={() =>
                      setChosenClassification(active ? null : cls.code)
                    }
                    className={`px-3 py-1.5 rounded-full border text-xs transition-colors ${
                      active ? "" : "hover:bg-white/[0.03]"
                    }`}
                    style={{
                      background: active ? `${cls.color}20` : "transparent",
                      borderColor: active ? cls.color : "rgba(255,255,255,0.1)",
                      color: active ? cls.color : "rgba(214,232,246,0.7)",
                    }}
                  >
                    {cls.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Nota */}
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-2 px-1 block">
              Justificativa clínica{" "}
              <span className="normal-case opacity-60">(opcional)</span>
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ex: marquei como sintoma_novo porque recusa repetida pode ser sinal de delirium incipiente."
              rows={3}
              className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-accent-cyan/40"
            />
          </div>

          {error && (
            <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
              {error}
            </div>
          )}

          {/* Ações */}
          <div className="flex justify-between gap-2 sticky bottom-2 bg-[hsl(222,47%,7%)]/90 backdrop-blur p-2 rounded-xl border border-white/10">
            <button
              onClick={skip}
              disabled={submitting}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50"
            >
              <SkipForward className="h-4 w-4" />
              Passar
            </button>
            <button
              onClick={submit}
              disabled={submitting || !chosenEventType}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-40 disabled:cursor-not-allowed flex-1 justify-center"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Salvar e ir pro próximo
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Pill2({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="px-3 py-1.5 rounded-full bg-white/[0.03] border border-white/10 flex items-center gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-bold tabular">{value}</span>
    </div>
  );
}
