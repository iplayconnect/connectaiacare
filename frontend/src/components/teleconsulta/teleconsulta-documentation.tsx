"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  Download,
  FileText,
  Loader2,
  Pill,
  Save,
  Sparkles,
  Stethoscope,
} from "lucide-react";

import {
  api,
  type PrescriptionItem,
  type SoapDocument,
  type TeleconsultaRecord,
} from "@/lib/api";

import { PrescriptionModal } from "./prescription-modal";
import { SignCelebration } from "./sign-celebration";
import { SoapEditor } from "./soap-editor";

type LoadState = "loading" | "ready" | "not_found" | "error";

export function TeleconsultaDocumentation({
  teleconsultaId,
}: {
  teleconsultaId: string;
}) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [tc, setTc] = useState<TeleconsultaRecord | null>(null);
  const [transcription, setTranscription] = useState("");
  const [soap, setSoap] = useState<SoapDocument | null>(null);
  const [prescriptions, setPrescriptions] = useState<PrescriptionItem[]>([]);
  const [signedAt, setSignedAt] = useState<string | null>(null);

  const [generatingSoap, setGeneratingSoap] = useState(false);
  const [savingSoap, setSavingSoap] = useState(false);
  const [signing, setSigning] = useState(false);
  const [savingTranscription, setSavingTranscription] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rxOpen, setRxOpen] = useState(false);
  const [celebrationOpen, setCelebrationOpen] = useState(false);
  const [fhirBundleId, setFhirBundleId] = useState<string | null>(null);

  // ---- Load inicial ---------------------------------------------------
  const load = useCallback(async () => {
    try {
      const res = await api.getTeleconsulta(teleconsultaId);
      const record = res.teleconsulta;
      setTc(record);
      setTranscription(record.transcription_full || "");
      setSoap(record.soap);
      setPrescriptions(record.prescription || []);
      setSignedAt(record.signed_at);
      if (record.fhir_bundle && typeof record.fhir_bundle === "object") {
        const maybeId = (record.fhir_bundle as Record<string, unknown>).id;
        if (typeof maybeId === "string") setFhirBundleId(maybeId);
      }
      setLoadState("ready");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "erro";
      if (msg.includes("404")) setLoadState("not_found");
      else setLoadState("error");
      setError(msg);
    }
  }, [teleconsultaId]);

  useEffect(() => {
    load();
  }, [load]);

  // ---- Actions --------------------------------------------------------
  async function handleSaveTranscription() {
    if (!transcription.trim()) return;
    setSavingTranscription(true);
    setError(null);
    try {
      await api.saveTranscription(teleconsultaId, transcription);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar transcrição");
    } finally {
      setSavingTranscription(false);
    }
  }

  async function handleGenerateSoap() {
    if (!transcription.trim()) {
      setError("Cole ou digite a transcrição antes de gerar o SOAP.");
      return;
    }
    setGeneratingSoap(true);
    setError(null);
    try {
      // Salva transcrição primeiro (idempotente)
      await api.saveTranscription(teleconsultaId, transcription);
      const res = await api.generateSoap(teleconsultaId);
      setSoap(res.soap);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao gerar SOAP");
    } finally {
      setGeneratingSoap(false);
    }
  }

  async function handleSaveSoap(next: SoapDocument) {
    setSavingSoap(true);
    setError(null);
    try {
      await api.updateSoap(teleconsultaId, next);
      setSoap(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar SOAP");
    } finally {
      setSavingSoap(false);
    }
  }

  async function handleAddPrescription(item: {
    medication: string;
    dose?: string;
    schedule?: string;
    duration?: string;
    indication?: string;
  }) {
    const res = await api.addPrescription(teleconsultaId, item);
    setPrescriptions((prev) => [...prev, res.prescription_item]);
    return res;
  }

  async function handleSign() {
    if (!soap) {
      setError("Gere o SOAP antes de assinar.");
      return;
    }
    setSigning(true);
    setError(null);
    try {
      const res = await api.signTeleconsulta(teleconsultaId, {
        doctor_name: tc?.doctor_name_snapshot || "Dra. Ana Silva",
        doctor_crm: tc?.doctor_crm_snapshot || "CRM/RS 12345",
      });
      setSignedAt(new Date().toISOString());
      setFhirBundleId(res.fhir_bundle_id);
      setCelebrationOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao assinar");
    } finally {
      setSigning(false);
    }
  }

  // ---- Derived --------------------------------------------------------
  const patientAge = useMemo(() => {
    if (!tc?.patient_birth_date) return null;
    try {
      const bd = new Date(tc.patient_birth_date);
      const now = new Date();
      let age = now.getFullYear() - bd.getFullYear();
      const m = now.getMonth() - bd.getMonth();
      if (m < 0 || (m === 0 && now.getDate() < bd.getDate())) age--;
      return age;
    } catch {
      return null;
    }
  }, [tc?.patient_birth_date]);

  const isSigned = !!signedAt;

  // ---- Render ---------------------------------------------------------
  if (loadState === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh] gap-3 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando teleconsulta…
      </div>
    );
  }

  if (loadState === "not_found") {
    return (
      <div className="p-12 max-w-lg">
        <div className="glass-card rounded-2xl p-6 border border-white/[0.08]">
          <h2 className="text-lg font-semibold mb-2">Teleconsulta não encontrada</h2>
          <p className="text-sm text-muted-foreground mb-4">
            O registro <span className="font-mono">{teleconsultaId}</span> não existe
            ou já foi encerrado há muito tempo.
          </p>
          <Link
            href="/dashboard"
            className="text-xs text-accent-cyan hover:text-accent-teal inline-flex items-center gap-1"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Voltar ao Dashboard
          </Link>
        </div>
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="p-12 max-w-lg">
        <div className="glass-card rounded-2xl p-6 border border-classification-critical/30">
          <h2 className="text-lg font-semibold mb-2 text-classification-critical">
            Erro ao carregar
          </h2>
          <p className="text-sm text-muted-foreground mb-4">{error}</p>
          <button
            onClick={load}
            className="px-3 py-1.5 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/dashboard"
          className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-3"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Dashboard
        </Link>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center flex-shrink-0">
            <FileText className="h-6 w-6 text-accent-cyan" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl md:text-2xl font-semibold leading-tight">
              Documentação clínica
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Teleconsulta com{" "}
              <span className="text-foreground font-medium">
                {tc?.patient_full_name}
              </span>
              {patientAge !== null && (
                <span className="text-muted-foreground"> · {patientAge} anos</span>
              )}
              {tc?.patient_care_level && (
                <span className="text-muted-foreground"> · {tc.patient_care_level}</span>
              )}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.06] text-muted-foreground">
                <Stethoscope className="h-3 w-3" />
                {tc?.doctor_name_snapshot || "Dra. Ana Silva"}
              </span>
              <span className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.06] text-muted-foreground font-mono">
                sala {tc?.room_name}
              </span>
              {isSigned ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-classification-routine/15 border border-classification-routine/25 text-classification-routine font-medium">
                  <Check className="h-3 w-3" /> Assinada
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-classification-attention/15 border border-classification-attention/30 text-classification-attention">
                  rascunho
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 text-xs text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-lg px-3 py-2 flex items-start gap-2">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          <div className="flex-1">{error}</div>
          <button
            onClick={() => setError(null)}
            className="text-classification-critical/70 hover:text-classification-critical text-xs"
          >
            fechar
          </button>
        </div>
      )}

      {/* Paciente — ficha resumida */}
      <PatientBriefCard tc={tc} />

      {/* Seção 1: Transcrição */}
      <Section
        title="1 · Transcrição da consulta"
        description="Cole as notas da consulta ou a transcrição automática. A IA usará este texto para gerar o SOAP estruturado."
        defaultOpen={!soap}
      >
        <textarea
          disabled={isSigned}
          value={transcription}
          onChange={(e) => setTranscription(e.target.value)}
          rows={8}
          placeholder="Ex: Paciente relata dor no joelho há 3 dias, piora ao caminhar. Nega trauma. Exame: edema leve, sem sinais flogísticos. Conduta: paracetamol 750mg de 8/8h por 5 dias, compressa morna, retorno em 7 dias se não melhorar..."
          className="w-full rounded-lg bg-black/30 border border-white/[0.06] px-3 py-2 text-[13px] font-mono leading-relaxed placeholder:text-foreground/40 focus:outline-none focus:border-accent-cyan/40 disabled:opacity-60"
        />
        <div className="flex items-center justify-between mt-3 gap-2 flex-wrap">
          <div className="text-[11px] text-muted-foreground">
            {transcription.length} caracteres ·{" "}
            {transcription.trim() ? transcription.trim().split(/\s+/).length : 0} palavras
          </div>
          <div className="flex items-center gap-2">
            {!isSigned && (
              <button
                disabled={savingTranscription || !transcription.trim()}
                onClick={handleSaveTranscription}
                className="px-3 py-1.5 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
              >
                {savingTranscription ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                Salvar texto
              </button>
            )}
            {!isSigned && (
              <button
                disabled={generatingSoap || !transcription.trim()}
                onClick={handleGenerateSoap}
                className="px-4 py-1.5 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors disabled:opacity-50 inline-flex items-center gap-1.5 shadow-glow-cyan"
              >
                {generatingSoap ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Gerando…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3 w-3" />
                    {soap ? "Regerar SOAP" : "Gerar SOAP"}
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </Section>

      {/* Seção 2: SOAP editor */}
      {soap && (
        <Section
          title="2 · Prontuário SOAP"
          description="Revise e edite cada seção. O scribe indica confiança por trecho — reescreva sempre que o texto não refletir a consulta real."
          defaultOpen
          badge={
            soap.scribe_confidence?.overall ? (
              <ConfidenceBadge level={soap.scribe_confidence.overall} />
            ) : undefined
          }
        >
          <SoapEditor
            soap={soap}
            disabled={isSigned}
            onChange={setSoap}
            onSave={handleSaveSoap}
            saving={savingSoap}
          />
        </Section>
      )}

      {/* Seção 3: Prescrição */}
      {soap && (
        <Section
          title="3 · Prescrição"
          description="Adicione medicações. O validador cruza Critérios de Beers, alergias e medicações atuais do paciente."
          defaultOpen
          badge={
            prescriptions.length > 0 ? (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-accent-cyan/15 border border-accent-cyan/25 text-accent-cyan">
                {prescriptions.length} item{prescriptions.length > 1 ? "s" : ""}
              </span>
            ) : undefined
          }
        >
          <PrescriptionList items={prescriptions} />
          {!isSigned && (
            <button
              onClick={() => setRxOpen(true)}
              className="mt-3 w-full px-4 py-2.5 rounded-lg bg-white/[0.03] border border-dashed border-white/[0.12] hover:border-accent-cyan/40 text-xs font-medium text-muted-foreground hover:text-foreground inline-flex items-center justify-center gap-2 transition-colors"
            >
              <Pill className="h-3.5 w-3.5" />
              Adicionar medicação
            </button>
          )}
        </Section>
      )}

      {/* Seção 4: Assinatura */}
      {soap && (
        <div className="mt-8">
          {isSigned ? (
            <div className="glass-card rounded-2xl p-5 border border-classification-routine/30 bg-classification-routine/[0.03]">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-full bg-classification-routine/15 flex items-center justify-center flex-shrink-0">
                  <Check className="h-5 w-5 text-classification-routine" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold mb-1">Prontuário assinado</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    Assinatura eletrônica registrada em{" "}
                    {new Date(signedAt!).toLocaleString("pt-BR")}. O Bundle FHIR foi
                    gerado e sincronizado com o TotalCare.
                  </p>
                  {fhirBundleId && (
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL || ""}/api/teleconsulta/${teleconsultaId}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-[11px] text-accent-cyan hover:text-accent-teal font-mono"
                    >
                      <Download className="h-3 w-3" />
                      Bundle {fhirBundleId.slice(0, 12)}…
                    </a>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="glass-card rounded-2xl p-5 border border-accent-cyan/25 bg-gradient-to-br from-accent-cyan/[0.04] to-accent-teal/[0.03]">
              <h3 className="font-semibold mb-2">Pronto para assinar?</h3>
              <p className="text-xs text-muted-foreground mb-4 leading-relaxed">
                Ao assinar eletronicamente você (1) gera o <strong>FHIR Bundle R4</strong>,
                (2) sincroniza o resumo com a central de cuidadores TotalCare,
                (3) encerra o evento de cuidado como <span className="text-foreground">"cuidado iniciado"</span>.
                <br />
                <span className="italic mt-1 block opacity-70">
                  Demo · assinatura mocked. Em produção: Vidaas / ICP-Brasil.
                </span>
              </p>
              <button
                disabled={signing}
                onClick={handleSign}
                className="w-full px-5 py-3 rounded-xl bg-accent-cyan text-slate-900 text-sm font-semibold hover:bg-accent-teal transition-all disabled:opacity-50 inline-flex items-center justify-center gap-2 shadow-glow-cyan active:scale-[0.99]"
              >
                {signing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Assinando e gerando FHIR…
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4" strokeWidth={2.5} />
                    Assinar prontuário
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {rxOpen && tc && (
        <PrescriptionModal
          onClose={() => setRxOpen(false)}
          onSubmit={handleAddPrescription}
          patientAllergies={tc.patient_allergies || []}
          patientMedications={
            (tc.patient_medications || []).map((m) => m.name).filter(Boolean)
          }
        />
      )}

      {celebrationOpen && tc && (
        <SignCelebration
          patientName={tc.patient_full_name}
          doctorName={tc.doctor_name_snapshot || "Dra. Ana Silva"}
          onClose={() => setCelebrationOpen(false)}
          teleconsultaId={teleconsultaId}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Subcomponentes locais
// ═══════════════════════════════════════════════════════════════

function PatientBriefCard({ tc }: { tc: TeleconsultaRecord | null }) {
  if (!tc) return null;
  const conditions = tc.patient_conditions || [];
  const meds = tc.patient_medications || [];
  const allergies = tc.patient_allergies || [];

  return (
    <div className="glass-card rounded-xl p-4 border border-white/[0.06] mb-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold mb-1.5">
            Condições ativas
          </div>
          {conditions.length === 0 ? (
            <div className="text-muted-foreground italic">Nenhuma registrada</div>
          ) : (
            <div className="flex flex-wrap gap-1">
              {conditions.slice(0, 6).map((c, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.06]"
                >
                  {c.description}
                </span>
              ))}
            </div>
          )}
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold mb-1.5">
            Medicações em uso
          </div>
          {meds.length === 0 ? (
            <div className="text-muted-foreground italic">Nenhuma registrada</div>
          ) : (
            <ul className="space-y-0.5">
              {meds.slice(0, 5).map((m, i) => (
                <li key={i} className="text-foreground/90">
                  • {m.name}
                  {m.dose ? ` · ${m.dose}` : ""}
                  {m.schedule ? ` · ${m.schedule}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-accent-cyan/80 font-semibold mb-1.5 flex items-center gap-1">
            Alergias
            {allergies.length > 0 && (
              <AlertTriangle className="h-3 w-3 text-classification-critical" />
            )}
          </div>
          {allergies.length === 0 ? (
            <div className="text-muted-foreground italic">Nenhuma registrada</div>
          ) : (
            <div className="flex flex-wrap gap-1">
              {allergies.map((a, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-full bg-classification-critical/10 border border-classification-critical/25 text-classification-critical text-[11px] font-medium"
                >
                  {a}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  children,
  defaultOpen = true,
  badge,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="glass-card rounded-2xl border border-white/[0.06] mb-5 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start justify-between gap-3 p-5 hover:bg-white/[0.02] transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-sm font-semibold">{title}</h2>
            {badge}
          </div>
          {description && (
            <p className="text-[13px] text-foreground/75 mt-1 leading-relaxed">
              {description}
            </p>
          )}
        </div>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground flex-shrink-0 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </section>
  );
}

function ConfidenceBadge({ level }: { level: string }) {
  const styles =
    level === "high"
      ? "bg-classification-routine/15 border-classification-routine/25 text-classification-routine"
      : level === "low"
      ? "bg-classification-critical/15 border-classification-critical/25 text-classification-critical"
      : "bg-classification-attention/15 border-classification-attention/30 text-classification-attention";
  const label =
    level === "high" ? "alta confiança" : level === "low" ? "revisar" : "média";
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border ${styles}`}>
      scribe: {label}
    </span>
  );
}

function PrescriptionList({ items }: { items: PrescriptionItem[] }) {
  if (items.length === 0) {
    return (
      <div className="text-xs text-muted-foreground italic py-3">
        Nenhuma medicação prescrita ainda.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <PrescriptionCard key={item.id} item={item} />
      ))}
    </div>
  );
}

function PrescriptionCard({ item }: { item: PrescriptionItem }) {
  const v = item.validation;
  const hasIssues = v?.issues && v.issues.length > 0;
  const severity = v?.severity;

  const borderClass =
    severity === "critical" || severity === "high"
      ? "border-classification-critical/40 bg-classification-critical/[0.04]"
      : severity === "moderate"
      ? "border-classification-attention/30 bg-classification-attention/[0.03]"
      : "border-white/[0.08] bg-white/[0.02]";

  return (
    <div className={`rounded-xl p-3.5 border ${borderClass}`}>
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center flex-shrink-0">
          <Pill className="h-4 w-4 text-accent-cyan" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="text-sm font-semibold">{item.medication}</div>
            {v?.validation_status && (
              <StatusBadge status={v.validation_status} />
            )}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {[item.dose, item.schedule, item.duration].filter(Boolean).join(" · ") || (
              <span className="italic">sem posologia detalhada</span>
            )}
            {item.indication && (
              <span className="text-muted-foreground/80">
                {" · "}indicação: {item.indication}
              </span>
            )}
          </div>

          {hasIssues && (
            <div className="mt-2.5 space-y-1.5">
              {v!.issues!.slice(0, 3).map((iss, i) => (
                <div
                  key={i}
                  className="text-[11px] rounded-md bg-black/20 border border-white/[0.05] px-2.5 py-1.5"
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <AlertTriangle
                      className={`h-3 w-3 ${
                        iss.severity === "critical" || iss.severity === "high"
                          ? "text-classification-critical"
                          : "text-classification-attention"
                      }`}
                    />
                    <span className="font-medium uppercase tracking-wider text-[9px]">
                      {iss.type.replace("_", " ")}
                    </span>
                  </div>
                  <div className="text-foreground/90">{iss.description}</div>
                  {iss.recommendation && (
                    <div className="text-muted-foreground italic mt-1">
                      → {iss.recommendation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {v?.overall_recommendation && !hasIssues && (
            <div className="mt-2 text-[11px] text-classification-routine">
              ✓ {v.overall_recommendation}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    approved: {
      label: "aprovada",
      cls: "bg-classification-routine/15 border-classification-routine/25 text-classification-routine",
    },
    approved_with_warnings: {
      label: "com ressalvas",
      cls: "bg-classification-attention/15 border-classification-attention/30 text-classification-attention",
    },
    rejected: {
      label: "rejeitada",
      cls: "bg-classification-critical/15 border-classification-critical/30 text-classification-critical",
    },
  };
  const cfg = map[status] || {
    label: status,
    cls: "bg-white/[0.04] border-white/[0.08] text-muted-foreground",
  };
  return (
    <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}
