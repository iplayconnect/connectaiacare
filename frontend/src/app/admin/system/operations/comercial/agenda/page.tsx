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
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type UpcomingDemo,
  type UpcomingCallback,
} from "@/lib/api-commercial";

function brDate(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function timeUntil(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms < 0) return "passou";
  const h = Math.floor(ms / 3600000);
  if (h < 1) return `em ${Math.floor(ms / 60000)}min`;
  if (h < 24) return `em ${h}h`;
  return `em ${Math.floor(h / 24)}d`;
}

function scoreBadge(score: number | null): string {
  if (score === null) return "bg-white/[0.04] text-slate-400";
  if (score >= 80) return "bg-emerald-500/20 text-emerald-300";
  if (score >= 60) return "bg-amber-500/20 text-amber-300";
  return "bg-white/[0.04] text-slate-300";
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, demoDays, callbackDays]);

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

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Agenda Comercial</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Demos agendadas e callbacks pendentes
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-3 py-1.5 hover:bg-white/[0.07] disabled:opacity-50 flex items-center gap-1.5"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Atualizar
        </button>
      </header>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Demos */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-blue-400" />
              Demos <span className="text-slate-500">({demos.length})</span>
            </h2>
            <select
              value={demoDays}
              onChange={(e) => setDemoDays(parseInt(e.target.value))}
              className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1"
            >
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
              <option value={30}>30 dias</option>
            </select>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
            {demos.length === 0 ? (
              <div className="p-8 text-sm text-slate-500 text-center italic">
                Nenhuma demo agendada
              </div>
            ) : (
              demos.map((d) => (
                <Link
                  key={d.id}
                  href={`/admin/system/operations/comercial/leads/${d.lead_id}`}
                  className="block p-3 hover:bg-white/[0.04] transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-slate-100">
                        {d.full_name || "(sem nome)"}
                      </div>
                      {d.organization && (
                        <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-1 truncate">
                          <Building2 className="w-3 h-3" />
                          {d.organization}
                        </div>
                      )}
                      <div className="text-xs text-blue-300 mt-1 flex items-center gap-1 flex-wrap">
                        <Clock className="w-3 h-3" />
                        <span>{brDate(d.scheduled_at)}</span>
                        <span className="text-slate-500">·</span>
                        <span>{d.duration_minutes}min</span>
                        <span className="text-slate-500">({timeUntil(d.scheduled_at)})</span>
                      </div>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${scoreBadge(d.qualification_score)}`}>
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
            <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Phone className="w-4 h-4 text-violet-400" />
              Callbacks <span className="text-slate-500">({callbacks.length})</span>
            </h2>
            <select
              value={callbackDays}
              onChange={(e) => setCallbackDays(parseInt(e.target.value))}
              className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1"
            >
              <option value={3}>3 dias</option>
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
            </select>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
            {callbacks.length === 0 ? (
              <div className="p-8 text-sm text-slate-500 text-center italic">
                Nenhum callback pendente
              </div>
            ) : (
              callbacks.map((c) => (
                <Link
                  key={c.id}
                  href={`/admin/system/operations/comercial/leads/${c.lead_id}`}
                  className="block p-3 hover:bg-white/[0.04] transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-slate-100">
                        {c.full_name || "(sem nome)"}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-1 truncate">
                        <Phone className="w-3 h-3" />
                        {c.phone}
                        {c.organization && (
                          <>
                            <span className="text-slate-500">·</span>
                            <span>{c.organization}</span>
                          </>
                        )}
                      </div>
                      <div className="text-xs text-violet-300 mt-1 flex items-center gap-1 flex-wrap">
                        <Clock className="w-3 h-3" />
                        <span>{brDate(c.next_action_at)}</span>
                        <span className="text-slate-500">·</span>
                        <span>{c.call_type}</span>
                        <span className="text-slate-500">({timeUntil(c.next_action_at)})</span>
                      </div>
                      {c.summary && (
                        <div className="text-xs text-slate-500 mt-1 italic line-clamp-2">
                          {c.summary}
                        </div>
                      )}
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${scoreBadge(c.qualification_score)}`}>
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
