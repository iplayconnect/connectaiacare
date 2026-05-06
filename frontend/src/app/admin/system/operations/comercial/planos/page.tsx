"use client";

import { useEffect, useState } from "react";
import {
  Package,
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

// ─── /admin/system/operations/comercial/planos ───
//
// Catálogo de planos. View read-only por enquanto + toggle active.
// CRUD completo via API (POST/PATCH) — UI de criação/edição numa
// próxima iteração se necessário.

function priceLabel(p: CommercialPlan): string {
  if (p.price_monthly_cents) {
    return `R$ ${(p.price_monthly_cents / 100).toFixed(2).replace(".", ",")}/mês`;
  }
  if (p.price_setup_cents) {
    return `Sob consulta + R$ ${(p.price_setup_cents / 100).toFixed(0)} setup`;
  }
  return "Sob consulta";
}

function scopeBadge(scope: CommercialPlan["scope"]) {
  const map = {
    subscription_b2c: { label: "B2C self-service", color: "bg-emerald-100 text-emerald-700" },
    commercial_sales: { label: "Comercial (Sofia recomenda)", color: "bg-blue-100 text-blue-700" },
  };
  const cfg = map[scope];
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

function personaBadge(persona: string | null) {
  if (!persona) return null;
  const colors: Record<string, string> = {
    individual: "bg-slate-100 text-slate-700",
    familia: "bg-purple-100 text-purple-700",
    ilpi: "bg-orange-100 text-orange-700",
    clinica: "bg-amber-100 text-amber-700",
    hospital: "bg-red-100 text-red-700",
    parceiro: "bg-cyan-100 text-cyan-700",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded font-medium ${
        colors[persona] || "bg-slate-100 text-slate-700"
      }`}
    >
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
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!hasRole(user, "super_admin", "admin_tenant", "comercial")) {
    return (
      <div className="p-8">
        <h1 className="text-xl font-semibold">Acesso negado</h1>
      </div>
    );
  }

  const isAdmin = hasRole(user, "super_admin");

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
            <Package className="w-6 h-6 text-cyan-500" />
            Catálogo de Planos
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {plans.length} planos visíveis
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as any)}
            className="text-sm border border-slate-300 rounded px-2 py-1 bg-white"
          >
            <option value="all">Todos</option>
            <option value="subscription_b2c">B2C self-service</option>
            <option value="commercial_sales">Comercial (Sofia)</option>
          </select>
          <label className="text-sm flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded"
            />
            Incluir inativos
          </label>
          <button
            onClick={load}
            disabled={loading}
            className="text-sm bg-white border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Atualizar
          </button>
        </div>
      </header>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {plans.map((p) => (
          <article
            key={p.id}
            className={`bg-white rounded-lg border p-4 ${
              p.active ? "border-slate-200" : "border-slate-200 opacity-60"
            }`}
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-slate-900 leading-tight">
                  {p.name}
                </h3>
                <code className="text-xs text-slate-500 font-mono">
                  {p.sku}
                </code>
              </div>
              {p.active ? (
                <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                  <Check className="w-3 h-3" /> ativo
                </span>
              ) : (
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                  <X className="w-3 h-3" /> inativo
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-1.5 mb-3">
              {scopeBadge(p.scope)}
              {personaBadge(p.target_persona)}
              {p.target_segment && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-slate-100 text-slate-600">
                  {p.target_segment}
                </span>
              )}
              {!p.public && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-amber-100 text-amber-700">
                  não público
                </span>
              )}
              {p.requires_demo_to_close && (
                <span className="text-xs px-2 py-0.5 rounded font-medium bg-violet-100 text-violet-700">
                  agenda obrigatório
                </span>
              )}
            </div>

            <div className="text-lg font-bold text-slate-900 mb-1">
              {priceLabel(p)}
            </div>

            {p.pitch_short && (
              <p className="text-sm text-slate-700 mb-3 leading-snug">
                {p.pitch_short}
              </p>
            )}

            <div className="text-xs text-slate-600 space-y-1 mb-3">
              {p.daily_calls_count !== undefined && p.daily_calls_count > 0 && (
                <div className="flex items-center gap-1">
                  <Phone className="w-3 h-3" />
                  {p.daily_calls_count} ligaç{p.daily_calls_count === 1 ? "ão" : "ões"}/dia
                </div>
              )}
              {p.daily_calls_count === 0 && p.scope === "subscription_b2c" && (
                <div className="flex items-center gap-1 text-slate-400">
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
                  <summary className="cursor-pointer text-cyan-600 hover:underline">
                    Ver features ({p.features.length})
                  </summary>
                  <ul className="mt-1 ml-4 list-disc text-xs text-slate-600 space-y-0.5">
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
                    className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-50 text-cyan-700 font-mono"
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
                className={`text-xs px-3 py-1 rounded border ${
                  p.active
                    ? "border-red-200 text-red-700 hover:bg-red-50"
                    : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                } disabled:opacity-50`}
              >
                {updating === p.id
                  ? "Atualizando…"
                  : p.active
                    ? "Desativar"
                    : "Ativar"}
              </button>
            )}
          </article>
        ))}
      </div>

      {plans.length === 0 && !loading && (
        <div className="text-center py-12 text-slate-500">
          Nenhum plano encontrado com esses filtros
        </div>
      )}
    </div>
  );
}
