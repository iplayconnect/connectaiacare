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
  ThumbsUp,
  ThumbsDown,
  ArrowLeft,
  AlertCircle,
  Footprints,
  TrendingUp,
  PillBottle,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// /admin/governance/corpus-review — revisão clínica do gold-standard.
//
// UX (refeito 2026-05-09): força decisão explícita Concordo/Discordo
// pra evitar viés de "salvar sem revisar" (estado anterior tinha 100%
// concordância falsa). Quando Discordar, motivo é OBRIGATÓRIO.
// ═══════════════════════════════════════════════════════════════

const EVENT_TYPES: {
  code: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { code: "relato_geral", label: "Relato geral", hint: "informativo, sem ação clínica", icon: MessageSquare },
  { code: "cuidado_higiene", label: "Higiene/cuidado", hint: "banho, fralda, curativo, troca de posição (mobilização)", icon: Heart },
  { code: "alimentacao_hidratacao", label: "Alimentação/Hidratação", hint: "comeu, bebeu, recusou alimentação", icon: Droplet },
  { code: "medicacao", label: "Medicação", hint: "tomou, não tomou, dose perdida (sem efeito adverso reportado)", icon: Pill },
  { code: "evento_adverso_medicamentoso", label: "Evento adverso medicamentoso (EAM)", hint: "reação ao remédio: efeito colateral, alergia, interação", icon: PillBottle },
  { code: "sinal_vital", label: "Sinal vital", hint: "Pressão Arterial (PA), Frequência Cardíaca (FC), Frequência Respiratória (FR), Saturação de Oxigênio (SpO2), Glicemia Capilar (HGT), Temperatura", icon: Activity },
  { code: "intercorrencia", label: "Intercorrência", hint: "queda, perda de consciência, evento agudo, anafilaxia (alergia grave)", icon: AlertTriangle },
  { code: "sintoma_novo", label: "Sintoma novo", hint: "queixa nova, mal-estar (sem atribuição a fármaco)", icon: Stethoscope },
  { code: "avaliacao_funcional", label: "Avaliação funcional", hint: "Atividades Básicas de Vida Diária (ABVD) e Instrumentais (AIVD): mobilidade, autonomia, capacidade", icon: Footprints },
  { code: "evolucao_clinica", label: "Evolução clínica", hint: "update de quadro JÁ CONHECIDO (melhora/piora)", icon: TrendingUp },
  { code: "apoio_emocional", label: "Apoio emocional", hint: "cuidador: tristeza, exaustão, ansiedade", icon: HandHeart },
];

const CLASSIFICATIONS = [
  { code: "routine", label: "Rotina", color: "#34d399" },
  { code: "attention", label: "Atenção", color: "#fbbf24" },
  { code: "urgent", label: "Urgente", color: "#fb923c" },
  { code: "critical", label: "Crítico", color: "#ef4444" },
];

const TYPE_LABEL_BY_CODE: Record<string, string> = Object.fromEntries(
  EVENT_TYPES.map((e) => [e.code, e.label]),
);
const SEVERITY_LABEL_BY_CODE: Record<string, string> = Object.fromEntries(
  CLASSIFICATIONS.map((c) => [c.code, c.label]),
);

interface CorpusCase {
  id: string;
  case_code: string;
  transcript: string;
  llm_suggested_event_type: string;
  llm_suggested_classification: string | null;
  llm_rationale: string | null;
  difficulty: string | null;
  source: string | null;
  review_track?: string;
}

interface Stats {
  totals: { total_cases: number; reviewed: number; pending: number };
  agreement: { reviews_total: number; agreed: number };
  my_remaining: number;
}

