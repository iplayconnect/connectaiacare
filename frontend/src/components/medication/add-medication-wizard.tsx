"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import {
  Camera,
  Check,
  ChevronRight,
  Edit3,
  Loader2,
  Mic,
  Pill,
  Sparkles,
  Upload,
  UserCircle,
  X,
} from "lucide-react";

import {
  api,
  type ExtractedMedication,
  type MedicationImportAnalysis,
} from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// AddMedicationWizard — adiciona medicação por 3 caminhos:
//   1. Foto (Claude Vision) — caixa, receita, bula, organizador
//   2. Manual (quem já sabe digita)
//   3. (futuro) Áudio descrevendo
//
// Fluxo foto:
//   upload → análise Claude → revisão da lista → confirma → schedules criados
// ═══════════════════════════════════════════════════════════════

type Mode = "choose" | "photo" | "manual";
type PhotoStep = "select" | "uploading" | "review" | "done";

export function AddMedicationWizard({
  patientId,
  patientName,
  onClose,
  onSuccess,
}: {
  patientId: string;
  patientName?: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [mode, setMode] = useState<Mode>("choose");

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto animate-fade-up"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="glass-card rounded-2xl p-5 md:p-6 w-full max-w-2xl shadow-2xl border border-white/[0.1] my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center">
              <Pill className="h-5 w-5 text-accent-cyan" />
            </div>
            <div>
              <h2 className="text-[17px] font-semibold">
                Adicionar medicação
              </h2>
              <p className="text-[12px] text-foreground/75 mt-0.5 leading-relaxed">
                {patientName ? `Para ${patientName}. ` : ""}
                Escolha o caminho mais fácil pra você.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-foreground/55 hover:text-foreground p-1"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {mode === "choose" && (
          <ChooseMode
            onPhoto={() => setMode("photo")}
            onManual={() => setMode("manual")}
          />
        )}
        {mode === "photo" && (
          <PhotoFlow
            patientId={patientId}
            onBack={() => setMode("choose")}
            onDone={onSuccess}
          />
        )}
        {mode === "manual" && (
          <ManualFlow
            patientId={patientId}
            onBack={() => setMode("choose")}
            onDone={onSuccess}
          />
        )}
      </div>
    </div>,
    document.body,
  );
}

// ═══════════════════════════════════════════════════════════════════
// Choose mode
// ═══════════════════════════════════════════════════════════════════

function ChooseMode({
  onPhoto,
  onManual,
}: {
  onPhoto: () => void;
  onManual: () => void;
}) {
  return (
    <div className="space-y-3">
      <ModeCard
        icon={<Camera className="h-5 w-5" />}
        title="Enviar foto"
        description="Caixa do remédio, receita, bula ou organizador. Nossa IA identifica automaticamente."
        badge="mais fácil"
        onClick={onPhoto}
      />
      <ModeCard
        icon={<Edit3 className="h-5 w-5" />}
        title="Digitar manualmente"
        description="Informar nome, dose e horários direto."
        onClick={onManual}
      />
      <ModeCard
        icon={<Mic className="h-5 w-5" />}
        title="Descrever em áudio"
        description="Em breve — gravar e falar quais remédios toma."
        disabled
      />
      <ModeCard
        icon={<UserCircle className="h-5 w-5" />}
        title="Pedir ajuda pro familiar cadastrado"
        description="Em breve — envia convite pra família preencher."
        disabled
      />
    </div>
  );
}

