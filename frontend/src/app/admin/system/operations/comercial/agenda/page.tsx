"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Calendar,
  Phone,
  RefreshCw,
  Loader2,
  AlertCircle,
  Building2,
  Clock,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type UpcomingDemo,
  type UpcomingCallback,
} from "@/lib/api-commercial";

// ─── /admin/system/operations/comercial/agenda ───
//
// Calendário de demos próximas + callbacks pendentes.
// Time comercial vê o que precisa fazer hoje/semana.

function brDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function timeUntil(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms < 0) return "passou";
  const h = Math.floor(ms / (1000 * 60 * 60));
  if (h < 1) {
    const m = Math.floor(ms / (1000 * 60));
    return `em ${m}min`;
  }
  if (h < 24) return `em ${h}h`;
  const d = Math.floor(h / 24);
  return `em ${d}d`;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-500 bg-slate-100";
  if (score >= 80) return "text-emerald-700 bg-emerald-100";
  if (score >= 60) return "text-amber-700 bg-amber-100";
  return "text-slate-600 bg-slate-100";
}

export default function AgendaPage() {
  const { user, loading: authLoading } = useAuth();
  const [demos, setDemos] = useState<UpcomingDemo[]>([]);
  const [callbacks, setCallbacks] = useState<UpcomingCallback[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoDays, setDemoDays] = useState(14);
  const [callbackDays, setCallbackDays] = useState(7);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [d, c] = await Promise.all([
        commercialApi.upcomingDemos(demoDays),
        commercialApi.upcomingCallbacks(callbackDays),
      ]);
      setDemos(d.items);
      setCallbacks(c.items);
    } catch (e: any) {
      setError(e.message || "Falha carregando agenda");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && hasRole(user, "super_admin", "admin_tenant", "comercial")) {
      load();
    }
  }, [authLoading, user, demoDays, callbackDays]);

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

  return (
    <div className="p-6 lg:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
            <Calendar className="w-6 h-6 text-cyan-500" />
            Agenda Comercial
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Demos agendadas e callbacks pendentes
          </p>
        </div>
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
      </header>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Demos */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-blue-500" />
              Demos ({demos.length})
            </h2>
            <select
              value={demoDays}
              onChange={(e) => setDemoDays(parseInt(e.target.value))}
              className="text-xs border border-slate-300 rounded px-2 py-1 bg-white"
            >
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
              <option value={30}>30 dias</option>
            </select>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {demos.length === 0 ? (
              <div className="p-6 text-sm text-slate-500 text-center">
                Nenhuma demo agendada
              </div>
            ) : (
              demos.map((d) => (
                <Link
                  key={d.id}
                  href={`/admin/system/operations/comercial/leads/${d.lead_id}`}
                  className="block p-3 hover:bg-slate-50 transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-900 text-sm">
                        {d.full_name || "(sem nome)"}
                      </div>
                      {d.organization && (
                        <div className="text-xs text-slate-600 mt-0.5 flex items-center gap-1">
                          <Building2 className="w-3 h-3" />
                          {d.organization}
                        </div>
                      )}
                      <div className="text-xs text-blue-700 mt-1 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {brDate(d.scheduled_at)} · {d.duration_minutes}min
                        <span className="text-slate-500 ml-1">
                          ({timeUntil(d.scheduled_at)})
                        </span>
                      </div>
                    </div>
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${scoreColor(d.qualification_score)}`}
                    >
                      {d.qualification_score ?? "—"}
                    </span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>

        {/* Callbacks */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <Phone className="w-5 h-5 text-violet-500" />
              Callbacks ({callbacks.length})
            </h2>
            <select
              value={callbackDays}
              onChange={(e) => setCallbackDays(parseInt(e.target.value))}
              className="text-xs border border-slate-300 rounded px-2 py-1 bg-white"
            >
              <option value={3}>3 dias</option>
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
            </select>
          </div>
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {callbacks.length === 0 ? (
              <div className="p-6 text-sm text-slate-500 text-center">
                Nenhum callback pendente
              </div>
            ) : (
              callbacks.map((c) => (
                <Link
                  key={c.id}
                  href={`/admin/system/operations/comercial/leads/${c.lead_id}`}
                  className="block p-3 hover:bg-slate-50 transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-slate-900 text-sm">
                        {c.full_name || "(sem nome)"}
                      </div>
                      <div className="text-xs text-slate-600 mt-0.5 flex items-center gap-1">
                        <Phone className="w-3 h-3" />
                        {c.phone}
                        {c.organization && (
                          <>
                            <span>·</span>
                            <span>{c.organization}</span>
                          </>
                        )}
                      </div>
                      <div className="text-xs text-violet-700 mt-1 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {brDate(c.next_action_at)} · {c.call_type}
                        <span className="text-slate-500 ml-1">
                          ({timeUntil(c.next_action_at)})
                        </span>
                      </div>
                      {c.summary && (
                        <div className="text-xs text-slate-500 mt-1 italic line-clamp-2">
                          {c.summary}
                        </div>
                      )}
                    </div>
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${scoreColor(c.qualification_score)}`}
                    >
                      {c.qualification_score ?? "—"}
                    </span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
