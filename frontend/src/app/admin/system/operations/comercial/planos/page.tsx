"use client";

import { useEffect, useState } from "react";
import {
  RefreshCw,
  Loader2,
  AlertCircle,
  Check,
  X,
  Phone,
  PhoneOff,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { commercialApi, type CommercialPlan } from "@/lib/api-commercial";

function priceLabel(p: CommercialPlan): string {
  if (p.price_monthly_cents) {
    return `R$ ${(p.price_monthly_cents / 100).toFixed(2).replace(".", ",")}/mês`;
  }
  if (p.price_setup_cents) {
    return `Sob consulta + R$ ${(p.price_setup_cents / 100).toFixed(0)} setup`;
  }
  return "Sob consulta";
}

const SCOPE_LABELS: Record<string, { label: string; cls: string }> = {
  subscription_b2c: {
    label: "B2C self-service",
    cls: "bg-emerald-500/20 text-emerald-300",
  },
  commercial_sales: {
    label: "Comercial (Sofia)",
    cls: "bg-blue-500/20 text-blue-300",
  },
};

const PERSONA_COLORS: Record<string, string> = {
  individual: "bg-slate-500/20 text-slate-300",
  familia: "bg-purple-500/20 text-purple-300",
  ilpi: "bg-orange-500/20 text-orange-300",
  clinica: "bg-amber-500/20 text-amber-300",
  hospital: "bg-red-500/20 text-red-300",
  parceiro: "bg-cyan-500/20 text-cyan-300",
};

function scopeBadge(scope: CommercialPlan["scope"]) {
  // Defensivo: scope pode vir null/undefined em rows antigos
  const cfg = SCOPE_LABELS[scope ?? ""] ?? {
    label: scope || "(sem scope)",
    cls: "bg-white/[0.04] text-slate-400",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function personaBadge(persona: string | null) {
  if (!persona) return null;
  const cls = PERSONA_COLORS[persona] ?? "bg-white/[0.04] text-slate-300";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${cls}`}>
      {persona}
    </span>
  );
}

export default function PlanosPage() {
  const { user, loading: authLoading } = useAuth();
  const [plans, setPlans] = useState<CommercialPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<"all" | "commercial_sales" | "subscription_b2c">("all");
  const [showInactive, setShowInactive] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await commercialApi.listPlans({
        scope: scope as any,
        active: showInactive ? undefined : true,
      });
      setPlans(r.items);
    } catch (e: any) {
      setError(e.message || "Falha carregando planos");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && hasRole(user, "super_admin", "admin_tenant", "comercial")) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, scope, showInactive]);

  async function toggleActive(plan: CommercialPlan) {
    setUpdating(plan.id);
    try {
      await commercialApi.updatePlan(plan.id, { active: !plan.active });
      await load();
    } catch (e: any) {
      setError(`Falha atualizando plano: ${e.message}`);
    } finally {
      setUpdating(null);
    }
  }

  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );
  }

  if (!hasRole(user, "super_admin", "admin_tenant", "comercial")) {
    return (
      <div className="p-8">
        <h1 className="text-xl font-semibold text-slate-100">Acesso negado</h1>
      </div>
    );
  }

  const isAdmin = hasRole(user, "super_admin");

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Catálogo de Planos</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {plans.length} {plans.length === 1 ? "plano visível" : "planos visíveis"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as any)}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5"
          >
            <option value="all">Todos</option>
            <option value="subscription_b2c">B2C self-service</option>
            <option value="commercial_sales">Comercial (Sofia)</option>
          </select>
          <label className="text-xs flex items-center gap-1.5 text-slate-300">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded bg-white/[0.04] border-white/20"
            />
            Inativos
          </label>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-3 py-1.5 hover:bg-white/[0.07] disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Atualizar
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {plans.map((p) => (
          <article
            key={p.id}
            className={`rounded-lg border p-4 ${
              p.active
                ? "border-white/10 bg-white/[0.03]"
                : "border-white/5 bg-white/[0.01] opacity-50"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-slate-100 leading-tight">
                  {p.name}
                </h3>
                <code className="text-[11px] text-slate-500 font-mono">
                  {p.sku}
                </code>
              </div>
              {p.active ? (
                <span className="text-xs bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded font-medium flex items-center gap-1 shrink-0">
                  <Check className="w-3 h-3" />
                  ativo
                </span>
              ) : (
                <span className="text-xs bg-white/[0.04] text-slate-400 px-2 py-0.5 rounded font-medium flex items-center gap-1 shrink-0">
                  <X className="w-3 h-3" />
                  inativo
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-1.5 mb-3">
              {scopeBadge(p.scope)}
              {personaBadge(p.target_persona)}
              {p.target_segment && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-white/[0.04] text-slate-300">
                  {p.target_segment}
                </span>
              )}
              {!p.public && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-amber-500/20 text-amber-300">
                  não público
                </span>
              )}
              {p.requires_demo_to_close && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-violet-500/20 text-violet-300">
                  agenda obrigatória
                </span>
              )}
            </div>

            <div className="text-lg font-bold text-slate-100 mb-1">
              {priceLabel(p)}
            </div>

            {p.pitch_short && (
              <p className="text-sm text-slate-300 mb-3 leading-snug">
                {p.pitch_short}
              </p>
            )}

            <div className="text-xs text-slate-400 space-y-1 mb-3">
              {p.daily_calls_count !== undefined && p.daily_calls_count > 0 && (
                <div className="flex items-center gap-1">
                  <Phone className="w-3 h-3" />
                  {p.daily_calls_count} ligaç{p.daily_calls_count === 1 ? "ão" : "ões"}/dia
                </div>
              )}
              {p.daily_calls_count === 0 && p.scope === "subscription_b2c" && (
                <div className="flex items-center gap-1 text-slate-600">
                  <PhoneOff className="w-3 h-3" />
                  sem ligações automáticas
                </div>
              )}
              {p.max_patients && (
                <div>
                  Até {p.max_patients} {p.max_patients === 1 ? "idoso" : "idosos"}
                </div>
              )}
              {Array.isArray(p.features) && p.features.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-cyan-400 hover:underline">
                    Ver features ({p.features.length})
                  </summary>
                  <ul className="mt-1 ml-4 list-disc text-xs text-slate-400 space-y-0.5">
                    {p.features.map((f: string, i: number) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>

            {Array.isArray(p.differentials) && p.differentials.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {p.differentials.map((d) => (
                  <span
                    key={d}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 font-mono border border-cyan-500/20"
                  >
                    {d}
                  </span>
                ))}
              </div>
            )}

            {isAdmin && (
              <button
                onClick={() => toggleActive(p)}
                disabled={updating === p.id}
                className={`text-xs px-3 py-1 rounded border transition ${
                  p.active
                    ? "border-red-500/30 text-red-300 hover:bg-red-500/10"
                    : "border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10"
                } disabled:opacity-50`}
              >
                {updating === p.id ? "Atualizando…" : p.active ? "Desativar" : "Ativar"}
              </button>
            )}
          </article>
        ))}
      </div>

      {plans.length === 0 && !loading && (
        <div className="text-center py-12 text-slate-500 italic">
          Nenhum plano encontrado com esses filtros
        </div>
      )}
    </div>
  );
}