function ModeCard({
  icon,
  title,
  description,
  badge,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  badge?: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-start gap-3 p-4 rounded-xl border transition-all text-left ${
        disabled
          ? "bg-white/[0.015] border-white/[0.04] opacity-60 cursor-not-allowed"
          : "bg-white/[0.025] border-white/[0.06] hover:border-accent-cyan/40 hover:bg-white/[0.04]"
      }`}
    >
      <div
        className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
          disabled
            ? "bg-white/[0.03] border border-white/[0.05] text-foreground/40"
            : "bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan"
        }`}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-[14px] font-semibold text-foreground">{title}</div>
          {badge && (
            <span className="text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded-full bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/25">
              {badge}
            </span>
          )}
          {disabled && (
            <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-white/[0.04] text-foreground/50">
              em breve
            </span>
          )}
        </div>
        <div className="text-[12px] text-foreground/70 leading-relaxed mt-0.5">
          {description}
        </div>
      </div>
      {!disabled && (
        <ChevronRight className="h-4 w-4 text-foreground/40 flex-shrink-0 mt-2" />
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Photo flow — upload + Claude Vision + review
// ═══════════════════════════════════════════════════════════════════

function PhotoFlow({
  patientId,
  onBack,
  onDone,
}: {
  patientId: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<PhotoStep>("select");
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<MedicationImportAnalysis | null>(null);
  const [meds, setMeds] = useState<ExtractedMedication[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sourceType, setSourceType] = useState<string>("photo_package");

  async function handleFile(file: File) {
    setError(null);
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const b64 = ev.target?.result as string;
      if (!b64) return;
      setImagePreview(b64);
      setStep("uploading");
      try {
        const res = await api.createMedicationImport(patientId, {
          source_type: sourceType,
          file_b64: b64,
          file_mime: file.type,
          uploaded_by_type: "caregiver",
        });
        setAnalysis(res);
        setMeds(res.medications || []);
        setStep("review");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao analisar");
        setStep("select");
      }
    };
    reader.readAsDataURL(file);
  }

  async function handleConfirm() {
    if (!analysis) return;
    try {
      await api.confirmMedicationImport(analysis.import_id, {
        medications: meds,
        added_by_type: "caregiver",
      });
      setStep("done");
      setTimeout(onDone, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    }
  }

  return (
    <div>
      <button
        onClick={onBack}
        className="text-[11px] text-foreground/55 hover:text-foreground mb-4"
      >
        ← Voltar
      </button>

      {step === "select" && (
        <>
          <div className="mb-4">
            <label className="text-[11px] uppercase tracking-[0.1em] text-accent-cyan/80 font-semibold mb-2 block">
              Tipo de foto
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { v: "photo_package", label: "Caixa / blister" },
                { v: "photo_prescription", label: "Receita médica" },
                { v: "photo_leaflet", label: "Bula" },
                { v: "photo_pill_organizer", label: "Organizador semanal" },
              ].map((o) => (
                <button
                  key={o.v}
                  onClick={() => setSourceType(o.v)}
                  className={`px-3 py-2 rounded-lg text-[12px] font-medium transition-colors ${
                    sourceType === o.v
                      ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan"
                      : "bg-white/[0.03] border border-white/[0.06] text-foreground/70"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
            <div className="border-2 border-dashed border-accent-cyan/30 rounded-xl p-8 text-center hover:border-accent-cyan/50 transition-colors cursor-pointer bg-accent-cyan/[0.02]">
              <Upload className="h-10 w-10 text-accent-cyan/70 mx-auto mb-3" />
              <div className="text-[14px] font-semibold mb-1">
                Toque aqui pra enviar a foto
              </div>
              <div className="text-[12px] text-foreground/70">
                JPG, PNG ou HEIC. A IA analisa em segundos.
              </div>
            </div>
          </label>

          {error && (
            <div className="mt-3 text-[12px] text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </>
      )}

      {step === "uploading" && (
        <div className="py-12 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-accent-cyan/10 border border-accent-cyan/25 mb-3">
            <Loader2 className="h-6 w-6 text-accent-cyan animate-spin" />
          </div>
          <p className="text-sm font-medium mb-1">Analisando a foto…</p>
          <p className="text-[12px] text-foreground/70">
            A IA está identificando os medicamentos. Pode levar até 10 segundos.
          </p>
          {imagePreview && (
            <div className="mt-5 max-w-xs mx-auto">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imagePreview}
                alt="Foto enviada"
                className="rounded-xl border border-white/[0.08] max-h-60 mx-auto"
              />
            </div>
          )}
        </div>
      )}

      {step === "review" && analysis && (
        <ReviewExtraction
          analysis={analysis}
          imagePreview={imagePreview}
          medications={meds}
          onChange={setMeds}
          onConfirm={handleConfirm}
          onRetry={() => {
            setStep("select");
            setAnalysis(null);
            setMeds([]);
          }}
        />
      )}

      {step === "done" && (
        <div className="py-12 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-classification-routine/15 border border-classification-routine/30 mb-3">
            <Check className="h-6 w-6 text-classification-routine" strokeWidth={3} />
          </div>
          <p className="text-base font-semibold mb-1">
            Medicações cadastradas!
          </p>
          <p className="text-[13px] text-foreground/70">
            Os lembretes automáticos já estão ativos.
          </p>
        </div>
      )}
    </div>
  );
}

function ReviewExtraction({
  analysis,
  imagePreview,
  medications,
  onChange,
  onConfirm,
  onRetry,
}: {
  analysis: MedicationImportAnalysis;
  imagePreview: string | null;
  medications: ExtractedMedication[];
  onChange: (next: ExtractedMedication[]) => void;
  onConfirm: () => void;
  onRetry: () => void;
}) {
  if (analysis.kind === "not_medication_related" || analysis.kind === "unclear") {
    return (
      <div className="py-6 text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-classification-attention/15 border border-classification-attention/30 mb-3">
          <Camera className="h-6 w-6 text-classification-attention" />
        </div>
        <p className="text-sm font-semibold mb-1">
          Não consegui identificar medicamento na foto
        </p>
        <p className="text-[13px] text-foreground/70 mb-4">
          {analysis.needs_more_info ||
            "A imagem ficou borrada ou não mostra a informação com clareza."}
        </p>
        <button
          onClick={onRetry}
          className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors"
        >
          Tentar outra foto
        </button>
      </div>
    );
  }

  if (medications.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-foreground/70">
        Nenhum medicamento foi extraído da foto. Tente uma imagem mais nítida.
        <div className="mt-4">
          <button
            onClick={onRetry}
            className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold"
          >
            Nova foto
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Sparkles className="h-4 w-4 text-accent-cyan" />
        <div className="text-[13px] font-semibold">
          Encontrei {medications.length} medicamento
          {medications.length > 1 ? "s" : ""}
        </div>
        <span className="ml-auto text-[11px] text-foreground/60">
          Confira e ajuste se precisar
        </span>
      </div>

      {analysis.notes_for_user && (
        <div className="mb-3 text-[12px] text-foreground/75 bg-accent-cyan/[0.04] border border-accent-cyan/20 rounded-lg px-3 py-2 leading-relaxed">
          {analysis.notes_for_user}
        </div>
      )}

      <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
        {medications.map((med, i) => (
          <ExtractedMedRow
            key={i}
            med={med}
            onChange={(next) => {
              const copy = [...medications];
              copy[i] = next;
              onChange(copy);
            }}
            onRemove={() =>
              onChange(medications.filter((_, idx) => idx !== i))
            }
          />
        ))}
      </div>

      <div className="flex items-center justify-between gap-3 mt-5">
        <button
          onClick={onRetry}
          className="text-[12px] text-foreground/65 hover:text-foreground"
        >
          Enviar outra foto
        </button>
        <button
          onClick={onConfirm}
          disabled={medications.length === 0}
          className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors disabled:opacity-50 inline-flex items-center gap-2"
        >
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
          Confirmar e criar lembretes
        </button>
      </div>
    </div>
  );
}

function ExtractedMedRow({
  med,
  onChange,
  onRemove,
}: {
  med: ExtractedMedication;
  onChange: (next: ExtractedMedication) => void;
  onRemove: () => void;
}) {
  const conf =
    med.field_confidence &&
    Math.min(
      med.field_confidence.name ?? 1,
      med.field_confidence.dose ?? 1,
      med.field_confidence.schedule ?? 1,
    );
  const lowConf = conf !== undefined && conf < 0.7;

  return (
    <div
      className={`rounded-xl p-3 border ${
        lowConf
          ? "bg-classification-attention/5 border-classification-attention/25"
          : "bg-white/[0.025] border-white/[0.06]"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Pill className="h-4 w-4 text-accent-cyan" />
        </div>
        <div className="flex-1 min-w-0 space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <input
              value={med.name}
              onChange={(e) => onChange({ ...med, name: e.target.value })}
              placeholder="Nome do medicamento"
              className="rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] font-medium focus:outline-none focus:border-accent-cyan/40"
            />
            <input
              value={med.dose}
              onChange={(e) => onChange({ ...med, dose: e.target.value })}
              placeholder="Dose (ex: 50mg)"
              className="rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] focus:outline-none focus:border-accent-cyan/40"
            />
          </div>

          <input
            value={med.schedule_text || ""}
            onChange={(e) =>
              onChange({ ...med, schedule_text: e.target.value })
            }
            placeholder="Posologia (ex: 1 comprimido 8/8h)"
            className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[12px] focus:outline-none focus:border-accent-cyan/40"
          />

          {med.indication && (
            <div className="text-[11px] text-foreground/65">
              Indicação: {med.indication}
            </div>
          )}

          {med.warnings && med.warnings.length > 0 && (
            <div className="text-[11px] text-classification-attention">
              ⚠ {med.warnings.join(" · ")}
            </div>
          )}

          {lowConf && (
            <div className="text-[10px] uppercase tracking-wider text-classification-attention font-semibold">
              Confiança baixa — revise antes de confirmar
            </div>
          )}
        </div>
        <button
          onClick={onRemove}
          className="text-foreground/40 hover:text-classification-critical text-[11px] flex-shrink-0"
          title="Remover"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Manual flow
// ═══════════════════════════════════════════════════════════════════

function ManualFlow({
  patientId,
  onBack,
  onDone,
}: {
  patientId: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState("");
  const [dose, setDose] = useState("");
  const [scheduleType, setScheduleType] = useState<string>("fixed_daily");
  const [timesStr, setTimesStr] = useState("08:00, 20:00");
  const [indication, setIndication] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!name.trim() || !dose.trim()) {
      setError("Informe nome e dose");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const times = timesStr
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .map((t) => (t.length === 5 ? t : t.padStart(5, "0")));
      await api.createMedicationSchedule(patientId, {
        medication_name: name.trim(),
        dose: dose.trim(),
        schedule_type: scheduleType as "fixed_daily",
        times_of_day: scheduleType === "prn" ? undefined : times,
        special_instructions: indication.trim() || undefined,
        source_type: "manual_admin",
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <button
        onClick={onBack}
        className="text-[11px] text-foreground/55 hover:text-foreground mb-4"
      >
        ← Voltar
      </button>

      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <Field label="Medicação *">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Losartana"
              autoFocus
              className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] focus:outline-none focus:border-accent-cyan/40"
            />
          </Field>
          <Field label="Dose *">
            <input
              value={dose}
              onChange={(e) => setDose(e.target.value)}
              placeholder="Ex: 50mg ou 1 comprimido"
              className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] focus:outline-none focus:border-accent-cyan/40"
            />
          </Field>
        </div>

        <Field label="Tipo de uso">
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { v: "fixed_daily", label: "Todo dia" },
              { v: "fixed_weekly", label: "Dias da semana" },
              { v: "prn", label: "Se necessário" },
            ].map((o) => (
              <button
                key={o.v}
                onClick={() => setScheduleType(o.v)}
                className={`px-2.5 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                  scheduleType === o.v
                    ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan"
                    : "bg-white/[0.03] border border-white/[0.06] text-foreground/70"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </Field>

        {scheduleType !== "prn" && (
          <Field label="Horários (separe por vírgula)">
            <input
              value={timesStr}
              onChange={(e) => setTimesStr(e.target.value)}
              placeholder="08:00, 20:00"
              className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] font-mono focus:outline-none focus:border-accent-cyan/40"
            />
          </Field>
        )}

        <Field label="Para quê serve (opcional)">
          <input
            value={indication}
            onChange={(e) => setIndication(e.target.value)}
            placeholder="Ex: Pressão alta, dor, ansiedade"
            className="w-full rounded-md bg-black/30 border border-white/[0.06] px-2.5 py-1.5 text-[13px] focus:outline-none focus:border-accent-cyan/40"
          />
        </Field>

        {error && (
          <div className="text-[12px] text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-md px-2.5 py-1.5">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onBack}
            className="text-[12px] text-foreground/60 px-3 py-1.5"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name.trim() || !dose.trim()}
            className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" strokeWidth={3} />}
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-[0.1em] text-accent-cyan/80 font-semibold mb-1 block">
        {label}
      </label>
      {children}
    </div>
  );
}