type Mode = "decide" | "disagree";

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

  // Estado da decisão
  const [mode, setMode] = useState<Mode>("decide");
  const [chosenEventType, setChosenEventType] = useState<string | null>(null);
  const [chosenClassification, setChosenClassification] = useState<string | null>(null);
  const [disagreeReason, setDisagreeReason] = useState("");
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

  const resetDecisionState = () => {
    setMode("decide");
    setChosenEventType(null);
    setChosenClassification(null);
    setDisagreeReason("");
  };

  const loadNext = useCallback(
    async (skipIds: string[] = []) => {
      setError(null);
      resetDecisionState();
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

  // ─── Submit (3 paths) ──────────────────────────────────────────

  // Path A: "Concordo" — aceita sugestão LLM tal como está.
  const submitAgree = async () => {
    if (!current) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.request(`/api/admin/corpus-review/${current.id}`, {
        method: "POST",
        body: JSON.stringify({
          expected_event_type: current.llm_suggested_event_type,
          expected_classification: current.llm_suggested_classification,
          // Sem note — concordância é registro silencioso
        }),
      });
      await loadStats();
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro salvando concordância");
    } finally {
      setSubmitting(false);
    }
  };

  // Path B: "Discordo" — exige re-classificação + motivo obrigatório.
  const submitDisagree = async () => {
    if (!current || !chosenEventType) {
      setError("Selecione a categoria que você considera correta.");
      return;
    }
    if (!disagreeReason.trim()) {
      setError("Descreva o motivo da discordância (obrigatório).");
      return;
    }
    // Validação: se mantém a mesma categoria + severidade do LLM, não é discordância real
    const sameType = chosenEventType === current.llm_suggested_event_type;
    const sameSev = chosenClassification === current.llm_suggested_classification;
    if (sameType && sameSev) {
      setError(
        "Você marcou exatamente o que o LLM sugeriu. Se concorda, use o botão \"Concordo\".",
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const reasonBlock = `[DISCORDÂNCIA]\n${disagreeReason.trim()}`;
      await api.request(`/api/admin/corpus-review/${current.id}`, {
        method: "POST",
        body: JSON.stringify({
          expected_event_type: chosenEventType,
          expected_classification: chosenClassification,
          note: reasonBlock,
        }),
      });
      await loadStats();
      await loadNext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro salvando discordância");
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
          Você lê o relato + sugestão do LLM e decide:{" "}
          <strong className="text-foreground">concordo</strong> (aceita como
          gold-standard) ou{" "}
          <strong className="text-foreground">discordo</strong> (re-classifica
          com justificativa obrigatória).
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
          </div>

          {/* SUGESTÃO LLM (sempre visível, em destaque) */}
          <div className="rounded-xl border border-accent-cyan/30 bg-accent-cyan/[0.04] p-4 sm:p-5">
            <div className="text-[11px] uppercase tracking-wider text-accent-cyan/80 mb-2 flex items-center gap-1.5">
              <Sparkles className="h-3 w-3" />
              Sugestão do LLM
            </div>
            <div className="space-y-1.5">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">categoria:</span>
                <span className="text-base font-semibold text-foreground">
                  {TYPE_LABEL_BY_CODE[current.llm_suggested_event_type] ||
                    current.llm_suggested_event_type}
                </span>
              </div>
              {current.llm_suggested_classification && (
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">severidade:</span>
                  <span
                    className="text-sm font-semibold"
                    style={{
                      color:
                        CLASSIFICATIONS.find(
                          (c) => c.code === current.llm_suggested_classification,
                        )?.color || "inherit",
                    }}
                  >
                    {SEVERITY_LABEL_BY_CODE[current.llm_suggested_classification] ||
                      current.llm_suggested_classification}
                  </span>
                </div>
              )}
              {current.llm_rationale && (
                <details className="text-xs text-muted-foreground mt-1">
                  <summary className="cursor-pointer hover:text-foreground">
                    Justificativa do LLM
                  </summary>
                  <div className="mt-1.5 pl-3 border-l border-accent-cyan/20 italic">
                    {current.llm_rationale}
                  </div>
                </details>
              )}
            </div>
          </div>

          {/* MODO DECIDE: 2 botões enormes ─────────────────── */}
          {mode === "decide" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={submitAgree}
                  disabled={submitting}
                  className="flex flex-col items-center justify-center gap-1.5 py-5 rounded-xl border-2 border-classification-routine/40 bg-classification-routine/10 hover:bg-classification-routine/20 transition disabled:opacity-50"
                >
                  {submitting ? (
                    <Loader2 className="h-6 w-6 animate-spin text-classification-routine" />
                  ) : (
                    <ThumbsUp className="h-6 w-6 text-classification-routine" />
                  )}
                  <span className="text-base font-semibold text-classification-routine">
                    Concordo
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    aceito como gold-standard
                  </span>
                </button>
                <button
                  onClick={() => {
                    // Pre-fill com a sugestão pra revisor ajustar a partir dela
                    setChosenEventType(current.llm_suggested_event_type);
                    setChosenClassification(current.llm_suggested_classification);
                    setMode("disagree");
                  }}
                  disabled={submitting}
                  className="flex flex-col items-center justify-center gap-1.5 py-5 rounded-xl border-2 border-classification-urgent/40 bg-classification-urgent/10 hover:bg-classification-urgent/20 transition disabled:opacity-50"
                >
                  <ThumbsDown className="h-6 w-6 text-classification-urgent" />
                  <span className="text-base font-semibold text-classification-urgent">
                    Discordo
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    re-classificar com justificativa
                  </span>
                </button>
              </div>

              {error && (
                <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {error}
                </div>
              )}

              <div className="flex justify-center pt-2">
                <button
                  onClick={skip}
                  disabled={submitting}
                  className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50 text-muted-foreground"
                >
                  <SkipForward className="h-4 w-4" />
                  Não tenho opinião agora — passar pro próximo
                </button>
              </div>
            </>
          )}

          {/* MODO DISAGREE: re-classificação + motivo OBRIGATÓRIO ─ */}
          {mode === "disagree" && (
            <>
              <div className="rounded-md border border-classification-urgent/30 bg-classification-urgent/[0.04] px-3 py-2 text-xs text-classification-urgent">
                Você marcou <strong>discordância</strong>. Reclassifique e
                explique o motivo.
              </div>

              {/* Categorias */}
              <div>
                <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 px-1">
                  Categoria correta
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
                                  title="O LLM sugeriu esta opção"
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

              {/* Severidade */}
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

              {/* Motivo OBRIGATÓRIO */}
              <div>
                <label className="text-xs uppercase tracking-wider text-classification-urgent mb-2 px-1 block">
                  Motivo da discordância{" "}
                  <span className="normal-case opacity-80">(obrigatório)</span>
                </label>
                <textarea
                  value={disagreeReason}
                  onChange={(e) => setDisagreeReason(e.target.value)}
                  placeholder="Ex: Recusa repetida de água em idoso é sintoma_novo, não relato_geral — pode indicar delirium incipiente."
                  rows={4}
                  required
                  className="w-full bg-white/[0.03] border border-classification-urgent/30 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-classification-urgent/60"
                />
                <p className="text-[10.5px] text-muted-foreground mt-1.5 px-1">
                  Esse texto fica registrado no review pra audit + entra no
                  treinamento do classificador.
                </p>
              </div>

              {error && (
                <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {error}
                </div>
              )}

              {/* Ações */}
              <div className="flex justify-between gap-2 sticky bottom-2 bg-[hsl(222,47%,7%)]/90 backdrop-blur p-2 rounded-xl border border-white/10">
                <button
                  onClick={() => {
                    resetDecisionState();
                  }}
                  disabled={submitting}
                  className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Voltar
                </button>
                <button
                  onClick={submitDisagree}
                  disabled={
                    submitting || !chosenEventType || !disagreeReason.trim()
                  }
                  className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-classification-urgent text-slate-900 font-medium disabled:opacity-40 disabled:cursor-not-allowed flex-1 justify-center"
                >
                  {submitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  Salvar discordância
                </button>
              </div>
            </>
          )}
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
