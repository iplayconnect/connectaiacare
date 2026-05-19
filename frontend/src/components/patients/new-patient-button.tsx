"use client";

/**
 * Botão "Novo paciente" + modal de criação rápida.
 *
 * Fluxo:
 *   1. Usuário clica no botão (header da lista de pacientes)
 *   2. Modal pede só nome (CPF e apelido opcionais)
 *   3. POST /api/patients cria o stub
 *   4. Redireciona pro wizard /patients/<id>/registration
 *      onde o resto do cadastro é preenchido (demografia,
 *      condições, medicamentos, alergias, responsável, etc.)
 *
 * Permission: WIZARD_ROLES (super_admin, admin_tenant, medico,
 * enfermeiro, cuidador_pro, familia). Para outros roles, o botão
 * fica oculto.
 */

import { useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { Loader2, Plus, X } from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { patientRegistrationApi } from "@/lib/api-patient-registration";

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

export function NewPatientButton() {
  const { user } = useAuth();
  const router = useRouter();
  const canCreate = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
    "cuidador_pro",
    "familia",
  );

  const [open, setOpen] = useState(false);

  if (!canCreate) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium hover:shadow-[0_0_24px_rgba(49,225,255,0.35)] transition"
      >
        <Plus className="h-3.5 w-3.5" />
        Novo paciente
      </button>
      {open && (
        <NewPatientModal
          onClose={() => setOpen(false)}
          onCreated={(id) => {
            setOpen(false);
            router.push(`/patients/${id}/registration`);
          }}
        />
      )}
    </>
  );
}

function NewPatientModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (patientId: string) => void;
}) {
  const [fullName, setFullName] = useState("");
  const [nickname, setNickname] = useState("");
  const [cpf, setCpf] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);

    const name = fullName.trim();
    if (name.length < 2) {
      setErr("Informe o nome completo (mínimo 2 caracteres).");
      return;
    }
    const cpfDigits = cpf.replace(/\D/g, "");
    if (cpfDigits && !isValidCpf(cpfDigits)) {
      setErr("CPF inválido. Confira os dígitos ou deixe em branco — pode preencher depois no wizard.");
      return;
    }

    setSaving(true);
    try {
      const res = await patientRegistrationApi.createPatient({
        full_name: name,
        nickname: nickname.trim() || undefined,
        cpf: cpfDigits || undefined,
      });
      onCreated(res.patient.id);
    } catch (e: any) {
      setErr(e?.message || "Falha ao criar paciente");
      setSaving(false);
    }
  }

  // Renderiza via portal pra não ser limitado por transforms de parents.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-bg-elevated p-6 space-y-4 shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Novo paciente</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              Cadastro rápido — apenas o nome é obrigatório. O resto vem
              no wizard logo em seguida.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/[0.04] text-muted-foreground"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="block space-y-1">
          <span className="text-sm text-muted-foreground">
            Nome completo *
          </span>
          <input
            autoFocus
            required
            className="input w-full"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="ex: Maria Aparecida Santos"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-sm text-muted-foreground">
            Como é chamado(a)
          </span>
          <input
            className="input w-full"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="ex: Dona Maria, Dona Mariazinha (opcional)"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-sm text-muted-foreground">
            CPF (opcional)
          </span>
          <input
            className="input w-full"
            value={cpf}
            onChange={(e) => setCpf(formatCpf(e.target.value))}
            placeholder="000.000.000-00"
            maxLength={14}
          />
          <span className="text-sm text-muted-foreground block">
            Pode ser preenchido depois no wizard. Necessário pra
            integrações externas (Tecnosenior).
          </span>
        </label>

        {err && (
          <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-2.5 text-sm text-classification-attention">
            {err}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="text-sm px-3 py-2 rounded-lg hover:bg-white/[0.04] disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Criar e abrir cadastro
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
