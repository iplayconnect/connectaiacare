"use client";

import { useState } from "react";
import { Check, Loader2, Save, Sparkles } from "lucide-react";

import type { SoapDocument } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// SOAP Editor — 4 seções (Subjetivo / Objetivo / Avaliação / Plano)
// Campos críticos são editáveis inline. O médico SEMPRE revisa
// antes de assinar — nada é auto-committed.
// ═══════════════════════════════════════════════════════════════

export function SoapEditor({
  soap,
  onChange,
  onSave,
  saving,
  disabled = false,
}: {
  soap: SoapDocument;
  onChange: (next: SoapDocument) => void;
  onSave: (next: SoapDocument) => Promise<void>;
  saving: boolean;
  disabled?: boolean;
}) {
  const [dirty, setDirty] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  function patch(partial: Partial<SoapDocument>) {
    const next = { ...soap, ...partial };
    onChange(next);
    setDirty(true);
    setJustSaved(false);
  }

  function patchSection<K extends keyof SoapDocument>(
    key: K,
    updates: Partial<SoapDocument[K]>,
  ) {
    const next = {
      ...soap,
      [key]: { ...(soap[key] as object), ...updates },
    } as SoapDocument;
    onChange(next);
    setDirty(true);
    setJustSaved(false);
  }

  async function handleSave() {
    await onSave(soap);
    setDirty(false);
    setJustSaved(true);
    setTimeout(() => setJustSaved(false), 2200);
  }

  return (
    <div className="space-y-5">
      {/* Nota pro scribe */}
      {soap.scribe_confidence?.notes_for_doctor && (
        <div className="rounded-lg bg-accent-cyan/[0.04] border border-accent-cyan/20 p-3 flex items-start gap-2.5">
          <Sparkles className="h-4 w-4 text-accent-cyan flex-shrink-0 mt-0.5" />
          <div className="text-xs text-muted-foreground leading-relaxed">
            <span className="text-accent-cyan font-medium">Nota do scribe: </span>
            {soap.scribe_confidence.notes_for_doctor}
          </div>
        </div>
      )}

      {/* S — Subjetivo */}
      <SoapBlock letter="S" title="Subjetivo" tint="cyan">
        <Field
          label="Queixa principal"
          value={soap.subjective.chief_complaint || ""}
          onChange={(v) => patchSection("subjective", { chief_complaint: v })}
          placeholder="Ex: dor no joelho direito há 3 dias"
          disabled={disabled}
        />
        <TextArea
          label="História da doença atual (HDA)"
          value={soap.subjective.history_of_present_illness || ""}
          onChange={(v) =>
            patchSection("subjective", { history_of_present_illness: v })
          }
          rows={4}
          placeholder="Início, localização, intensidade, fatores que melhoram/pioram, sintomas associados..."
          disabled={disabled}
        />
        {soap.subjective.patient_quotes &&
          soap.subjective.patient_quotes.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
                Citações do paciente
              </div>
              <div className="space-y-1">
                {soap.subjective.patient_quotes.map((q, i) => (
                  <div
                    key={i}
                    className="text-xs italic text-muted-foreground border-l-2 border-accent-cyan/40 pl-2.5 py-0.5"
                  >
                    &ldquo;{q}&rdquo;
                  </div>
                ))}
              </div>
            </div>
          )}
      </SoapBlock>

      {/* O — Objetivo */}
      <SoapBlock letter="O" title="Objetivo" tint="teal">
        <TextArea
          label="Sinais vitais mencionados"
          value={soap.objective.vital_signs_reported_in_consult || ""}
          onChange={(v) =>
            patchSection("objective", { vital_signs_reported_in_consult: v })
          }
          rows={2}
          placeholder="Ex: PA 130/80, FC 72, afebril. (Vitais de sensores dos últimos dias são anexados ao FHIR.)"
          disabled={disabled}
        />
        <TextArea
          label="Exame físico (teleconsulta — limitado)"
          value={soap.objective.physical_exam_findings || ""}
          onChange={(v) =>
            patchSection("objective", { physical_exam_findings: v })
          }
          rows={3}
          placeholder="Achados observáveis via vídeo: fácies, fala, mobilidade aparente, aspecto geral..."
          disabled={disabled}
        />
        <Field
          label="Exames laboratoriais mencionados"
          value={soap.objective.lab_results_mentioned || ""}
          onChange={(v) =>
            patchSection("objective", { lab_results_mentioned: v })
          }
          placeholder="Opcional · deixe vazio se não houve"
          disabled={disabled}
        />
      </SoapBlock>

      {/* A — Avaliação */}
      <SoapBlock letter="A" title="Avaliação" tint="violet">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
            Hipótese diagnóstica principal
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input
              disabled={disabled}
              value={soap.assessment.primary_hypothesis?.description || ""}
              onChange={(e) =>
                patchSection("assessment", {
                  primary_hypothesis: {
                    ...(soap.assessment.primary_hypothesis || {}),
                    description: e.target.value,
                  },
                })
              }
              placeholder="Descrição clínica"
              className="md:col-span-2 rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
            />
            <input
              disabled={disabled}
              value={soap.assessment.primary_hypothesis?.icd10 || ""}
              onChange={(e) =>
                patchSection("assessment", {
                  primary_hypothesis: {
                    ...(soap.assessment.primary_hypothesis || {}),
                    icd10: e.target.value,
                  },
                })
              }
              placeholder="CID-10"
              className="rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm font-mono disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
            />
          </div>
        </div>

        <TextArea
          label="Raciocínio clínico"
          value={soap.assessment.clinical_reasoning || ""}
          onChange={(v) => patchSection("assessment", { clinical_reasoning: v })}
          rows={3}
          placeholder="Justifique a hipótese. Correlacione com antecedentes, sintomas e exames."
          disabled={disabled}
        />

        {soap.assessment.differential_diagnoses &&
          soap.assessment.differential_diagnoses.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
                Diagnósticos diferenciais
              </div>
              <ul className="space-y-1">
                {soap.assessment.differential_diagnoses.map((dx, i) => (
                  <li
                    key={i}
                    className="text-xs bg-white/[0.02] border border-white/[0.05] rounded-md px-2.5 py-1.5"
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-foreground/90 font-medium">
                        {dx.description}
                      </span>
                      {dx.icd10 && (
                        <span className="text-[10px] font-mono text-muted-foreground px-1.5 py-0.5 bg-black/20 rounded">
                          {dx.icd10}
                        </span>
                      )}
                    </div>
                    {dx.reasoning && (
                      <div className="text-muted-foreground italic mt-0.5">
                        {dx.reasoning}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

        {soap.assessment.active_problems_confirmed &&
          soap.assessment.active_problems_confirmed.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
                Problemas ativos confirmados
              </div>
              <div className="flex flex-wrap gap-1">
                {soap.assessment.active_problems_confirmed.map((p, i) => (
                  <span
                    key={i}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
      </SoapBlock>

      {/* P — Plano */}
      <SoapBlock letter="P" title="Plano" tint="emerald">
        <MedicationPlan
          plan={soap.plan.medications || {}}
          disabled={disabled}
          onChange={(meds) =>
            patchSection("plan", {
              medications: { ...(soap.plan.medications || {}), ...meds },
            })
          }
        />

        <StringList
          label="Orientações não-farmacológicas"
          items={soap.plan.non_pharmacological || []}
          onChange={(items) =>
            patchSection("plan", { non_pharmacological: items })
          }
          placeholder="Ex: repouso relativo, hidratação oral, compressa morna 3x/dia..."
          disabled={disabled}
        />

        <StringList
          label="Exames solicitados"
          items={soap.plan.diagnostic_tests_requested || []}
          onChange={(items) =>
            patchSection("plan", { diagnostic_tests_requested: items })
          }
          placeholder="Ex: hemograma, função renal, RX joelho AP+perfil..."
          disabled={disabled}
        />

        <StringList
          label="Encaminhamentos"
          items={soap.plan.referrals || []}
          onChange={(items) => patchSection("plan", { referrals: items })}
          placeholder="Ex: ortopedia presencial em 15 dias..."
          disabled={disabled}
        />

        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
            Retorno / Seguimento
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <input
              disabled={disabled}
              value={soap.plan.return_follow_up?.when || ""}
              onChange={(e) =>
                patchSection("plan", {
                  return_follow_up: {
                    ...(soap.plan.return_follow_up || {}),
                    when: e.target.value,
                  },
                })
              }
              placeholder="Ex: reavaliar em 7 dias"
              className="rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
            />
            <input
              disabled={disabled}
              value={soap.plan.return_follow_up?.modality || ""}
              onChange={(e) =>
                patchSection("plan", {
                  return_follow_up: {
                    ...(soap.plan.return_follow_up || {}),
                    modality: e.target.value,
                  },
                })
              }
              placeholder="Modalidade: presencial / teleconsulta / flexível"
              className="rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
            />
          </div>
          {soap.plan.return_follow_up?.trigger_signs &&
            soap.plan.return_follow_up.trigger_signs.length > 0 && (
              <div className="mt-2">
                <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1">
                  Sinais de alerta para retorno imediato
                </div>
                <div className="flex flex-wrap gap-1">
                  {soap.plan.return_follow_up.trigger_signs.map((s, i) => (
                    <span
                      key={i}
                      className="text-[11px] px-2 py-0.5 rounded-full bg-classification-attention/10 border border-classification-attention/25 text-classification-attention"
                    >
                      ⚠ {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
        </div>

        <TextArea
          label="Orientações ao paciente/cuidador"
          value={soap.plan.patient_education || ""}
          onChange={(v) => patchSection("plan", { patient_education: v })}
          rows={3}
          placeholder="Em linguagem simples — como tomar o remédio, quando procurar atendimento, sinais de alerta..."
          disabled={disabled}
        />
      </SoapBlock>

      {/* Save */}
      {!disabled && (
        <div className="flex items-center justify-between pt-2">
          <div className="text-[11px] text-muted-foreground">
            {dirty ? (
              <span className="text-classification-attention">
                • Alterações não salvas
              </span>
            ) : justSaved ? (
              <span className="text-classification-routine inline-flex items-center gap-1">
                <Check className="h-3 w-3" /> Salvo
              </span>
            ) : (
              <span>Sincronizado</span>
            )}
          </div>
          <button
            disabled={!dirty || saving}
            onClick={handleSave}
            className="px-3 py-1.5 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {saving ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Save className="h-3 w-3" />
            )}
            Salvar alterações
          </button>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Blocks
// ═══════════════════════════════════════════════════════════════

function SoapBlock({
  letter,
  title,
  tint,
  children,
}: {
  letter: string;
  title: string;
  tint: "cyan" | "teal" | "violet" | "emerald";
  children: React.ReactNode;
}) {
  const colors: Record<string, string> = {
    cyan: "bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan",
    teal: "bg-accent-teal/10 border-accent-teal/30 text-accent-teal",
    violet: "bg-violet-500/10 border-violet-500/30 text-violet-300",
    emerald: "bg-emerald-500/10 border-emerald-500/30 text-emerald-300",
  };
  return (
    <div className="rounded-xl bg-white/[0.015] border border-white/[0.05] p-4">
      <div className="flex items-center gap-3 mb-3 pb-2 border-b border-white/[0.05]">
        <div
          className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm border ${colors[tint]}`}
        >
          {letter}
        </div>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="space-y-3.5">{children}</div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5 block">
        {label}
      </label>
      <input
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
      />
    </div>
  );
}

function TextArea({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5 block">
        {label}
      </label>
      <textarea
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-2 text-sm leading-relaxed disabled:opacity-60 focus:outline-none focus:border-accent-cyan/40"
      />
    </div>
  );
}

function StringList({
  label,
  items,
  onChange,
  placeholder,
  disabled,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const v = draft.trim();
    if (!v) return;
    onChange([...items, v]);
    setDraft("");
  }

  return (
    <div>
      <label className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5 block">
        {label}
      </label>
      {items.length > 0 && (
        <ul className="space-y-1 mb-2">
          {items.map((item, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-sm bg-white/[0.02] border border-white/[0.05] rounded-md px-2.5 py-1.5"
            >
              <span className="text-muted-foreground mt-0.5">•</span>
              <span className="flex-1">{item}</span>
              {!disabled && (
                <button
                  onClick={() => onChange(items.filter((_, idx) => idx !== i))}
                  className="text-muted-foreground hover:text-classification-critical text-[11px]"
                >
                  remover
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!disabled && (
        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            placeholder={placeholder}
            className="flex-1 rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
          />
          <button
            onClick={add}
            disabled={!draft.trim()}
            className="px-3 py-1.5 rounded-md bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] disabled:opacity-50"
          >
            + Adicionar
          </button>
        </div>
      )}
    </div>
  );
}

function MedicationPlan({
  plan,
  onChange,
  disabled,
}: {
  plan: NonNullable<SoapDocument["plan"]["medications"]>;
  onChange: (meds: NonNullable<SoapDocument["plan"]["medications"]>) => void;
  disabled?: boolean;
}) {
  const sections: Array<{
    key: "continued" | "adjusted" | "started" | "suspended";
    label: string;
    tint: string;
  }> = [
    { key: "continued", label: "Mantidas", tint: "bg-white/[0.04] border-white/[0.08] text-foreground/80" },
    { key: "adjusted", label: "Ajustadas", tint: "bg-classification-attention/10 border-classification-attention/25 text-classification-attention" },
    { key: "started", label: "Iniciadas", tint: "bg-accent-cyan/10 border-accent-cyan/25 text-accent-cyan" },
    { key: "suspended", label: "Suspensas", tint: "bg-classification-critical/10 border-classification-critical/25 text-classification-critical" },
  ];

  const hasAny = sections.some((s) => (plan[s.key] || []).length > 0);
  if (!hasAny && disabled) return null;

  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
        Medicações — revisão e ajuste
      </div>
      {hasAny ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {sections.map((s) => {
            const items = plan[s.key] || [];
            if (items.length === 0) return null;
            return (
              <div key={s.key} className={`rounded-lg border px-2.5 py-2 ${s.tint}`}>
                <div className="text-[10px] font-semibold uppercase tracking-wider mb-1 opacity-80">
                  {s.label}
                </div>
                <ul className="space-y-0.5 text-xs">
                  {items.map((m, i) => (
                    <li key={i}>• {m}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground italic">
          Nenhum ajuste medicamentoso identificado pela IA. Adicione manualmente ou use
          a seção de prescrição abaixo para registrar medicações iniciadas.
        </div>
      )}
    </div>
  );
}
