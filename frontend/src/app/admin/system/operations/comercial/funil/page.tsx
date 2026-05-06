"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  RefreshCw,
  Loader2,
  Phone,
  Building2,
  TrendingUp,
  Calendar,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type FunnelData,
  type FunnelLead,
  type LeadStatus,
} from "@/lib/api-commercial";

// ─── /admin/system/operations/comercial/funil ───
//
// Kanban do funil comercial: leads agrupados por status
// (new → qualified → demo_scheduled → in_demo → proposal_sent).
// Status converted/lost ficam fora do kanban (são finais).

const COLUMNS: { key: LeadStatus; label: string; color: string }[] = [
  { key: "new", label: "Novos", color: "bg-slate-50 border-slate-200" },
  { key: "qualified", label: "Qualificados", color: "bg-cyan-50 border-cyan-200" },
  { key: "demo_scheduled", label: "Demo agendada", color: "bg-blue-50 border-blue-200" },
  { key: "in_demo", label: "Em demo", color: "bg-indigo-50 border-indigo-200" },
  { key: "proposal_sent", label: "Proposta enviada", color: "bg-violet-50 border-violet-200" },
];

function brDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function daysSince(iso: string): number {
  const ms = Date.now() - new Date(iso).getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-500 bg-slate-100";
  if (score >= 80) return "text-emerald-700 bg-emerald-100";
  if (score >= 60) return "text-amber-700 bg-amber-100";
  if (score >= 30) return "text-orange-700 bg-orange-100";
  return "text-red-700 bg-red-100";
}

function LeadCard({ lead }: { lead: FunnelLead }) {
  const days = daysSince(lead.created_at);
  return (
    <Link
      href={`/admin/system/operations/comercial/leads/${lead.id}`}
      className="block bg-white rounded-lg border border-slate-200 p-3 hover:border-cyan-400 hover:shadow-sm transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium text-slate-900 text-sm leading-tight">
          {lead.full_name || "(sem nome)"}
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${scoreColor(lead.qualification_score)}`}
        >
          {lead.qualification_score ?? "—"}
        </span>
      </div>
      {lead.organization && (
        <div className="text-xs text-slate-600 mt-1 flex items-center gap-1">
          <Building2 className="w-3 h-3" />
          <span className="truncate">{lead.organization}</span>
        </div>
      )}
      <div className="text-xs text-slate-500 mt-1 flex items-center gap-1">
        <Phone className="w-3 h-3" />
        <span>{lead.phone}</span>
      </div>
      {lead.demo_scheduled_at && (
        <div className="text-xs text-blue-700 mt-1.5 flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          <span>{brDate(lead.demo_scheduled_at)}</span>
        </div>
      )}
      <div className="text-[11px] text-slate-400 mt-1.5 flex justify-between">
        <span>há {days}d</span>
        <span>{lead.intent}</span>
      </div>
    </Link>
  );
}

export default function FunilPage() {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(60);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await commercialApi.funnelKanban(days);
      setData(d);
    } catch (e: any) {
      setError(e.message || "Falha carregando funil");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && hasRole(user, "super_admin", "admin_tenant", "comercial")) {
      load();
    }
  }, [authLoading, user, days]);

  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!hasRole(user, "super_admin", "admin_tenant", "comercial")) {
    return (
      <div className="p-8 max-w-2xl">
        <h1 className="text-xl font-semibold mb-2">Acesso negado</h1>
        <p className="text-slate-600">
          Você precisa ser super_admin, admin_tenant ou comercial.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-cyan-500" />
            Funil Comercial
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {data
              ? `${data.total} leads ativos · agrupados por estágio`
              : "Carregando…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="text-sm border border-slate-300 rounded px-2 py-1 bg-white"
          >
            <option value={30}>Últimos 30 dias</option>
            <option value={60}>Últimos 60 dias</option>
            <option value={90}>Últimos 90 dias</option>
            <option value={180}>Últimos 180 dias</option>
          </select>
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

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {COLUMNS.map((col) => {
            const items = data.columns[col.key] || [];
            return (
              <div
                key={col.key}
                className={`rounded-lg border p-3 ${col.color}`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-700">
                    {col.label}
                  </h3>
                  <span className="text-xs font-medium text-slate-600 bg-white px-2 py-0.5 rounded">
                    {items.length}
                  </span>
                </div>
                <div className="space-y-2 max-h-[70vh] overflow-y-auto">
                  {items.length === 0 ? (
                    <div className="text-xs text-slate-400 text-center py-8">
                      Vazio
                    </div>
                  ) : (
                    items.map((lead) => <LeadCard key={lead.id} lead={lead} />)
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <footer className="mt-6 pt-4 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
        <span>
          Status `converted` e `lost` não aparecem aqui — ver{" "}
          <Link
            href="/admin/system/operations/leads"
            className="text-cyan-600 hover:underline"
          >
            Leads (lista completa)
          </Link>
        </span>
        <span>
          <TrendingUp className="w-3 h-3 inline mr-1" />
          score 0-100 · {">"}=80 quente, {">"}=60 morno, {">"}=30 frio
        </span>
      </footer>
    </div>
  );
}
