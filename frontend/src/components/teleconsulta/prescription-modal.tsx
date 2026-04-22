"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  Check,
  Loader2,
  Pill,
  ShieldCheck,
  X,
} from "lucide-react";

import type { PrescriptionItem, PrescriptionValidation } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// Modal de prescrição — 2 fases:
//   Fase 1: formulário (medicação, dose, posologia, duração, indicação)
//   Fase 2: resultado da validação (Beers + interações + alergias + dose)
//           com opção de voltar/ajustar ou confirmar adição.
// O backend já adiciona a prescrição ANTES de retornar — aqui só confirmamos
// visualmente ao médico.
// ═══════════════════════════════════════════════════════════════

const QUICK_MEDS = [
  "Paracetamol 750mg",
  "Dipirona 500mg",
  "Losartana 50mg",
  "Enalapril 10mg",
  "Metformina 500mg",
  "AAS 100mg",
  "Omeprazol 20mg",
];

type Phase = "form" | "validating" | "result";

export function PrescriptionModal({
  onClose,
  onSubmit,
  patientAllergies,
  patientMedications,
}: {
  onClose: () => void;
  onSubmit: (item: {
    medication: string;
    dose?: string;
    schedule?: string;
    duration?: string;
    indication?: string;
  }) => Promise<{ prescription_item: PrescriptionItem; validation: PrescriptionValidation }>;
  patientAllergies: string[];
  patientMedications: string[];
}) {
  const [phase, setPhase] = useState<Phase>("form");
  const [medication, setMedication] = useState("");
  const [dose, setDose] = useState("");
  const [schedule, setSchedule] = useState("");
  const [duration, setDuration] = useState("");
  const [indication, setIndication] = useState("");
  const [validation, setValidation] = useState<PrescriptionValidation | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Heurística frontend: avisa já no formulário se parece alergia conhecida
  const allergyWarning = patientAllergies.some((a) =>
    medication.toLowerCase().includes(a.toLowerCase().trim()),
  );

  async function handleSubmit() {
    if (!medication.trim()) {
      setError("Informe pelo menos o nome da medicação");
      return;
    }
    setPhase("validating");
    setError(null);
    try {
      const res = await onSubmit({
        medication: medication.trim(),
        dose: dose.trim() || undefined,
        schedule: schedule.trim() || undefined,
        duration: duration.trim() || undefined,
        indication: indication.trim() || undefined,
      });
      setValidation(res.validation);
      setPhase("result");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao validar prescrição");
      setPhase("form");
    }
  }

  function pickQuick(name: string) {
    // Split em "nome dose" naive
    const match = name.match(/^(.+?)\s+(\d+\s*\w+)$/);
    if (match) {
      setMedication(match[1]);
      setDose(match[2]);
    } else {
      setMedication(name);
    }
  }

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fade-up"
      onClick={(e) => {
        if (e.target === e.currentTarget && phase !== "validating") onClose();
      }}
    >
      <div
        className="glass-card rounded-2xl p-5 md:p-6 w-full max-w-lg shadow-2xl border border-white/[0.1] my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center">
              <Pill className="h-5 w-5 text-accent-cyan" />
            </div>
            <div>
              <h2 className="text-base font-semibold">
                {phase === "result" ? "Validação da prescrição" : "Nova prescrição"}
              </h2>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {phase === "result"
                  ? "Resultado da análise IA (Beers + interações + alergias)"
                  : "Será validada contra Critérios de Beers + medicações atuais + alergias"}
              </p>
            </div>
          </div>
          {phase !== "validating" && (
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground p-1"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Phase: form */}
        {phase === "form" && (
          <div className="space-y-3">
            {/* Quick picks */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1.5">
                Sugestões frequentes
              </div>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_MEDS.map((m) => (
                  <button
                    key={m}
                    onClick={() => pickQuick(m)}
                    className="text-[11px] px-2 py-1 rounded-md bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] hover:border-accent-cyan/30 transition-colors"
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            <FormField label="Medicação *">
              <input
                value={medication}
                onChange={(e) => setMedication(e.target.value)}
                placeholder="Ex: Losartana, Paracetamol, Metformina"
                autoFocus
                className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
              />
            </FormField>

            {allergyWarning && (
              <div className="rounded-md bg-classification-critical/10 border border-classification-critical/30 p-2.5 text-[11px] text-classification-critical flex items-start gap-2">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                <span>
                  Atenção: paciente tem alergia registrada que parece compatível com
                  este medicamento. Revise antes de continuar.
                </span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <FormField label="Dose">
                <input
                  value={dose}
                  onChange={(e) => setDose(e.target.value)}
                  placeholder="50mg, 500mg..."
                  className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
                />
              </FormField>
              <FormField label="Posologia">
                <input
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  placeholder="1x/dia manhã"
                  className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
                />
              </FormField>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <FormField label="Duração">
                <input
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  placeholder="7 dias / uso contínuo"
                  className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
                />
              </FormField>
              <FormField label="Indicação">
                <input
                  value={indication}
                  onChange={(e) => setIndication(e.target.value)}
                  placeholder="HAS, dor..."
                  className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
                />
              </FormField>
            </div>

            {/* Contexto rápido */}
            {(patientAllergies.length > 0 || patientMedications.length > 0) && (
              <div className="rounded-md bg-white/[0.02] border border-white/[0.05] p-2.5 text-[11px] leading-relaxed">
                {patientAllergies.length > 0 && (
                  <div className="mb-1">
                    <span className="text-muted-foreground">Alergias: </span>
                    <span className="text-classification-critical">
                      {patientAllergies.join(", ")}
                    </span>
                  </div>
                )}
                {patientMedications.length > 0 && (
                  <div>
                    <span className="text-muted-foreground">Em uso: </span>
                    <span className="text-foreground/80">
                      {patientMedications.slice(0, 8).join(", ")}
                      {patientMedications.length > 8 &&
                        ` (+${patientMedications.length - 8})`}
                    </span>
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="text-[11px] text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-md px-2.5 py-1.5">
                {error}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                Cancelar
              </button>
              <button
                onClick={handleSubmit}
                disabled={!medication.trim()}
                className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                Validar e adicionar
              </button>
            </div>
          </div>
        )}

        {/* Phase: validating */}
        {phase === "validating" && (
          <div className="py-10 text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-accent-cyan/10 border border-accent-cyan/25 mb-3">
              <Loader2 className="h-5 w-5 text-accent-cyan animate-spin" />
            </div>
            <p className="text-sm font-medium mb-1">Validando prescrição…</p>
            <p className="text-[11px] text-muted-foreground">
              Cruzando Critérios de Beers, alergias e medicações atuais do paciente.
            </p>
          </div>
        )}

        {/* Phase: result */}
        {phase === "result" && validation && (
          <ValidationResult validation={validation} onClose={onClose} />
        )}
      </div>
    </div>,
    document.body,
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground mb-1 block">
        {label}
      </label>
      {children}
    </div>
  );
}

function ValidationResult({
  validation,
  onClose,
}: {
  validation: PrescriptionValidation;
  onClose: () => void;
}) {
  const status = validation.validation_status;
  const hasIssues = validation.issues && validation.issues.length > 0;

  const statusCfg =
    status === "rejected"
      ? {
          icon: <AlertTriangle className="h-5 w-5" />,
          bg: "bg-classification-critical/10 border-classification-critical/30 text-classification-critical",
          title: "Prescrição rejeitada",
          subtitle: "Revise os itens abaixo e ajuste antes de prosseguir.",
        }
      : status === "approved_with_warnings"
      ? {
          icon: <AlertTriangle className="h-5 w-5" />,
          bg: "bg-classification-attention/10 border-classification-attention/30 text-classification-attention",
          title: "Aprovada com ressalvas",
          subtitle: "Adicionada à prescrição. Observe os pontos de atenção.",
        }
      : {
          icon: <Check className="h-5 w-5" />,
          bg: "bg-classification-routine/10 border-classification-routine/30 text-classification-routine",
          title: "Aprovada",
          subtitle: "Adicionada à prescrição sem ressalvas identificadas pela IA.",
        };

  return (
    <div className="space-y-3">
      <div className={`rounded-xl border p-4 ${statusCfg.bg}`}>
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">{statusCfg.icon}</div>
          <div>
            <div className="font-semibold text-sm">{statusCfg.title}</div>
            <div className="text-xs opacity-85 mt-0.5">{statusCfg.subtitle}</div>
            {validation.overall_recommendation && (
              <div className="text-xs mt-2 italic opacity-90">
                “{validation.overall_recommendation}”
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Beers */}
      {validation.beers_match?.is_potentially_inappropriate && (
        <div className="rounded-lg bg-classification-attention/5 border border-classification-attention/25 p-3">
          <div className="text-[10px] uppercase tracking-wider text-classification-attention font-semibold mb-1">
            Critérios de Beers — potencialmente inapropriado em idosos
          </div>
          {validation.beers_match.category && (
            <div className="text-xs font-medium mb-1">
              Categoria: {validation.beers_match.category}
            </div>
          )}
          <div className="text-[11px] text-muted-foreground leading-relaxed">
            {validation.beers_match.justification}
          </div>
        </div>
      )}

      {/* Dose */}
      {validation.dose_assessment?.geriatric_adjustment_note && (
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
            Ajuste geriátrico
          </div>
          <div className="text-[11px] leading-relaxed">
            {validation.dose_assessment.geriatric_adjustment_note}
          </div>
        </div>
      )}

      {/* Issues detalhados */}
      {hasIssues && (
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
            Pontos identificados
          </div>
          {validation.issues!.map((iss, i) => (
            <div
              key={i}
              className="rounded-lg bg-white/[0.02] border border-white/[0.06] p-3"
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded font-semibold ${
                    iss.severity === "critical" || iss.severity === "high"
                      ? "bg-classification-critical/15 text-classification-critical"
                      : iss.severity === "moderate"
                      ? "bg-classification-attention/15 text-classification-attention"
                      : "bg-white/[0.04] text-muted-foreground"
                  }`}
                >
                  {iss.type.replace("_", " ")} · {iss.severity}
                </span>
              </div>
              <div className="text-xs leading-relaxed text-foreground/90">
                {iss.description}
              </div>
              {iss.recommendation && (
                <div className="mt-1.5 text-[11px] text-accent-cyan leading-relaxed">
                  → {iss.recommendation}
                </div>
              )}
              {iss.reasoning && (
                <div className="mt-1 text-[11px] text-muted-foreground italic">
                  {iss.reasoning}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-end pt-2">
        <button
          onClick={onClose}
          className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors"
        >
          Entendi, fechar
        </button>
      </div>
    </div>
  );
}
