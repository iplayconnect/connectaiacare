"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  Plus,
  Loader2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Pause,
  Users,
  Activity,
  Sparkles,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";

interface Tenant {
  id: string;
  name: string;
  ai_name: string;
  ai_voice: string;
  voice_did: string | null;
  whatsapp_phone: string | null;
  active: boolean;
  suspended: boolean;
  suspended_reason: string | null;
  patients_count: number;
  users_count: number;
  created_at: string;
  integrations_enabled: Record<string, boolean>;
}

export default function TenantsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [creating, setCreating] = useState(false);

  // Form state
  const [newId, setNewId] = useState("");
  const [newName, setNewName] = useState("");
  const [newAiName, setNewAiName] = useState("Sofia");

  const allowed = hasRole(user, "super_admin");

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.request<{ tenants: Tenant[] }>(
        "/api/system/tenants",
      );
      setTenants(res.tenants || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro carregando tenants");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
  }, [allowed, load]);

  const createTenant = async () => {
    setCreating(true);
    try {
      await api.request("/api/system/tenants", {
        method: "POST",
        body: JSON.stringify({
          id: newId.trim().toLowerCase(),
          name: newName.trim(),
          ai_name: newAiName.trim() || "Sofia",
        }),
      });
      setShowNewForm(false);
      setNewId("");
      setNewName("");
      setNewAiName("Sofia");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Erro ao criar tenant");
    } finally {
      setCreating(false);
    }
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Apenas super_admin pode acessar gestão de tenants.
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6 text-accent-cyan" />
            Tenants (Sistema)
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Gestão multi-tenant. Cada tenant tem sua identidade (Sofia,
            Emília, etc), canais (WhatsApp, voz) e integrações.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
          <Link
            href="/admin/system/tenants/new"
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan/5"
          >
            <Sparkles className="h-4 w-4" />
            Onboarding wizard
          </Link>
          <button
            onClick={() => setShowNewForm((v) => !v)}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg accent-gradient text-slate-900 font-medium"
          >
            <Plus className="h-4 w-4" />
            Novo (rápido)
          </button>
        </div>
      </header>

      {/* Form criação */}
      {showNewForm && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
          <h2 className="text-sm font-semibold">Novo tenant</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                ID (slug)
              </label>
              <input
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="ex: hospital_xyz"
                className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
              />
              <div className="text-xs text-muted-foreground mt-1">
                lowercase + underscore + numbers (3-40 chars)
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Nome (display)
              </label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="ex: Hospital XYZ"
                className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Nome IA
              </label>
              <input
                value={newAiName}
                onChange={(e) => setNewAiName(e.target.value)}
                placeholder="Sofia"
                className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={createTenant}
              disabled={creating || !newId || !newName}
              className="flex items-center gap-2 px-4 py-1.5 rounded-md accent-gradient text-slate-900 font-medium text-sm disabled:opacity-50"
            >
              {creating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              Criar
            </button>
            <button
              onClick={() => setShowNewForm(false)}
              className="px-4 py-1.5 rounded-md border border-white/10 text-sm hover:bg-white/5"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Lista */}
      <div className="rounded-xl border border-white/10 overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06]">
          <h2 className="text-sm font-semibold">
            {tenants.length} tenant{tenants.length === 1 ? "" : "s"}
          </h2>
        </div>
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="h-6 w-6 animate-spin mx-auto" />
          </div>
        ) : tenants.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">
            Nenhum tenant cadastrado.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2 font-medium">ID</th>
                <th className="text-left px-3 py-2 font-medium">Nome</th>
                <th className="text-left px-3 py-2 font-medium">IA</th>
                <th className="text-left px-3 py-2 font-medium">Canais</th>
                <th className="text-right px-3 py-2 font-medium">Pacientes</th>
                <th className="text-right px-3 py-2 font-medium">Users</th>
                <th className="text-center px-3 py-2 font-medium">Status</th>
                <th className="text-left px-3 py-2 font-medium">Criado</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr
                  key={t.id}
                  className="border-t border-white/[0.04] hover:bg-white/[0.015]"
                >
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link
                      href={`/admin/system/tenants/${t.id}`}
                      className="text-accent-cyan hover:underline"
                    >
                      {t.id}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{t.name}</td>
                  <td className="px-3 py-2 text-xs">
                    {t.ai_name} ({t.ai_voice})
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {t.voice_did && (
                      <span className="block">📞 {t.voice_did}</span>
                    )}
                    {t.whatsapp_phone && (
                      <span className="block">💬 {t.whatsapp_phone}</span>
                    )}
                    {!t.voice_did && !t.whatsapp_phone && "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {t.patients_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {t.users_count}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {t.suspended ? (
                      <span title={t.suspended_reason || ""}>
                        <Pause className="h-4 w-4 text-classification-attention inline" />
                      </span>
                    ) : t.active ? (
                      <CheckCircle2 className="h-4 w-4 text-classification-routine inline" />
                    ) : (
                      <XCircle className="h-4 w-4 text-muted-foreground inline" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {formatDateTime(t.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
