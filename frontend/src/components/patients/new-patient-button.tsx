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

import { useEffect, useRef, useState } from "react";
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
  // Quando CPF ja existe no tenant, em vez de "erro" mostramos um
  // call-to-action pra abrir o cadastro existente direto.
  const [duplicate, setDuplicate] = useState<{
    id: string;
    full_name: string;
  } | null>(null);
  // Estado da checagem realtime de CPF (enquanto digita)
  const [checkingCpf, setCheckingCpf] = useState(false);
  const checkDebounceRef = useRef<number | null>(null);

  // ── Validacao realtime de CPF (debounced 500ms) ─────────────────
  // Assim que o user termina de digitar 11 digitos validos, consultamos
  // o backend pra ver se ja existe paciente com esse CPF nesse tenant.
  // Se sim, mostramos o card "Abrir cadastro existente" antes mesmo
  // do user clicar em "Criar". UX mais natural que esperar o submit.
  useEffect(() => {
    if (checkDebounceRef.current) {
      window.clearTimeout(checkDebounceRef.current);
    }
    const cpfDigits = cpf.replace(/\D/g, "");
    // So checa quando CPF esta completo E e valido (evita request
    // pra cada digito + nao consulta CPF invalido)
    if (cpfDigits.length !== 11 || !isValidCpf(cpfDigits)) {
      setDuplicate(null);
      setCheckingCpf(false);
      return;
    }

    setCheckingCpf(true);
    checkDebounceRef.current = window.setTimeout(async () => {
      try {
        const res = await patientRegistrationApi.findByCpf(cpfDigits);
        if (res.exists && res.patient) {
          setDuplicate({
            id: res.patient.id,
            full_name: res.patient.full_name,
          });
        } else {
          setDuplicate(null);
        }
      } catch {
        // Erro de rede: silencioso. O submit ainda valida no backend.
        setDuplicate(null);
      } finally {
        setCheckingCpf(false);
      }
    }, 500);

    return () => {
      if (checkDebounceRef.current) {
        window.clearTimeout(checkDebounceRef.current);
      }
    };
  }, [cpf]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setDuplicate(null);

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
      // 409 = CPF ja cadastrado neste tenant. Backend retorna o paciente
      // existente; oferecemos "Abrir cadastro existente" em vez de
      // mensagem de erro hostil.
      if (e?.status === 409 && e?.reason === "cpf_already_exists") {
        const existing = e?.body?.existing_patient;
        if (existing?.id) {
          setDuplicate({ id: existing.id, full_name: existing.full_name });
          setSaving(false);
          return;
        }
        setErr("Esse CPF já está cadastrado neste tenant.");
        setSaving(false);
        return;
      }
      // Outros erros: usar hint amigavel do backend OU fallback generico.
      // Nao expor message completa pq pode conter detail tecnico.
      setErr(e?.body?.hint || e?.reason || "Falha ao criar paciente. Tente de novo.");
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
          <span className="text-sm text-muted-foreground flex items-center gap-2">
            CPF (opcional)
            {checkingCpf && (
              <span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground/70">
                <Loader2 className="h-3 w-3 animate-spin" /> verificando…
              </span>
            )}
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
            integrações externas com parceiros.
          </span>
        </label>

        {duplicate && (
          <div className="rounded-lg border border-accent-cyan/30 bg-accent-cyan/5 p-3 text-sm space-y-2">
            <div className="text-foreground">
              Esse CPF já está cadastrado para{" "}
              <span className="font-semibold">{duplicate.full_name}</span>{" "}
              neste tenant.
            </div>
            <div className="text-muted-foreground text-[13px]">
              Em vez de criar um novo, abra o cadastro existente e continue de
              onde parou.
            </div>
            <button
              type="button"
              onClick={() => {
                const id = duplicate.id;
                setDuplicate(null);
                onCreated(id);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-cyan/15 border border-accent-cyan/40 text-accent-cyan text-sm font-medium hover:bg-accent-cyan/25 transition"
            >
              Abrir cadastro existente
            </button>
          </div>
        )}

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
            // Bloqueia "Criar" se ja detectamos duplicate via lookup
            // realtime — forca o user a clicar "Abrir cadastro existente"
            // (UX mais clara que aceitar o submit e mostrar erro depois).
            disabled={saving || !!duplicate}
            title={duplicate ? "Esse CPF já está cadastrado — abra o cadastro existente" : undefined}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
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
