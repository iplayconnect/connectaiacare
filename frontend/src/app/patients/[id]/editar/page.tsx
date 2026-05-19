"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  ClipboardCheck,
  Heart,
  IdCard,
  Loader2,
  Phone,
  Save,
  ShieldAlert,
  User,
  UserCheck,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ════════════════════════════════════════════════════════════════════
// /patients/[id]/editar
//
// Edição dos campos cadastrais do paciente. Inclui o CPF (campo novo
// migration 054) que destrava integrações externas com parceiros.
//
// Hoje cobre os campos editáveis em produção. Faltando ainda: edição
// de medicações ativas (vai pra /admin/governance/clinical-rules) e plantões
// (vai pra /admin/plantoes).
// ════════════════════════════════════════════════════════════════════

const FORM_OF_ADDRESS_OPTIONS: {
  value: "first_name" | "formal" | "full_first_name" | "nickname";
  label: string;
  example: string;
}[] = [
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

type PatientForm = {
  full_name: string;
  nickname: string;
  cpf: string;
  birth_date: string;
  gender: string;
  care_unit: string;
  room_number: string;
  care_level: string;
  preferred_form_of_address: string;
  is_self_reporting: boolean;
  conditions: string;
  allergies: string;
  responsible_name: string;
  responsible_phone: string;
  responsible_relationship: string;
  tecnosenior_patient_id: string;
};

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
  for (let i = 0; i < 9; i++) sum += parseInt(d[i]) * (10 - i);
  let r = (sum * 10) % 11;
  if (r === 10) r = 0;
  if (r !== parseInt(d[9])) return false;
  sum = 0;
  for (let i = 0; i < 10; i++) sum += parseInt(d[i]) * (11 - i);
  r = (sum * 10) % 11;
  if (r === 10) r = 0;
  return r === parseInt(d[10]);
}

