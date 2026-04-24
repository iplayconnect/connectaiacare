"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, UserPlus, X } from "lucide-react";

import {
  type CaregiverRole,
  type CaregiverShift,
  createCaregiver,
} from "@/hooks/use-caregivers";

interface Props {
  onSuccess: () => void;
  onCancel: () => void;
}

const ROLES: { value: CaregiverRole; label: string; hint: string }[] = [
  { value: "cuidador", label: "Cuidador", hint: "Cuidador direto" },
  { value: "enfermagem", label: "Enfermagem", hint: "Auxiliar ou enfermeiro" },
  { value: "tecnico", label: "Técnico", hint: "Tec. enfermagem" },
  { value: "coordenador", label: "Coordenador", hint: "Gestão clínica" },
  { value: "medico", label: "Médico", hint: "CRM ativo" },
];

const SHIFTS: { value: CaregiverShift; label: string }[] = [
  { value: "manha", label: "Manhã (6h-14h)" },
  { value: "tarde", label: "Tarde (14h-22h)" },
  { value: "noite", label: "Noite (22h-6h)" },
  { value: "12x36", label: "12×36" },
  { value: "24h", label: "24 horas" },
  { value: "plantao", label: "Plantão SOS" },
  { value: "flexivel", label: "Flexível" },
];

// ═══════════════════════════════════════════════════════════════════
// Formulário de cadastro de cuidador/profissional
// ═══════════════════════════════════════════════════════════════════

