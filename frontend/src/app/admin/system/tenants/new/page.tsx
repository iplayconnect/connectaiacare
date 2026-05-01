"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2,
  Brain,
  Palette,
  Phone,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Sparkles,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

type StepId = "identity" | "ai" | "channels" | "branding" | "review";

const STEPS: { id: StepId; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "identity", label: "Identidade", icon: Building2 },
  { id: "ai", label: "IA / Voz", icon: Brain },
  { id: "channels", label: "Canais", icon: Phone },
  { id: "branding", label: "Branding", icon: Palette },
  { id: "review", label: "Revisão", icon: Sparkles },
];

interface FormState {
  id: string;
  name: string;
  ai_name: string;
  ai_voice: string;
  ai_kickoff_phrase: string;
  voice_did: string;
  whatsapp_phone: string;
  whatsapp_evolution_instance: string;
  logo_url: string;
  primary_color: string;
  accent_color: string;
}

const INITIAL: FormState = {
  id: "",
  name: "",
  ai_name: "Sofia",
  ai_voice: "ara",
  ai_kickoff_phrase: "",
  voice_did: "",
  whatsapp_phone: "",
  whatsapp_evolution_instance: "",
  logo_url: "",
  primary_color: "",
  accent_color: "",
};

export default function NewTenantWizardPage() {
  const router = useRouter();
  const { user } = useAuth();
  const allowed = hasRole(user, "super_admin");

  const [step, setStep] = useState<StepId>("identity");
  const [form, setForm] = useState<FormState>(INITIAL);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  const idx = STEPS.findIndex((s) => s.id === step);
  const last = idx === STEPS.length - 1;

  const validateStep = (s: StepId): string | null => {
    if (s === "identity") {
      if (!form.id.trim()) return "ID é obrigatório.";
      if (!/^[a-z][a-z0-9_]{2,40}$/.test(form.id))
        return "ID precisa ser lowercase, underscore e dígitos (3-40).";
      if (!form.name.trim()) return "Nome é obrigatório.";
    }
    if (s === "ai") {
      if (!form.ai_name.trim()) return "Nome da IA é obrigatório.";
      if (!form.ai_voice.trim()) return "Voz é obrigatória.";
    }
    return null;
  };

  const next = () => {
    setError(null);
    const err = validateStep(step);
    if (err) {
      setError(err);
      return;
    }
    if (idx < STEPS.length - 1) setStep(STEPS[idx + 1].id);
  };

  const prev = () => {
    setError(null);
    if (idx > 0) setStep(STEPS[idx - 1].id);
  };

  const submit = async () => {
    setError(null);
    // Re-valida steps com campos obrigatórios
    for (const s of STEPS) {
      const err = validateStep(s.id);
      if (err) {
        setError(err);
        setStep(s.id);
        return;
      }
    }
    setSubmitting(true);
    try {
      await api.request("/api/system/tenants", {
        method: "POST",
        body: JSON.stringify({
          id: form.id.trim().toLowerCase(),
          name: form.name.trim(),
          ai_name: form.ai_name.trim(),
          ai_voice: form.ai_voice.trim(),
          ai_kickoff_phrase: form.ai_kickoff_phrase.trim() || null,
          voice_did: form.voice_did.trim() || null,
          whatsapp_phone: form.whatsapp_phone.trim() || null,
          whatsapp_evolution_instance:
            form.whatsapp_evolution_instance.trim() || null,
          logo_url: form.logo_url.trim() || null,
          primary_color: form.primary_color.trim() || null,
          accent_color: form.accent_color.trim() || null,
        }),
      });
      router.push(`/admin/system/tenants/${form.id.trim().toLowerCase()}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao criar tenant");
      setSubmitting(false);
    }
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Apenas super_admin.
      </div>
    );
  }

  return (
    <div className="max-w-[1100px] mx-auto px-6 py-6 space-y-6">
      <div className="flex items-center gap-2 text-sm">
        <button
          onClick={() => router.push("/admin/system/tenants")}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          Tenants
        </button>
        <span className="text-muted-foreground">/</span>
        <span>Novo</span>
      </div>

      <header>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Building2 className="h-6 w-6 text-accent-cyan" />
          Onboarding · novo tenant
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Provisiona um tenant completo (identidade, IA, canais e
          branding) em um fluxo guiado. Você poderá ajustar tudo depois.
        </p>
      </header>

      {/* Stepper */}
      <ol className="flex items-center gap-1 flex-wrap">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const active = s.id === step;
          const done = i < idx;
          return (
            <li key={s.id} className="flex items-center gap-1">
              <button
                onClick={() => {
                  // Permite voltar a passos já visitados
                  if (i <= idx) setStep(s.id);
                }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-colors ${
                  active
                    ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30"
                    : done
                      ? "text-foreground/80 hover:bg-white/[0.03] border border-transparent"
                      : "text-muted-foreground border border-transparent"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {s.label}
                {done && <CheckCircle2 className="h-3 w-3 text-classification-routine" />}
              </button>
              {i < STEPS.length - 1 && (
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
              )}
            </li>
          );
        })}
      </ol>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 space-y-4">
        {step === "identity" && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Building2 className="h-4 w-4 text-accent-cyan" />
              Identidade
            </h2>
            <p className="text-xs text-muted-foreground">
              ID é o slug interno (não muda depois). Nome é o display que
              aparece em UI/relatórios.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="ID (slug)"
                value={form.id}
                onChange={(v) => update({ id: v.toLowerCase() })}
                placeholder="ex: hospital_xyz"
                hint="lowercase + underscore + dígitos (3-40 chars)"
              />
              <Field
                label="Nome"
                value={form.name}
                onChange={(v) => update({ name: v })}
                placeholder="ex: Hospital XYZ"
              />
            </div>
          </div>
        )}

        {step === "ai" && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Brain className="h-4 w-4 text-accent-cyan" />
              Identidade da IA
            </h2>
            <p className="text-xs text-muted-foreground">
              Cada tenant tem sua própria IA. Sofia, Emília, Helena…
              escolha o nome e a voz Grok.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="Nome da IA"
                value={form.ai_name}
                onChange={(v) => update({ ai_name: v })}
                placeholder="Sofia"
              />
              <Field
                label="Voz Grok"
                value={form.ai_voice}
                onChange={(v) => update({ ai_voice: v })}
                placeholder="ara"
                hint="ara | sage | breeze | …"
              />
            </div>
            <Field
              label="Frase de saudação custom (opcional)"
              value={form.ai_kickoff_phrase}
              onChange={(v) => update({ ai_kickoff_phrase: v })}
              placeholder="Deixe vazio pra usar o default do scenario"
            />
          </div>
        )}

        {step === "channels" && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Phone className="h-4 w-4 text-accent-cyan" />
              Canais
            </h2>
            <p className="text-xs text-muted-foreground">
              Opcional na criação — pode ser configurado depois quando
              os números forem provisionados pelo operador SIP / Evolution.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="Voice DID (E.164 sem +)"
                value={form.voice_did}
                onChange={(v) => update({ voice_did: v })}
                placeholder="ex: 5130624363"
              />
              <Field
                label="WhatsApp (E.164 sem +)"
                value={form.whatsapp_phone}
                onChange={(v) => update({ whatsapp_phone: v })}
                placeholder="ex: 5551999548043"
              />
              <Field
                label="Evolution instance"
                value={form.whatsapp_evolution_instance}
                onChange={(v) => update({ whatsapp_evolution_instance: v })}
                placeholder="ex: hospitalxyz_main"
              />
            </div>
          </div>
        )}

        {step === "branding" && (
          <div className="space-y-4">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Palette className="h-4 w-4 text-accent-cyan" />
              Branding
            </h2>
            <p className="text-xs text-muted-foreground">
              Logo + cores aparecem em emails, relatórios e UI quando o
              tenant é selecionado. Tudo opcional na criação.
            </p>
            <Field
              label="Logo URL"
              value={form.logo_url}
              onChange={(v) => update({ logo_url: v })}
              placeholder="https://…/logo.png"
            />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="Cor primária"
                value={form.primary_color}
                onChange={(v) => update({ primary_color: v })}
                placeholder="#0ea5e9"
              />
              <Field
                label="Cor de destaque"
                value={form.accent_color}
                onChange={(v) => update({ accent_color: v })}
                placeholder="#22d3ee"
              />
            </div>
          </div>
        )}

        {step === "review" && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent-cyan" />
              Revisão
            </h2>
            <p className="text-xs text-muted-foreground">
              Confira tudo antes de criar. Você pode ajustar campos
              individuais depois em <code>/admin/system/tenants/{form.id || "<id>"}</code>.
            </p>
            <ReviewBlock title="Identidade" items={[
              ["ID", form.id || "—"],
              ["Nome", form.name || "—"],
            ]} />
            <ReviewBlock title="IA" items={[
              ["Nome", form.ai_name],
              ["Voz", form.ai_voice],
              ["Saudação", form.ai_kickoff_phrase || "(default)"],
            ]} />
            <ReviewBlock title="Canais" items={[
              ["Voice DID", form.voice_did || "—"],
              ["WhatsApp", form.whatsapp_phone || "—"],
              ["Evolution instance", form.whatsapp_evolution_instance || "—"],
            ]} />
            <ReviewBlock title="Branding" items={[
              ["Logo", form.logo_url || "—"],
              ["Primária", form.primary_color || "—"],
              ["Destaque", form.accent_color || "—"],
            ]} />
          </div>
        )}

        {error && (
          <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
            {error}
          </div>
        )}

        <div className="flex justify-between pt-2">
          <button
            onClick={prev}
            disabled={idx === 0 || submitting}
            className="px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Voltar
          </button>
          {!last ? (
            <button
              onClick={next}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-md accent-gradient text-slate-900 font-medium"
            >
              Próximo
              <ChevronRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={submitting}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              Criar tenant
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:border-accent-cyan/40"
      />
      {hint && (
        <div className="text-[10px] text-muted-foreground mt-1">{hint}</div>
      )}
    </div>
  );
}

function ReviewBlock({
  title,
  items,
}: {
  title: string;
  items: [string, string][];
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/10 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
        {title}
      </div>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-y-1 gap-x-4 text-xs">
        {items.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 truncate">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-mono truncate text-right">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
