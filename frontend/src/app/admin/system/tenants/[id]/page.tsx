"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft,
  Building2,
  Brain,
  Phone,
  MessageSquare,
  Activity,
  CheckCircle2,
  Pause,
  PlayCircle,
  RefreshCw,
  Loader2,
  Save,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

interface Tenant {
  id: string;
  name: string;
  ai_name: string;
  ai_voice: string;
  ai_kickoff_phrase: string | null;
  whatsapp_phone: string | null;
  voice_did: string | null;
  voice_sip_provider: string | null;
  active: boolean;
  suspended: boolean;
  suspended_reason: string | null;
  integrations_enabled: Record<string, boolean>;
  created_at: string;
  metadata: Record<string, unknown>;
}

interface TenantHealth {
  patients: number;
  users: number;
  caregivers: number;
  care_events_24h: number;
  care_events_open: number;
  last_care_event_at: string | null;
  last_user_at: string | null;
}

export default function TenantDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const tenantId = params?.id || "";

  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = useState<TenantHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Editable fields
  const [name, setName] = useState("");
  const [aiName, setAiName] = useState("");
  const [aiVoice, setAiVoice] = useState("");
  const [aiKickoff, setAiKickoff] = useState("");
  const [whatsappPhone, setWhatsappPhone] = useState("");
  const [voiceDid, setVoiceDid] = useState("");

  const allowed = hasRole(user, "super_admin");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [det, h] = await Promise.all([
        api.request<{ tenant: Tenant; config: Record<string, unknown> | null }>(
          `/api/system/tenants/${tenantId}`,
        ),
        api.request<{ metrics: TenantHealth }>(
          `/api/system/tenants/${tenantId}/health`,
        ).catch(() => null),
      ]);
      setTenant(det.tenant);
      setConfig(det.config);
      if (h) setHealth(h.metrics);
      setName(det.tenant.name);
      setAiName(det.tenant.ai_name);
      setAiVoice(det.tenant.ai_voice);
      setAiKickoff(det.tenant.ai_kickoff_phrase || "");
      setWhatsappPhone(det.tenant.whatsapp_phone || "");
      setVoiceDid(det.tenant.voice_did || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro carregando tenant");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    if (!allowed || !tenantId) return;
    load();
  }, [allowed, tenantId, load]);

  const save = async () => {
    setSaving(true);
    try {
      await api.request(`/api/system/tenants/${tenantId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          ai_name: aiName,
          ai_voice: aiVoice,
          ai_kickoff_phrase: aiKickoff || null,
          whatsapp_phone: whatsappPhone || null,
          voice_did: voiceDid || null,
        }),
      });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erro salvando");
    } finally {
      setSaving(false);
    }
  };

  const toggleSuspend = async () => {
    if (!tenant) return;
    const targetSuspended = !tenant.suspended;
    const reason = targetSuspended
      ? prompt("Motivo da suspensão (opcional):") || ""
      : "";
    try {
      await api.request(`/api/system/tenants/${tenantId}/suspend`, {
        method: "POST",
        body: JSON.stringify({ suspended: targetSuspended, reason }),
      });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erro");
    }
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Apenas super_admin.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="text-center py-16">
        <Loader2 className="h-6 w-6 animate-spin mx-auto" />
      </div>
    );
  }

  if (!tenant) {
    return (
      <div className="text-center py-16">
        <p className="text-muted-foreground mb-4">Tenant não encontrado</p>
        <button
          onClick={() => router.push("/admin/system/tenants")}
          className="px-3 py-2 rounded-lg border border-white/10"
        >
          Voltar
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-6 space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <button
          onClick={() => router.push("/admin/system/tenants")}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          Tenants
        </button>
        <span className="text-muted-foreground">/</span>
        <span className="font-mono text-xs">{tenant.id}</span>
        {tenant.suspended && (
          <span className="ml-2 px-2 py-0.5 rounded-full bg-classification-attention/15 text-classification-attention text-xs font-medium">
            Suspenso
          </span>
        )}
      </div>

      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6 text-accent-cyan" />
            {tenant.name}
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Criado {formatDateTime(tenant.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="p-2 rounded-lg border border-white/10 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={toggleSuspend}
            className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg ${
              tenant.suspended
                ? "bg-classification-routine/15 text-classification-routine border border-classification-routine/30"
                : "bg-classification-attention/15 text-classification-attention border border-classification-attention/30"
            }`}
          >
            {tenant.suspended ? (
              <>
                <PlayCircle className="h-4 w-4" />
                Reativar
              </>
            ) : (
              <>
                <Pause className="h-4 w-4" />
                Suspender
              </>
            )}
          </button>
        </div>
      </header>

      {/* Health metrics */}
      {health && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Pacientes" value={health.patients} />
          <Stat label="Usuários" value={health.users} />
          <Stat label="Cuidadores" value={health.caregivers} />
          <Stat label="Eventos 24h" value={health.care_events_24h} />
          <Stat label="Eventos abertos" value={health.care_events_open} />
        </div>
      )}

      {/* Edição */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-4">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Brain className="h-4 w-4 text-accent-cyan" />
          Identidade da IA
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Nome (display)" value={name} onChange={setName} />
          <Field label="Nome IA" value={aiName} onChange={setAiName} />
          <Field label="Voz Grok" value={aiVoice} onChange={setAiVoice} placeholder="ara" />
        </div>
        <Field
          label="Frase de saudação custom (opcional)"
          value={aiKickoff}
          onChange={setAiKickoff}
          placeholder="Deixe vazio pra usar o default do scenario"
        />
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-4">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Phone className="h-4 w-4 text-accent-cyan" />
          Canais
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Field
            label="Voice DID (número SIP inbound)"
            value={voiceDid}
            onChange={setVoiceDid}
            placeholder="ex: 5130624363"
          />
          <Field
            label="WhatsApp (número da IA)"
            value={whatsappPhone}
            onChange={setWhatsappPhone}
            placeholder="ex: 5551999548043"
          />
        </div>
      </div>

      {/* Integrações */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent-cyan" />
          Integrações
        </h2>
        <div className="text-xs text-muted-foreground">
          Edição via API por enquanto. UI em breve.
        </div>
        <pre className="text-xs bg-black/20 p-3 rounded overflow-x-auto">
          {JSON.stringify(tenant.integrations_enabled || {}, null, 2)}
        </pre>
      </div>

      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Salvar alterações
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-1 tabular">{value}</div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
      />
    </div>
  );
}
