"use client";

/**
 * Wizard de cadastro completo do paciente — PR 2 do plano patient-registration.
 *
 * Fluxo (5 passos):
 *   1. Identidade do informante  (registered_by_role + LGPD se B2C/familiar)
 *   2. Dados demográficos        (nome, CPF, nascimento, gênero, acomodação)
 *   3. Condições                 (autocomplete CID-10)
 *   4. Medicamentos              (lookup classe terapêutica em tempo real)
 *   5. Cross-validation + revisão (prompts não-bloqueantes + alergias + responsável)
 *
 * Cada save salva incrementalmente no backend (recuperável se fechar aba).
 * Cross-validation roda automaticamente ao entrar no passo 5.
 *
 * Acesso operacional: super_admin, admin_tenant, medico, enfermeiro,
 * cuidador_pro, familia. Verificação clínica é uma ação separada (não
 * faz parte deste wizard — vai pra UI dedicada do enfermeiro/médico).
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  ClipboardCheck,
  HeartPulse,
  Info,
  Loader2,
  Pill,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  Users,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  patientRegistrationApi,
  REGISTERED_BY_ROLE_LABEL,
  ITEM_SOURCE_LABEL,
  SEVERITY_BADGE,
  type ClinicalItem,
  type Cid10SearchResult,
  type CrossValidationPrompt,
  type MedicationLookupResult,
  type PatientRegistrationState,
  type RegisteredByRole,
} from "@/lib/api-patient-registration";

// ─── Types locais ───────────────────────────────────────────────────

type DemographicsForm = {
  full_name: string;
  nickname: string;
  cpf: string;
  birth_date: string;
  gender: string;
  preferred_form_of_address: string;
  is_self_reporting: boolean;
  care_unit: string;
  room_number: string;
  care_level: string;
};

type ResponsibleForm = {
  name: string;
  relationship: string;
  phone: string;
  email: string;
};

const STEPS = [
  { id: 1, key: "informant", label: "Quem está informando" },
  { id: 2, key: "demographics", label: "Identificação" },
  { id: 3, key: "conditions", label: "Condições de saúde" },
  { id: 4, key: "medications", label: "Medicamentos em uso" },
  { id: 5, key: "review", label: "Alergias, responsável e revisão" },
] as const;

const TOTAL_STEPS = STEPS.length;

// ─── Helpers ────────────────────────────────────────────────────────

function formatCpf(digits: string): string {
  const d = (digits || "").replace(/\D/g, "").slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

function isValidCpf(cpf: string): boolean {
  const d = (cpf || "").replace(/\D/g, "");
  if (d.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(d)) return false;
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += parseInt(d[i], 10) * (10 - i);
  let r = (sum * 10) % 11;
  if (r === 10) r = 0;
  if (r !== parseInt(d[9], 10)) return false;
  sum = 0;
  for (let i = 0; i < 10; i++) sum += parseInt(d[i], 10) * (11 - i);
  r = (sum * 10) % 11;
  if (r === 10) r = 0;
  return r === parseInt(d[10], 10);
}

function debounce<T extends (...a: any[]) => void>(fn: T, ms: number) {
  let t: any;
  return (...args: Parameters<T>) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

// ════════════════════════════════════════════════════════════════════
// Página principal
// ════════════════════════════════════════════════════════════════════

export default function PatientRegistrationWizardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const canRegister = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
    "cuidador_pro",
    "familia",
  );

  const [state, setState] = useState<PatientRegistrationState | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingStep, setSavingStep] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [step, setStep] = useState(1);

  // Form state ---------------------------------------------------
  const [registeredByRole, setRegisteredByRole] =
    useState<RegisteredByRole | "">("");
  const [consentLgpd, setConsentLgpd] = useState(false);

  const [demographics, setDemographics] = useState<DemographicsForm>({
    full_name: "",
    nickname: "",
    cpf: "",
    birth_date: "",
    gender: "",
    preferred_form_of_address: "formal",
    is_self_reporting: false,
    care_unit: "",
    room_number: "",
    care_level: "",
  });

  const [conditions, setConditions] = useState<ClinicalItem[]>([]);
  const [medications, setMedications] = useState<ClinicalItem[]>([]);
  const [allergies, setAllergies] = useState<ClinicalItem[]>([]);
  const [responsible, setResponsible] = useState<ResponsibleForm>({
    name: "",
    relationship: "",
    phone: "",
    email: "",
  });

  const [validationPrompts, setValidationPrompts] = useState<
    CrossValidationPrompt[]
  >([]);
  const [validating, setValidating] = useState(false);

  // ── Carregamento inicial ─────────────────────────────────────
  useEffect(() => {
    if (!patientId || !canRegister) return;
    let alive = true;
    setLoading(true);
    patientRegistrationApi
      .getState(patientId)
      .then((data) => {
        if (!alive) return;
        setState(data);
        // Hidrata forms a partir do que já existe no paciente
        const p = data.patient;
        setDemographics((d) => ({
          ...d,
          full_name: p.full_name || "",
        }));
        if (p.conditions?.length) setConditions(p.conditions);
        if (p.medications?.length) setMedications(p.medications);
        if (p.allergies?.length) setAllergies(p.allergies);
        const r: any = p.responsible;
        if (r) {
          if (Array.isArray(r?.family) && r.family[0]) {
            setResponsible({
              name: r.family[0].name || "",
              relationship: r.family[0].relationship || "",
              phone: r.family[0].phone || "",
              email: r.family[0].email || "",
            });
          } else if (typeof r === "object") {
            setResponsible({
              name: r.name || "",
              relationship: r.relationship || "",
              phone: r.phone || "",
              email: r.email || "",
            });
          }
        }
        // Se sessão ativa, posiciona no próximo passo a completar
        if (data.active_session) {
          setRegisteredByRole(data.active_session.registered_by_role);
          if (data.active_session.consent_lgpd_accepted_at) {
            setConsentLgpd(true);
          }
          const next = Math.min(
            (data.active_session.last_completed_step || 0) + 1,
            TOTAL_STEPS,
          );
          setStep(next);
        }
      })
      .catch((e: any) =>
        setErr(e?.message || "Erro ao carregar dados do paciente"),
      )
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [patientId, canRegister]);

  // ── Permissão ───────────────────────────────────────────────
  if (!canRegister) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center max-w-md mx-auto mt-12">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-[15px] text-foreground/80 mt-1">
          Cadastro de paciente disponível para equipe clínica, gestão e
          familiar responsável.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando…
      </div>
    );
  }

  if (err && !state) {
    return (
      <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-sm text-classification-attention max-w-2xl">
        {err}
      </div>
    );
  }

  // ── Ações ───────────────────────────────────────────────────
  async function ensureSession(): Promise<boolean> {
    if (state?.active_session) return true;
    if (!registeredByRole) {
      setErr("Selecione quem está informando.");
      return false;
    }
    const needsConsent =
      registeredByRole === "paciente_b2c" ||
      registeredByRole === "familiar_responsavel";
    if (needsConsent && !consentLgpd) {
      setErr("Aceite obrigatório do termo LGPD para B2C/familiar.");
      return false;
    }
    setSavingStep(true);
    try {
      const res = await patientRegistrationApi.start(patientId, {
        registered_by_role: registeredByRole,
        consent_lgpd_accepted: consentLgpd,
      });
      // Refresh state mínimo
      setState((s) =>
        s
          ? {
              ...s,
              active_session: {
                id: res.session_id,
                registered_by_user_id: null,
                registered_by_role: registeredByRole as RegisteredByRole,
                last_completed_step: 0,
                total_steps: TOTAL_STEPS,
                status: "in_progress",
                started_at: new Date().toISOString(),
                completed_at: null,
                consent_lgpd_accepted_at: consentLgpd
                  ? new Date().toISOString()
                  : null,
              },
            }
          : s,
      );
      setErr(null);
      return true;
    } catch (e: any) {
      setErr(e?.message || "Falha ao iniciar sessão de cadastro");
      return false;
    } finally {
      setSavingStep(false);
    }
  }

  async function saveCurrentStep(): Promise<boolean> {
    setSavingStep(true);
    setErr(null);
    try {
      if (step === 1) {
        const ok = await ensureSession();
        return ok;
      }
      if (step === 2) {
        const cpfDigits = demographics.cpf.replace(/\D/g, "");
        if (cpfDigits && !isValidCpf(cpfDigits)) {
          setErr("CPF inválido. Confira os dígitos.");
          return false;
        }
        await patientRegistrationApi.saveStep(patientId, {
          section: "demographics",
          step_number: 2,
          data: {
            full_name: demographics.full_name.trim(),
            nickname: demographics.nickname.trim() || null,
            cpf: cpfDigits || null,
            birth_date: demographics.birth_date || null,
            gender: demographics.gender || null,
            preferred_form_of_address: demographics.preferred_form_of_address,
            is_self_reporting: demographics.is_self_reporting,
            care_unit: demographics.care_unit.trim() || null,
            room_number: demographics.room_number.trim() || null,
            care_level: demographics.care_level || null,
          },
        });
        return true;
      }
      if (step === 3) {
        await patientRegistrationApi.saveStep(patientId, {
          section: "conditions",
          step_number: 3,
          data: conditions,
        });
        return true;
      }
      if (step === 4) {
        await patientRegistrationApi.saveStep(patientId, {
          section: "medications",
          step_number: 4,
          data: medications,
        });
        return true;
      }
      if (step === 5) {
        // Salva alergias + responsável
        await patientRegistrationApi.saveStep(patientId, {
          section: "allergies",
          step_number: 5,
          data: allergies,
        });
        await patientRegistrationApi.saveStep(patientId, {
          section: "responsibles",
          step_number: 5,
          data: {
            name: responsible.name.trim() || null,
            relationship: responsible.relationship.trim() || null,
            phone: responsible.phone.replace(/\D/g, "") || null,
            email: responsible.email.trim() || null,
          },
        });
        return true;
      }
      return true;
    } catch (e: any) {
      setErr(e?.message || "Falha ao salvar passo");
      return false;
    } finally {
      setSavingStep(false);
    }
  }

  async function handleNext() {
    const ok = await saveCurrentStep();
    if (!ok) return;
    if (step === 4) {
      // Antes de ir pro passo 5, roda cross-validation
      runValidation();
    }
    setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  }

  async function handleFinish() {
    const ok = await saveCurrentStep();
    if (!ok) return;
    setSavingStep(true);
    try {
      await patientRegistrationApi.complete(patientId);
      router.push(`/patients/${patientId}`);
    } catch (e: any) {
      setErr(e?.message || "Falha ao finalizar");
      setSavingStep(false);
    }
  }

  async function runValidation() {
    if (!conditions.length || !medications.length) {
      setValidationPrompts([]);
      return;
    }
    setValidating(true);
    try {
      const res = await patientRegistrationApi.validate(
        conditions,
        medications,
      );
      setValidationPrompts(res.prompts);
    } catch {
      // best-effort — não bloqueia conclusão
      setValidationPrompts([]);
    } finally {
      setValidating(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────
  const stepMeta = STEPS[step - 1];

  return (
    <div className="space-y-5 max-w-4xl animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link
            href={`/patients/${patientId}`}
            className="p-1.5 rounded hover:bg-white/[0.04] text-muted-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <ClipboardCheck className="h-5 w-5 text-accent-cyan" />
              Cadastro completo do paciente
            </h1>
            <p className="text-[15px] text-foreground/80 mt-0.5">
              {state?.patient.full_name || "Novo paciente"} ·
              {" "}
              {state?.patient.completeness?.completion_percentage ?? 0}% completo
            </p>
          </div>
        </div>
        {state?.active_session && (
          <span className="text-sm px-2 py-1 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan">
            Sessão ativa · {REGISTERED_BY_ROLE_LABEL[state.active_session.registered_by_role]}
          </span>
        )}
      </div>

      {/* Stepper */}
      <Stepper currentStep={step} onJump={setStep} />

      {/* Conteúdo do passo */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
        <div className="flex items-center gap-2 text-[15px] text-foreground/80">
          <span className="font-semibold text-foreground">Passo {step} de {TOTAL_STEPS}</span>
          <ChevronRight className="h-3 w-3" />
          <span>{stepMeta.label}</span>
        </div>

        {step === 1 && (
          <Step1Informant
            registeredByRole={registeredByRole}
            onChangeRole={setRegisteredByRole}
            consentLgpd={consentLgpd}
            onChangeConsent={setConsentLgpd}
            sessionActive={!!state?.active_session}
          />
        )}
        {step === 2 && (
          <Step2Demographics
            form={demographics}
            onChange={setDemographics}
          />
        )}
        {step === 3 && (
          <Step3Conditions
            items={conditions}
            onChange={setConditions}
          />
        )}
        {step === 4 && (
          <Step4Medications
            items={medications}
            onChange={setMedications}
          />
        )}
        {step === 5 && (
          <Step5Review
            allergies={allergies}
            onChangeAllergies={setAllergies}
            responsible={responsible}
            onChangeResponsible={setResponsible}
            conditions={conditions}
            medications={medications}
            prompts={validationPrompts}
            validating={validating}
            onRevalidate={runValidation}
          />
        )}
      </div>

      {err && (
        <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-sm text-classification-attention flex items-center gap-2">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" /> {err}
        </div>
      )}

      {/* Footer / navegação */}
      <div className="flex items-center justify-between gap-2 pt-1">
        <button
          type="button"
          onClick={() => setStep((s) => Math.max(s - 1, 1))}
          disabled={step === 1 || savingStep}
          className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-white/[0.06] hover:bg-white/[0.04] disabled:opacity-40"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Voltar
        </button>

        {step < TOTAL_STEPS ? (
          <button
            type="button"
            onClick={handleNext}
            disabled={savingStep}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-base font-medium disabled:opacity-50"
          >
            {savingStep ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <>
                Continuar <ArrowRight className="h-3.5 w-3.5" />
              </>
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={handleFinish}
            disabled={savingStep}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-base font-medium disabled:opacity-50"
          >
            {savingStep ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <>
                <Check className="h-3.5 w-3.5" /> Finalizar cadastro
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Stepper
// ════════════════════════════════════════════════════════════════════

function Stepper({
  currentStep,
  onJump,
}: {
  currentStep: number;
  onJump: (n: number) => void;
}) {
  return (
    <ol className="flex items-center gap-2 overflow-x-auto pb-1">
      {STEPS.map((s) => {
        const done = s.id < currentStep;
        const active = s.id === currentStep;
        return (
          <li key={s.id} className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={() => onJump(s.id)}
              className={[
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-sm uppercase tracking-wider transition",
                active
                  ? "bg-accent-cyan/15 border border-accent-cyan/40 text-accent-cyan"
                  : done
                  ? "bg-classification-routine/15 border border-classification-routine/30 text-classification-routine"
                  : "border border-white/[0.06] text-muted-foreground hover:bg-white/[0.04]",
              ].join(" ")}
            >
              <span
                className={[
                  "h-4 w-4 rounded-full flex items-center justify-center text-[12px] font-semibold",
                  active
                    ? "bg-accent-cyan text-slate-900"
                    : done
                    ? "bg-classification-routine text-slate-900"
                    : "bg-white/[0.06] text-muted-foreground",
                ].join(" ")}
              >
                {done ? <Check className="h-2.5 w-2.5" /> : s.id}
              </span>
              {s.label}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ════════════════════════════════════════════════════════════════════
// Passo 1 — Quem está informando
// ════════════════════════════════════════════════════════════════════

function Step1Informant({
  registeredByRole,
  onChangeRole,
  consentLgpd,
  onChangeConsent,
  sessionActive,
}: {
  registeredByRole: RegisteredByRole | "";
  onChangeRole: (r: RegisteredByRole | "") => void;
  consentLgpd: boolean;
  onChangeConsent: (v: boolean) => void;
  sessionActive: boolean;
}) {
  const needsConsent =
    registeredByRole === "paciente_b2c" ||
    registeredByRole === "familiar_responsavel";

  return (
    <div className="space-y-4">
      <p className="text-[15px] text-foreground/80">
        Identifique <b>quem está preenchendo</b> este cadastro. Cada item
        salvo carrega essa origem (provenance), o que permite ao clínico
        priorizar o que ainda precisa de validação.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {(Object.keys(REGISTERED_BY_ROLE_LABEL) as RegisteredByRole[]).map(
          (role) => (
            <label
              key={role}
              className={[
                "flex items-start gap-2 p-3 rounded-lg border cursor-pointer transition",
                registeredByRole === role
                  ? "border-accent-cyan/50 bg-accent-cyan/5"
                  : "border-white/[0.06] hover:bg-white/[0.04]",
                sessionActive ? "opacity-60 cursor-not-allowed" : "",
              ].join(" ")}
            >
              <input
                type="radio"
                name="registered_by_role"
                disabled={sessionActive}
                checked={registeredByRole === role}
                onChange={() => onChangeRole(role)}
                className="mt-0.5 accent-accent-cyan"
              />
              <div className="flex-1">
                <div className="text-base font-medium">
                  {REGISTERED_BY_ROLE_LABEL[role]}
                </div>
                <div className="text-sm text-muted-foreground mt-0.5">
                  {informantHint(role)}
                </div>
              </div>
            </label>
          ),
        )}
      </div>

      {needsConsent && !sessionActive && (
        <label className="flex items-start gap-2 p-3 rounded-lg border border-classification-attention/30 bg-classification-attention/5 cursor-pointer">
          <input
            type="checkbox"
            checked={consentLgpd}
            onChange={(e) => onChangeConsent(e.target.checked)}
            className="mt-0.5 accent-accent-cyan"
          />
          <div className="text-sm leading-relaxed">
            <b>Termo LGPD</b> — Confirmo que o cadastro é feito com
            conhecimento do paciente e/ou família, e autorizo o uso dos
            dados clínicos para acompanhamento de saúde no escopo da
            ConnectaIACare. Origem do consentimento será registrada com
            data, hora e IP.
          </div>
        </label>
      )}

      {sessionActive && (
        <div className="text-sm text-muted-foreground bg-white/[0.02] border border-white/[0.06] rounded-lg p-2 flex items-center gap-1.5">
          <Info className="h-3 w-3" /> Sessão já iniciada — origem e termo
          LGPD ficam congelados nesta sessão.
        </div>
      )}
    </div>
  );
}

function informantHint(role: RegisteredByRole): string {
  switch (role) {
    case "paciente_b2c":
      return "Idoso solo, auto-cuidado, fluxo B2C — Sofia interage em primeira pessoa.";
    case "familiar_responsavel":
      return "Filho(a), cônjuge ou responsável que cuida do idoso.";
    case "procurador":
      return "Procuração legal — fluxo formal com validação cartorial (futuro).";
    case "gestor_unidade":
      return "Coordenador(a) de ILPI / Senior Living — perfil operacional.";
    case "enfermeiro":
      return "Enfermeiro(a) preenchendo cadastro durante admissão.";
    case "medico":
      return "Médico(a) — itens já entram com origem clinician_validated.";
  }
}

// ════════════════════════════════════════════════════════════════════
// Passo 2 — Demografia
// ════════════════════════════════════════════════════════════════════

const FORM_OF_ADDRESS_OPTIONS = [
  { value: "first_name", label: "Primeiro nome", example: "Maria" },
  { value: "formal", label: "Sr./Sra. + nome", example: "Dona Maria" },
  { value: "full_first_name", label: "Nome composto", example: "Dona Maria Helena" },
  { value: "nickname", label: "Apelido", example: "Mariazinha" },
];

const CARE_LEVEL_OPTIONS = ["", "I", "II", "III", "IV"];
const GENDER_OPTIONS = [
  { value: "", label: "—" },
  { value: "M", label: "Masculino" },
  { value: "F", label: "Feminino" },
  { value: "O", label: "Outro" },
];

function Step2Demographics({
  form,
  onChange,
}: {
  form: DemographicsForm;
  onChange: (f: DemographicsForm) => void;
}) {
  function update<K extends keyof DemographicsForm>(
    field: K,
    value: DemographicsForm[K],
  ) {
    onChange({ ...form, [field]: value });
  }

  return (
    <div className="space-y-4">
      <p className="text-[15px] text-foreground/80">
        Identificação básica. <b>Nome completo</b> é obrigatório;{" "}
        <b>CPF</b> destrava integrações externas (Tecnosenior, etc.).
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Nome completo *">
          <input
            required
            className="input"
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
          />
        </Field>
        <Field label="Como é chamado(a)">
          <input
            className="input"
            value={form.nickname}
            onChange={(e) => update("nickname", e.target.value)}
            placeholder="ex: Dona Maria, Sr. José"
          />
        </Field>
        <Field
          label="CPF"
          hint="Identificador estável pra integrações externas"
        >
          <input
            className="input"
            value={form.cpf}
            onChange={(e) => update("cpf", formatCpf(e.target.value))}
            placeholder="000.000.000-00"
            maxLength={14}
          />
        </Field>
        <Field label="Data de nascimento">
          <input
            type="date"
            className="input"
            value={form.birth_date}
            onChange={(e) => update("birth_date", e.target.value)}
          />
        </Field>
        <Field label="Gênero">
          <select
            className="input"
            value={form.gender}
            onChange={(e) => update("gender", e.target.value)}
          >
            {GENDER_OPTIONS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Sofia chama por"
          hint="Tratamento usado na interação direta"
        >
          <select
            className="input"
            value={form.preferred_form_of_address}
            onChange={(e) =>
              update("preferred_form_of_address", e.target.value)
            }
          >
            {FORM_OF_ADDRESS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label} (ex: {o.example})
              </option>
            ))}
          </select>
        </Field>
      </div>

      <label className="flex items-start gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5 accent-accent-cyan"
          checked={form.is_self_reporting}
          onChange={(e) => update("is_self_reporting", e.target.checked)}
        />
        <span>
          <b>Paciente reporta sobre si mesmo</b> — idoso solo, sem cuidador
          intermediário. Sofia usa tom acolhedor de primeira pessoa.
        </span>
      </label>

      <div className="grid grid-cols-3 gap-3 pt-2 border-t border-white/[0.06]">
        <Field label="Unidade de cuidado">
          <input
            className="input"
            value={form.care_unit}
            onChange={(e) => update("care_unit", e.target.value)}
            placeholder="ex: Ala 2, Casa 1"
          />
        </Field>
        <Field label="Quarto">
          <input
            className="input"
            value={form.room_number}
            onChange={(e) => update("room_number", e.target.value)}
          />
        </Field>
        <Field label="Nível de cuidado">
          <select
            className="input"
            value={form.care_level}
            onChange={(e) => update("care_level", e.target.value)}
          >
            {CARE_LEVEL_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c || "—"}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Passo 3 — Condições com autocomplete CID-10
// ════════════════════════════════════════════════════════════════════

function Step3Conditions({
  items,
  onChange,
}: {
  items: ClinicalItem[];
  onChange: (it: ClinicalItem[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Cid10SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const search = useMemo(
    () =>
      debounce(async (q: string) => {
        if (q.trim().length < 2) {
          setResults([]);
          return;
        }
        setSearching(true);
        try {
          const res = await patientRegistrationApi.searchCid10(q, 12);
          setResults(res.items);
        } catch {
          setResults([]);
        } finally {
          setSearching(false);
        }
      }, 250),
    [],
  );

  function addCid(c: Cid10SearchResult) {
    if (items.some((i) => i.cid10_code === c.code)) return;
    onChange([
      ...items,
      {
        name: c.description_pt,
        cid10_code: c.code,
      },
    ]);
    setQuery("");
    setResults([]);
  }

  function addFreeText() {
    const v = query.trim();
    if (!v) return;
    onChange([...items, { name: v }]);
    setQuery("");
    setResults([]);
  }

  function removeAt(idx: number) {
    onChange(items.filter((_, i) => i !== idx));
  }

  function updateField(idx: number, patch: Partial<ClinicalItem>) {
    onChange(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  return (
    <div className="space-y-4">
      <p className="text-[15px] text-foreground/80">
        <b>Condições crônicas e diagnósticos.</b> Use a busca pra pegar o
        Código Internacional de Doenças (CID-10) e descrição padronizada;
        se não encontrar, pode digitar como texto livre.
      </p>

      <div className="relative">
        <input
          className="input w-full"
          placeholder="Buscar CID-10 — ex: pressão, diabetes, alzheimer…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            search(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (results.length > 0) addCid(results[0]);
              else addFreeText();
            }
          }}
        />
        {searching && (
          <Loader2 className="absolute right-2 top-2.5 h-3.5 w-3.5 animate-spin text-muted-foreground" />
        )}
        {results.length > 0 && (
          <div className="absolute z-10 mt-1 w-full max-h-64 overflow-auto rounded-lg border border-white/[0.06] bg-bg-elevated shadow-xl">
            {results.map((r) => (
              <button
                key={r.code}
                type="button"
                onClick={() => addCid(r)}
                className="w-full text-left px-3 py-2 hover:bg-white/[0.04] border-b border-white/[0.04] last:border-b-0"
              >
                <div className="text-sm">
                  <span className="font-mono text-accent-cyan mr-2">
                    {r.code}
                  </span>
                  {r.description_pt}
                </div>
                {r.description_layman && (
                  <div className="text-sm text-muted-foreground mt-0.5">
                    {r.description_layman}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <ItemList
        items={items}
        emptyMessage="Nenhuma condição cadastrada ainda."
        renderItem={(it, idx) => (
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 space-y-1">
              <div className="text-sm flex items-center gap-2">
                {it.cid10_code && (
                  <span className="font-mono text-sm text-accent-cyan bg-accent-cyan/10 px-1.5 py-0.5 rounded">
                    {it.cid10_code}
                  </span>
                )}
                <span className="font-medium">{it.name}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                <select
                  className="input text-sm"
                  value={it.severity || ""}
                  onChange={(e) =>
                    updateField(idx, { severity: e.target.value as any })
                  }
                >
                  <option value="">Severidade —</option>
                  <option value="leve">Leve</option>
                  <option value="moderate">Moderada</option>
                  <option value="severe">Severa</option>
                </select>
                <select
                  className="input text-sm"
                  value={it.controlled === undefined ? "" : it.controlled ? "sim" : "nao"}
                  onChange={(e) =>
                    updateField(idx, {
                      controlled:
                        e.target.value === ""
                          ? undefined
                          : e.target.value === "sim",
                    })
                  }
                >
                  <option value="">Controle —</option>
                  <option value="sim">Controlada</option>
                  <option value="nao">Descontrolada</option>
                </select>
                <input
                  className="input text-sm"
                  placeholder="Notas"
                  value={it.notes || ""}
                  onChange={(e) => updateField(idx, { notes: e.target.value })}
                />
              </div>
              <SourceBadge item={it} />
            </div>
            <button
              type="button"
              onClick={() => removeAt(idx)}
              className="p-1.5 rounded hover:bg-classification-attention/10 text-classification-attention"
              title="Remover"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        )}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Passo 4 — Medicamentos com lookup de classe
// ════════════════════════════════════════════════════════════════════

function Step4Medications({
  items,
  onChange,
}: {
  items: ClinicalItem[];
  onChange: (it: ClinicalItem[]) => void;
}) {
  const [name, setName] = useState("");
  const [classMatch, setClassMatch] = useState<MedicationLookupResult | null>(
    null,
  );
  const [looking, setLooking] = useState(false);

  const lookup = useMemo(
    () =>
      debounce(async (q: string) => {
        if (q.trim().length < 3) {
          setClassMatch(null);
          return;
        }
        setLooking(true);
        try {
          const res = await patientRegistrationApi.lookupMedication(q);
          setClassMatch(res.match);
        } catch {
          setClassMatch(null);
        } finally {
          setLooking(false);
        }
      }, 300),
    [],
  );

  function addMedication() {
    const v = name.trim();
    if (!v) return;
    const item: ClinicalItem = { name: v };
    if (classMatch) {
      item.therapeutic_class = classMatch.therapeutic_classes[0];
    }
    onChange([...items, item]);
    setName("");
    setClassMatch(null);
  }

  function removeAt(idx: number) {
    onChange(items.filter((_, i) => i !== idx));
  }

  function updateField(idx: number, patch: Partial<ClinicalItem>) {
    onChange(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  return (
    <div className="space-y-4">
      <p className="text-[15px] text-foreground/80">
        <b>Medicamentos em uso.</b> A plataforma identifica a classe
        terapêutica automaticamente quando reconhece o princípio ativo —
        isso alimenta o cruzamento condição × medicamento na próxima etapa.
      </p>

      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <input
            className="input sm:col-span-2"
            placeholder="Nome ou princípio ativo — ex: losartana, metformina, donepezila"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              lookup(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addMedication();
              }
            }}
          />
          <button
            type="button"
            onClick={addMedication}
            disabled={!name.trim()}
            className="text-sm px-3 py-2 rounded-lg accent-gradient text-slate-900 font-medium disabled:opacity-40"
          >
            Adicionar
          </button>
        </div>
        {(looking || classMatch) && (
          <div className="text-sm text-muted-foreground">
            {looking ? (
              <span className="flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" /> classificando…
              </span>
            ) : classMatch ? (
              <span className="flex items-start gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-accent-cyan flex-shrink-0 mt-0.5" />
                <span>
                  Reconhecido como{" "}
                  <b className="text-foreground">
                    {classMatch.active_ingredient}
                  </b>{" "}
                  · classe{" "}
                  <b className="text-accent-cyan">
                    {classMatch.therapeutic_classes.join(" / ")}
                  </b>
                  {classMatch.brand_names.length > 0 && (
                    <span className="text-foreground/70">
                      {" "}
                      (referências comerciais: {classMatch.brand_names.slice(0, 3).join(", ")})
                    </span>
                  )}
                </span>
              </span>
            ) : null}
          </div>
        )}
      </div>

      <ItemList
        items={items}
        emptyMessage="Nenhum medicamento cadastrado ainda."
        renderItem={(it, idx) => (
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 space-y-1">
              <div className="text-base font-medium flex items-center gap-2">
                <Pill className="h-3 w-3 text-accent-cyan" />
                {it.name}
                {it.therapeutic_class && (
                  <span className="text-sm px-1.5 py-0.5 rounded bg-accent-cyan/10 text-accent-cyan">
                    {it.therapeutic_class}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                <input
                  className="input text-sm"
                  placeholder="Dose — ex: 50 mg"
                  value={it.dose || ""}
                  onChange={(e) => updateField(idx, { dose: e.target.value })}
                />
                <input
                  className="input text-sm"
                  placeholder="Posologia — ex: 1x/dia manhã"
                  value={it.schedule || ""}
                  onChange={(e) => updateField(idx, { schedule: e.target.value })}
                />
                <input
                  className="input text-sm"
                  placeholder="Notas"
                  value={it.notes || ""}
                  onChange={(e) => updateField(idx, { notes: e.target.value })}
                />
              </div>
              <SourceBadge item={it} />
            </div>
            <button
              type="button"
              onClick={() => removeAt(idx)}
              className="p-1.5 rounded hover:bg-classification-attention/10 text-classification-attention"
              title="Remover"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        )}
      />
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Passo 5 — Revisão (alergias + responsável + cross-validation)
// ════════════════════════════════════════════════════════════════════

function Step5Review({
  allergies,
  onChangeAllergies,
  responsible,
  onChangeResponsible,
  conditions,
  medications,
  prompts,
  validating,
  onRevalidate,
}: {
  allergies: ClinicalItem[];
  onChangeAllergies: (a: ClinicalItem[]) => void;
  responsible: ResponsibleForm;
  onChangeResponsible: (r: ResponsibleForm) => void;
  conditions: ClinicalItem[];
  medications: ClinicalItem[];
  prompts: CrossValidationPrompt[];
  validating: boolean;
  onRevalidate: () => void;
}) {
  const [allergyName, setAllergyName] = useState("");

  function addAllergy() {
    const v = allergyName.trim();
    if (!v) return;
    onChangeAllergies([...allergies, { name: v }]);
    setAllergyName("");
  }

  function removeAllergy(idx: number) {
    onChangeAllergies(allergies.filter((_, i) => i !== idx));
  }

  // Auto-revalidate ao montar
  const onMountRef = useRef(false);
  useEffect(() => {
    if (onMountRef.current) return;
    onMountRef.current = true;
    onRevalidate();
  }, [onRevalidate]);

  return (
    <div className="space-y-5">
      {/* Alergias */}
      <section className="space-y-2">
        <div className="flex items-center gap-2 text-muted-foreground">
          <HeartPulse className="h-3.5 w-3.5" />
          <span className="text-sm uppercase tracking-wider">Alergias</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <input
            className="input col-span-2"
            placeholder="Ex: penicilina, AAS, frutos do mar"
            value={allergyName}
            onChange={(e) => setAllergyName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addAllergy();
              }
            }}
          />
          <button
            type="button"
            onClick={addAllergy}
            className="text-sm px-3 py-2 rounded-lg border border-white/[0.06] hover:bg-white/[0.04] disabled:opacity-40"
            disabled={!allergyName.trim()}
          >
            Adicionar
          </button>
        </div>
        {allergies.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {allergies.map((a, idx) => (
              <span
                key={`${a.name}-${idx}`}
                className="text-sm px-2 py-1 rounded-full bg-classification-attention/10 border border-classification-attention/30 text-classification-attention flex items-center gap-1"
              >
                {a.name}
                <button
                  type="button"
                  onClick={() => removeAllergy(idx)}
                  className="hover:text-foreground"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Responsável */}
      <section className="space-y-2">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Users className="h-3.5 w-3.5" />
          <span className="text-sm uppercase tracking-wider">
            Responsável familiar
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome">
            <input
              className="input"
              value={responsible.name}
              onChange={(e) =>
                onChangeResponsible({ ...responsible, name: e.target.value })
              }
              placeholder="ex: filha (nome)"
            />
          </Field>
          <Field label="Parentesco">
            <input
              className="input"
              value={responsible.relationship}
              onChange={(e) =>
                onChangeResponsible({
                  ...responsible,
                  relationship: e.target.value,
                })
              }
              placeholder="ex: filho(a), cônjuge, neto(a)"
            />
          </Field>
          <Field
            label="Telefone (WhatsApp)"
            hint="Sofia usa pra identificar familiar quando ele liga"
          >
            <input
              className="input"
              value={responsible.phone}
              onChange={(e) =>
                onChangeResponsible({
                  ...responsible,
                  phone: e.target.value.replace(/[^\d]/g, ""),
                })
              }
              placeholder="5551999999999"
              maxLength={13}
            />
          </Field>
          <Field label="E-mail">
            <input
              className="input"
              type="email"
              value={responsible.email}
              onChange={(e) =>
                onChangeResponsible({
                  ...responsible,
                  email: e.target.value,
                })
              }
              placeholder="opcional"
            />
          </Field>
        </div>
      </section>

      {/* Cross-validation */}
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span className="text-sm uppercase tracking-wider">
              Cruzamento clínico (Henrique + Coordenadora PUC)
            </span>
          </div>
          <button
            type="button"
            onClick={onRevalidate}
            disabled={validating}
            className="text-sm px-2 py-1 rounded border border-white/[0.06] hover:bg-white/[0.04] disabled:opacity-40 flex items-center gap-1"
          >
            {validating && <Loader2 className="h-3 w-3 animate-spin" />}
            Revalidar
          </button>
        </div>

        {validating && prompts.length === 0 ? (
          <div className="text-[15px] text-foreground/80">
            Cruzando condições × medicamentos…
          </div>
        ) : prompts.length === 0 ? (
          <div className="rounded-lg border border-classification-routine/20 bg-classification-routine/5 p-3 text-sm text-classification-routine flex items-center gap-2">
            <Check className="h-3.5 w-3.5" />
            Nenhuma inconsistência detectada nas regras de cruzamento ativas.
          </div>
        ) : (
          <div className="space-y-2">
            {prompts.map((p, idx) => {
              const badge = SEVERITY_BADGE[p.prompt_severity] || SEVERITY_BADGE.medium;
              return (
                <div
                  key={`${p.condition_label}-${idx}`}
                  className={`rounded-lg border p-3 text-sm space-y-1.5 ${badge.className}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                      <div>
                        <div className="font-medium">{p.condition_label}</div>
                        <div className="text-sm mt-1 leading-relaxed text-foreground/90">
                          {p.prompt_message}
                        </div>
                      </div>
                    </div>
                    <span className="text-[12px] uppercase font-semibold tracking-wider">
                      {badge.label}
                    </span>
                  </div>
                  {p.expected_therapeutic_classes.length > 0 && (
                    <div className="text-sm text-foreground/70">
                      Esperado: {p.expected_therapeutic_classes.join(", ")} ·
                      Encontrado: {p.found_classes.length > 0 ? p.found_classes.join(", ") : "—"}
                    </div>
                  )}
                  {p.clinical_rationale && (
                    <div className="text-sm text-foreground/60 italic">
                      {p.clinical_rationale}
                    </div>
                  )}
                </div>
              );
            })}
            <p className="text-sm text-muted-foreground italic">
              Estes alertas são <b>orientativos</b>, não bloqueiam a
              finalização. Validação clínica final fica com o(a)
              enfermeiro(a)/médico(a).
            </p>
          </div>
        )}
      </section>

      {/* Resumo do que vai ser salvo */}
      <section className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-sm text-muted-foreground">
        <div className="flex items-center gap-1.5 mb-1.5">
          <ClipboardCheck className="h-3 w-3" />
          <b className="text-foreground">Resumo do cadastro</b>
        </div>
        <ul className="space-y-0.5">
          <li>
            <b className="text-foreground">{conditions.length}</b> condição(ões){" "}
            ·{" "}
            <b className="text-foreground">{medications.length}</b>{" "}
            medicamento(s) · <b className="text-foreground">{allergies.length}</b>{" "}
            alergia(s)
          </li>
          {responsible.name && (
            <li>
              Responsável: <b className="text-foreground">{responsible.name}</b>
              {responsible.relationship && ` (${responsible.relationship})`}
            </li>
          )}
        </ul>
      </section>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════
// Helpers de UI compartilhados
// ════════════════════════════════════════════════════════════════════

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm text-muted-foreground">{label}</span>
      {children}
      {hint && (
        <span className="text-sm text-foreground/70 block">
          {hint}
        </span>
      )}
    </label>
  );
}

function ItemList({
  items,
  emptyMessage,
  renderItem,
}: {
  items: ClinicalItem[];
  emptyMessage: string;
  renderItem: (it: ClinicalItem, idx: number) => React.ReactNode;
}) {
  if (items.length === 0) {
    return (
      <div className="text-sm text-muted-foreground italic px-3 py-4 text-center border border-dashed border-white/[0.06] rounded-lg">
        {emptyMessage}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {items.map((it, idx) => (
        <div
          key={`${it.name}-${idx}`}
          className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
        >
          {renderItem(it, idx)}
        </div>
      ))}
    </div>
  );
}

function SourceBadge({ item }: { item: ClinicalItem }) {
  const verified = !!item.verified_by_clinician_at;
  const sourceLabel = item.source ? ITEM_SOURCE_LABEL[item.source] || item.source : null;
  if (!sourceLabel && !verified) return null;
  return (
    <div className="flex items-center gap-1.5 mt-1">
      {sourceLabel && (
        <span className="text-[12px] px-1.5 py-0.5 rounded bg-white/[0.04] text-muted-foreground">
          {sourceLabel}
        </span>
      )}
      {verified && (
        <span className="text-[12px] px-1.5 py-0.5 rounded bg-classification-routine/10 text-classification-routine flex items-center gap-1">
          <UserCheck className="h-2.5 w-2.5" /> Validado por clínico
        </span>
      )}
    </div>
  );
}