export default function PatientEditPage() {
  const { user } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const patientId = params.id;

  const canEdit = hasRole(
    user, "super_admin", "admin_tenant", "medico", "enfermeiro",
  );

  const [form, setForm] = useState<PatientForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    api
      .getPatient(patientId)
      .then(({ patient }) => {
        // patient pode vir com responsible em formato legado
        // ({phone, name, relationship}) ou novo ({family: [...]}).
        const resp: any = patient.responsible || {};
        const respLegacy =
          typeof resp === "object" && !Array.isArray(resp.family)
            ? resp
            : (resp.family && resp.family[0]) || {};
        setForm({
          full_name: patient.full_name || "",
          nickname: patient.nickname || "",
          cpf: formatCpf((patient as any).cpf || ""),
          birth_date: ((patient as any).birth_date || "").split("T")[0] || "",
          gender: (patient as any).gender || "",
          care_unit: patient.care_unit || "",
          room_number: patient.room_number || "",
          care_level: (patient as any).care_level || "",
          preferred_form_of_address:
            (patient as any).preferred_form_of_address || "formal",
          is_self_reporting: !!(patient as any).is_self_reporting,
          conditions: ((patient as any).conditions || []).join(", "),
          allergies: ((patient as any).allergies || []).join(", "),
          responsible_name: respLegacy.name || "",
          responsible_phone: respLegacy.phone || "",
          responsible_relationship: respLegacy.relationship || "",
          tecnosenior_patient_id:
            String((patient as any).tecnosenior_patient_id || ""),
        });
      })
      .catch((e: any) => setErr(e?.message || "Erro ao carregar paciente"))
      .finally(() => setLoading(false));
  }, [patientId]);

  if (!canEdit) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center max-w-md mx-auto">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Edição de paciente disponível apenas para equipe clínica/admin.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando...
      </div>
    );
  }

  if (err || !form) {
    return (
      <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention max-w-2xl">
        {err || "Paciente não encontrado."}
      </div>
    );
  }

  function update<K extends keyof PatientForm>(field: K, value: PatientForm[K]) {
    setForm((f) => (f ? { ...f, [field]: value } : f));
    setSuccess(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setErr(null);
    setSuccess(false);

    const cpfDigits = form.cpf.replace(/\D/g, "");
    if (cpfDigits && !isValidCpf(cpfDigits)) {
      setErr("CPF inválido. Confira os dígitos.");
      return;
    }

    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        nickname: form.nickname.trim() || null,
        cpf: cpfDigits || null,
        birth_date: form.birth_date || null,
        gender: form.gender || null,
        care_unit: form.care_unit.trim() || null,
        room_number: form.room_number.trim() || null,
        care_level: form.care_level || null,
        preferred_form_of_address: form.preferred_form_of_address,
        is_self_reporting: !!form.is_self_reporting,
        conditions: form.conditions
          .split(",").map((s) => s.trim()).filter(Boolean),
        allergies: form.allergies
          .split(",").map((s) => s.trim()).filter(Boolean),
        responsible: {
          name: form.responsible_name.trim() || null,
          phone: form.responsible_phone.replace(/\D/g, "") || null,
          relationship: form.responsible_relationship.trim() || null,
        },
      };
      if (form.tecnosenior_patient_id) {
        const n = parseInt(form.tecnosenior_patient_id, 10);
        if (Number.isFinite(n)) payload.tecnosenior_patient_id = n;
      }
      await api.patientUpdate(patientId, payload);
      setSuccess(true);
      // small delay to show success then navigate back
      setTimeout(() => router.push(`/patients/${patientId}`), 800);
    } catch (e: any) {
      setErr(e?.message || "Falha ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5 max-w-3xl">
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
              <UserCheck className="h-5 w-5 text-accent-cyan" />
              Editar paciente
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              Atualize cadastro, CPF, condições, alergias e responsável.
            </p>
          </div>
        </div>
        <Link
          href={`/patients/${patientId}/registration`}
          className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-lg border border-accent-cyan/40 bg-accent-cyan/5 text-accent-cyan hover:bg-accent-cyan/10"
          title="Wizard guiado: identificação, condições, medicamentos com cruzamento clínico"
        >
          <ClipboardCheck className="h-3.5 w-3.5" />
          Cadastro completo (wizard)
        </Link>
      </div>

      {/* Identificação */}
      <Section title="Identificação" icon={User}>
        <div className="grid grid-cols-2 gap-3">
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
            hint="Identificador estável pra integrações com parceiros externos"
            icon={IdCard}
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
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </Field>
          <Field
            label="Sofia chama por"
            hint="Forma de tratamento que a Sofia usa em interação direta."
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
        <label className="flex items-center gap-2 mt-3 text-xs cursor-pointer">
          <input
            type="checkbox"
            className="accent-accent-cyan"
            checked={form.is_self_reporting}
            onChange={(e) => update("is_self_reporting", e.target.checked)}
          />
          <span>
            <b>Paciente reporta sobre si mesmo</b> — idoso solo, sem cuidador
            intermediário. Sofia usa tom acolhedor de primeira pessoa.
          </span>
        </label>
      </Section>

      {/* Acomodação */}
      <Section title="Acomodação" icon={Building2}>
        <div className="grid grid-cols-3 gap-3">
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
                <option key={c} value={c}>{c || "—"}</option>
              ))}
            </select>
          </Field>
        </div>
      </Section>

      {/* Clínico */}
      <Section title="Condições e alergias" icon={Heart}>
        <Field
          label="Condições"
          hint="Separadas por vírgula. Ex: HAS, DM2, Demência leve"
        >
          <textarea
            rows={2}
            className="input resize-none"
            value={form.conditions}
            onChange={(e) => update("conditions", e.target.value)}
          />
        </Field>
        <Field
          label="Alergias"
          hint="Separadas por vírgula. Ex: penicilina, AAS, frutos do mar"
        >
          <textarea
            rows={2}
            className="input resize-none"
            value={form.allergies}
            onChange={(e) => update("allergies", e.target.value)}
          />
        </Field>
      </Section>

      {/* Responsável */}
      <Section title="Responsável familiar" icon={Phone}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome">
            <input
              className="input"
              value={form.responsible_name}
              onChange={(e) => update("responsible_name", e.target.value)}
              placeholder="ex: Filha (nome)"
            />
          </Field>
          <Field label="Parentesco">
            <input
              className="input"
              value={form.responsible_relationship}
              onChange={(e) =>
                update("responsible_relationship", e.target.value)
              }
              placeholder="ex: filho(a), cônjuge, neto(a)"
            />
          </Field>
          <Field
            label="Telefone (WhatsApp)"
            hint="Sofia usa pra identificar familiar quando ele liga."
          >
            <input
              className="input"
              value={form.responsible_phone}
              onChange={(e) =>
                update("responsible_phone", e.target.value.replace(/[^\d]/g, ""))
              }
              placeholder="5551999999999"
              maxLength={13}
            />
          </Field>
        </div>
      </Section>

      {/* Integração */}
      <Section title="Integrações externas">
        <Field
          label="Parceiro integrador — Patient ID (numérico)"
          hint="Mapping pra plataforma do parceiro externo. Geralmente preenchido automaticamente após primeiro lookup por CPF/phone."
        >
          <input
            type="number"
            className="input"
            value={form.tecnosenior_patient_id}
            onChange={(e) => update("tecnosenior_patient_id", e.target.value)}
            placeholder="(vazio = lookup automático)"
          />
        </Field>
      </Section>

      {/* Footer */}
      {err && (
        <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention flex items-center gap-2">
          <AlertCircle className="h-3.5 w-3.5" /> {err}
        </div>
      )}
      {success && (
        <div className="rounded-lg border border-classification-routine/20 bg-classification-routine/5 p-3 text-xs text-classification-routine">
          Salvo. Voltando pra ficha…
        </div>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <Link
          href={`/patients/${patientId}`}
          className="text-xs px-3 py-2 hover:bg-white/[0.04] rounded"
        >
          Cancelar
        </Link>
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium disabled:opacity-50"
        >
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="h-3.5 w-3.5" />
          )}
          Salvar alterações
        </button>
      </div>
    </form>
  );
}

// ─── helpers ────────────────────────────────────────

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        {Icon && <Icon className="h-3.5 w-3.5" />}
        <span className="text-[10px] uppercase tracking-wider">{title}</span>
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  hint,
  icon: Icon,
  children,
}: {
  label: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground flex items-center gap-1">
        {Icon && <Icon className="h-3 w-3" />}
        {label}
      </span>
      {children}
      {hint && (
        <span className="text-[10px] text-muted-foreground/60">{hint}</span>
      )}
    </label>
  );
}