export function CaregiverForm({ onSuccess, onCancel }: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [fullName, setFullName] = useState("");
  const [cpf, setCpf] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<CaregiverRole>("cuidador");
  const [shift, setShift] = useState<CaregiverShift>("manha");
  const [email, setEmail] = useState("");
  const [crm, setCrm] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Lock body scroll + Esc
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", handler);
    };
  }, [onCancel]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    // Client-side validation
    if (fullName.trim().split(" ").length < 2) {
      setErrors({ full_name: "Nome completo (nome + sobrenome)" });
      return;
    }

    setSubmitting(true);

    const metadata: Record<string, unknown> = {};
    if (email) metadata.email = email.trim().toLowerCase();
    if (crm) metadata.crm = crm.trim().toUpperCase();
    if (notes) metadata.notes = notes.trim();

    const result = await createCaregiver({
      full_name: fullName.trim(),
      cpf: cpf.replace(/\D/g, "") || undefined,
      phone: phone.replace(/\D/g, "") || undefined,
      role,
      shift,
      metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
    });

    if (result.status === "ok") {
      onSuccess();
    } else {
      setErrors({
        [result.field || "_"]: result.message || "Erro ao salvar",
      });
      setSubmitting(false);
    }
  };

  if (!mounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center pt-16 pb-8 px-4 overflow-y-auto"
      style={{ animation: "fade-in 180ms ease" }}
    >
      <div
        onClick={onCancel}
        className="absolute inset-0 bg-black/60 backdrop-blur-md"
        aria-hidden
      />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-xl glass-card rounded-2xl shadow-2xl overflow-hidden"
        style={{ animation: "slide-in-up 280ms cubic-bezier(0.16,1,0.3,1)" }}
      >
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl accent-gradient flex items-center justify-center">
              <UserPlus className="h-5 w-5 text-slate-900" strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-lg font-bold">Novo profissional</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Cadastre cuidadores, enfermagem, técnicos ou médicos da equipe
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Cancelar"
            className="w-8 h-8 rounded-lg border border-white/10 bg-white/5 text-foreground/80 grid place-items-center hover:bg-white/10 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </header>

        {/* Campos */}
        <div className="px-6 py-5 space-y-4 max-h-[calc(100vh-220px)] overflow-y-auto">
          {/* Nome completo */}
          <Field
            label="Nome completo"
            required
            error={errors.full_name}
          >
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Ex: Júlia Amorim Silva"
              autoComplete="name"
              required
              className={fieldClass(!!errors.full_name)}
            />
          </Field>

          {/* Role selector (grid visual) */}
          <Field label="Função" required>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-1">
              {ROLES.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRole(r.value)}
                  className={`p-2.5 rounded-lg border text-left transition-all ${
                    role === r.value
                      ? "border-accent-cyan/50 bg-accent-cyan/5 text-accent-cyan"
                      : "border-white/10 bg-white/[0.02] text-muted-foreground hover:border-accent-cyan/30"
                  }`}
                >
                  <div className="text-xs font-semibold">{r.label}</div>
                  <div className="text-[10px] text-muted-foreground/80 mt-0.5">
                    {r.hint}
                  </div>
                </button>
              ))}
            </div>
          </Field>

          {/* Turno */}
          <Field label="Turno">
            <select
              value={shift}
              onChange={(e) => setShift(e.target.value as CaregiverShift)}
              className={fieldClass(false)}
            >
              {SHIFTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>

          {/* Grid: CPF + Phone */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="CPF" error={errors.cpf} hint="Apenas números">
              <input
                type="text"
                value={cpf}
                onChange={(e) => setCpf(e.target.value)}
                placeholder="000.000.000-00"
                inputMode="numeric"
                className={`font-mono tabular ${fieldClass(!!errors.cpf)}`}
              />
            </Field>
            <Field label="Celular" error={errors.phone} hint="Com DDD">
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="(11) 98765-4321"
                autoComplete="tel"
                className={`font-mono tabular ${fieldClass(!!errors.phone)}`}
              />
            </Field>
          </div>

          {/* Email */}
          <Field label="Email" hint="Opcional">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="exemplo@clinica.com"
              autoComplete="email"
              className={fieldClass(false)}
            />
          </Field>

          {/* CRM (só pra médico) */}
          {role === "medico" && (
            <Field label="CRM" hint="Opcional · ex: CRM/SP 12345">
              <input
                type="text"
                value={crm}
                onChange={(e) => setCrm(e.target.value)}
                placeholder="CRM/SP 12345"
                className={fieldClass(false)}
              />
            </Field>
          )}

          {/* Notes */}
          <Field label="Observações" hint="Opcional">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Ex: Especialidade em geriatria, experiência com Alzheimer"
              className={`${fieldClass(false)} resize-y`}
            />
          </Field>

          {errors._ && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-classification-critical/10 border border-classification-critical/30 text-classification-critical text-sm">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{errors._}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="px-6 py-4 border-t border-white/10 bg-[hsl(222,30%,10%)]/60 flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm font-semibold border border-white/10 bg-white/5 text-foreground/85 hover:bg-white/10 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-semibold hover:shadow-[0_0_20px_rgba(49,225,255,0.35)] transition-all disabled:opacity-60"
          >
            {submitting ? "Salvando…" : "Cadastrar"}
          </button>
        </footer>
      </form>
    </div>,
    document.body,
  );
}

// ══════════════════════════════════════════════════════════════════
// Field / input styling helpers
// ══════════════════════════════════════════════════════════════════

function Field({
  label,
  required,
  error,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground block mb-1.5">
        {label}
        {required && <span className="text-classification-critical ml-0.5">*</span>}
        {hint && !error && (
          <span className="ml-2 normal-case tracking-normal text-muted-foreground/70 font-normal">
            {hint}
          </span>
        )}
      </label>
      {children}
      {error && (
        <div className="mt-1 text-[11px] text-classification-critical">{error}</div>
      )}
    </div>
  );
}

function fieldClass(hasError: boolean): string {
  return `w-full bg-[hsl(222,30%,10%)] border rounded-lg px-3 py-2 text-sm focus:outline-none transition-colors ${
    hasError
      ? "border-classification-critical/50 focus:border-classification-critical"
      : "border-white/10 focus:border-accent-cyan/50"
  }`;
}
