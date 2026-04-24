"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, ShieldCheck, Sparkles, Check } from "lucide-react";

import {
  extractUtmFromCurrentUrl,
  startOnboardingFromWeb,
  type WebOnboardingPayload,
} from "@/hooks/use-onboarding-web";

// ═══════════════════════════════════════════════════════════════════
// /cadastro — formulário web de captura
//
// Fluxo:
//   /planos → click "Assinar" → /cadastro?plan=X
//   → 4 campos (nome + email + celular + plano já vem da URL)
//   → POST /api/onboarding/start-from-web
//   → redirect pra wa.me com mensagem pré-populada
//   → Sofia pega no estado collect_payer_cpf
// ═══════════════════════════════════════════════════════════════════

const PLAN_LABELS: Record<string, { label: string; price_cents: number }> = {
  essencial: { label: "Essencial", price_cents: 4990 },
  familia: { label: "Família", price_cents: 8990 },
  premium: { label: "Premium", price_cents: 14990 },
  premium_device: { label: "Premium + Dispositivo", price_cents: 19990 },
};

export default function CadastroPage() {
  return (
    <div className="max-w-2xl mx-auto py-8 animate-fade-up">
      <Suspense fallback={<FormSkeleton />}>
        <CadastroForm />
      </Suspense>
    </div>
  );
}

function CadastroForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const planFromUrl = searchParams.get("plan") || "familia";
  const validPlan = PLAN_LABELS[planFromUrl] ? planFromUrl : "familia";

  const [planSku, setPlanSku] = useState(validPlan);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const planInfo = PLAN_LABELS[planSku];

  // UTMs capturados client-side
  const [utms, setUtms] = useState<Partial<WebOnboardingPayload>>({});
  useEffect(() => {
    setUtms(extractUtmFromCurrentUrl());
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    // Validação client-side mínima
    if (fullName.trim().split(" ").length < 2) {
      setErrors({ full_name: "Preciso de nome completo (com sobrenome)" });
      return;
    }
    if (!email.includes("@")) {
      setErrors({ email: "Email em formato inválido" });
      return;
    }
    const phoneDigits = phone.replace(/\D/g, "");
    if (phoneDigits.length < 10 || phoneDigits.length > 13) {
      setErrors({ phone: "Celular com DDD completo (ex: 11 98765-4321)" });
      return;
    }

    setIsSubmitting(true);

    const result = await startOnboardingFromWeb({
      full_name: fullName.trim(),
      email: email.trim().toLowerCase(),
      phone: phoneDigits,
      plan_sku: planSku as WebOnboardingPayload["plan_sku"],
      role: "family",
      ...utms,
    });

    if (result.status === "ok") {
      // Redirect pra confirmação
      router.push(
        `/cadastro/confirmacao?session=${result.session_id}&wa=${encodeURIComponent(result.whatsapp_url)}`,
      );
    } else {
      setErrors({ [result.field || "_"]: result.message });
      setIsSubmitting(false);
    }
  };

  return (
    <>
      {/* Header */}
      <header className="text-center space-y-3 mb-8">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan text-xs font-semibold uppercase tracking-wider">
          <Sparkles className="h-3 w-3" />
          Plano selecionado · <strong>{planInfo.label}</strong>
        </div>
        <h1 className="text-3xl lg:text-4xl font-bold">
          Começar com a <span className="accent-gradient-text">Sofia</span>
        </h1>
        <p className="text-muted-foreground">
          Últimas informações e a gente finaliza a ativação no WhatsApp 💙
        </p>
      </header>

      {/* Plan resumo */}
      <div className="glass-card rounded-2xl p-4 mb-6 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">{planInfo.label}</div>
          <div className="text-[11px] text-muted-foreground">
            7 dias grátis no cartão · cancelamento livre
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tabular">
            <span className="text-sm text-muted-foreground">R$</span>{" "}
            {(planInfo.price_cents / 100).toFixed(2).replace(".", ",")}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            por mês
          </div>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="glass-card rounded-2xl p-6 space-y-4">
        <Field
          label="Seu nome completo"
          id="full_name"
          value={fullName}
          onChange={setFullName}
          error={errors.full_name}
          placeholder="Ex: Juliana Santos Oliveira"
          autoComplete="name"
          required
        />
        <Field
          label="Email"
          id="email"
          type="email"
          value={email}
          onChange={setEmail}
          error={errors.email}
          placeholder="seu@email.com"
          autoComplete="email"
          required
        />
        <Field
          label="Celular com DDD"
          id="phone"
          type="tel"
          value={phone}
          onChange={setPhone}
          error={errors.phone}
          placeholder="(11) 98765-4321"
          autoComplete="tel"
          hint="Sofia continua por aqui depois"
          required
        />

        {/* Seletor de plano (se quiser trocar) */}
        <div>
          <label className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground block mb-1.5">
            Plano
          </label>
          <select
            value={planSku}
            onChange={(e) => setPlanSku(e.target.value)}
            className="w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-xl px-3 py-2.5 text-sm focus:border-accent-cyan/50 focus:outline-none transition-colors"
          >
            {Object.entries(PLAN_LABELS).map(([sku, info]) => (
              <option key={sku} value={sku}>
                {info.label} — R$ {(info.price_cents / 100).toFixed(2).replace(".", ",")}/mês
              </option>
            ))}
          </select>
        </div>

        {errors._ && (
          <div className="text-sm text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-md px-3 py-2">
            {errors._}
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl accent-gradient text-slate-900 font-bold disabled:opacity-60 transition-all hover:shadow-[0_0_24px_rgba(49,225,255,0.4)]"
        >
          {isSubmitting ? (
            "Preparando seu WhatsApp..."
          ) : (
            <>
              Continuar no WhatsApp
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>

        <p className="text-[11px] text-muted-foreground text-center">
          Seus dados são protegidos pela LGPD · DPO nomeado ·{" "}
          <Link href="/planos" className="underline hover:text-foreground">
            voltar pros planos
          </Link>
        </p>
      </form>

      {/* Compliance footer */}
      <div className="mt-6 flex items-center justify-center gap-2 text-[11px] text-muted-foreground">
        <ShieldCheck className="h-3.5 w-3.5 text-classification-routine" />
        <span>Criptografia fim-a-fim · audit chain imutável · ANPD-ready</span>
      </div>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════
// Field
// ══════════════════════════════════════════════════════════════════

function Field({
  label,
  id,
  type = "text",
  value,
  onChange,
  error,
  placeholder,
  hint,
  autoComplete,
  required,
}: {
  label: string;
  id: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  placeholder?: string;
  hint?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground block mb-1.5"
      >
        {label}
        {required && <span className="text-classification-critical ml-0.5">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={`
          w-full bg-[hsl(222,30%,10%)] border rounded-xl px-3 py-2.5 text-sm
          focus:outline-none transition-colors
          ${error
            ? "border-classification-critical/50 focus:border-classification-critical"
            : "border-white/10 focus:border-accent-cyan/50"
          }
        `}
      />
      {error && (
        <div id={`${id}-error`} className="mt-1 text-[11px] text-classification-critical">
          {error}
        </div>
      )}
      {!error && hint && (
        <div id={`${id}-hint`} className="mt-1 text-[11px] text-muted-foreground">
          {hint}
        </div>
      )}
    </div>
  );
}

function FormSkeleton() {
  return (
    <div className="glass-card rounded-2xl p-6 space-y-4 animate-pulse">
      <div className="h-6 bg-white/5 rounded w-1/2" />
      <div className="h-10 bg-white/5 rounded" />
      <div className="h-10 bg-white/5 rounded" />
      <div className="h-10 bg-white/5 rounded" />
      <div className="h-12 bg-accent-cyan/10 rounded-xl" />
    </div>
  );
}
