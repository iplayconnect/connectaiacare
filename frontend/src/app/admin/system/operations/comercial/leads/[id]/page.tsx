"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Phone,
  Building2,
  Mail,
  Calendar,
  MessageCircle,
  FileText,
  Sparkles,
  Loader2,
  RefreshCw,
  AlertCircle,
  Bot,
  User,
  Settings,
  TrendingUp,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type LeadTimeline,
  type LeadActivity,
} from "@/lib/api-commercial";

// ─── /admin/system/operations/comercial/leads/[id] ───
//
// Detail page do lead com timeline cross-table:
// activities + demos + calls + proposals em ordem cronológica.

function brDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function brDateLong(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    dateStyle: "full",
    timeStyle: "short",
  });
}

function actorIcon(actor_type: LeadActivity["actor_type"]) {
  switch (actor_type) {
    case "sofia":
      return <Bot className="w-4 h-4 text-cyan-600" />;
    case "human":
      return <User className="w-4 h-4 text-violet-600" />;
    case "system":
      return <Settings className="w-4 h-4 text-slate-500" />;
    case "lead":
      return <MessageCircle className="w-4 h-4 text-emerald-600" />;
  }
}

function importanceBadge(importance: LeadActivity["importance"]) {
  const colors: Record<string, string> = {
    minor: "bg-slate-100 text-slate-600",
    normal: "bg-blue-100 text-blue-700",
    important: "bg-amber-100 text-amber-800",
    critical: "bg-red-100 text-red-800",
  };
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colors[importance]}`}>
      {importance}
    </span>
  );
}

export default function LeadDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: leadId } = use(params);
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<LeadTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await commercialApi.leadTimeline(leadId);
      setData(d);
    } catch (e: any) {
      setError(e.message || "Falha carregando timeline");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && hasRole(user, "super_admin", "admin_tenant", "comercial")) {
      load();
    }
  }, [authLoading, user, leadId]);

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
    <div className="p-6 lg:p-8 max-w-5xl">
      <header className="mb-6">
        <Link
          href="/admin/system/operations/comercial/funil"
          className="inline-flex items-center gap-1 text-sm text-cyan-600 hover:underline mb-3"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar pro funil
        </Link>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-cyan-500" />
            Lead {leadId.slice(0, 8)}
          </h1>
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Coluna 1: Timeline */}
          <section className="lg:col-span-2">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">
              Timeline ({data.activities.length})
            </h2>
            <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
              {data.activities.length === 0 ? (
                <div className="p-6 text-sm text-slate-500 text-center">
                  Sem atividades ainda
                </div>
              ) : (
                data.activities.map((a) => (
                  <div key={a.id} className="p-4 flex items-start gap-3">
                    <div className="mt-0.5">{actorIcon(a.actor_type)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-sm text-slate-900 leading-snug">
                          {a.summary}
                        </div>
                        {importanceBadge(a.importance)}
                      </div>
                      <div className="text-xs text-slate-500 mt-1 flex items-center gap-2">
                        <span className="font-mono">{a.activity_type}</span>
                        <span>·</span>
                        <span>{a.actor_name || a.actor_type}</span>
                        <span>·</span>
                        <span>{brDate(a.occurred_at)}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>

          {/* Coluna 2: Demos / Calls / Proposals */}
          <aside className="space-y-6">
            {/* Demos */}
            <section>
              <h2 className="text-base font-semibold text-slate-900 mb-2 flex items-center gap-1.5">
                <Calendar className="w-4 h-4" />
                Demos ({data.demos.length})
              </h2>
              <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
                {data.demos.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center">Nenhuma</div>
                ) : (
                  data.demos.map((d) => (
                    <div key={d.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-900">
                        {brDate(d.scheduled_at)}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {d.duration_minutes}min · {d.meeting_provider || "—"} ·{" "}
                        <span className={`font-medium ${
                          d.status === "completed" ? "text-emerald-600" :
                          d.status === "no_show" ? "text-red-600" :
                          d.status === "cancelled" ? "text-slate-500" :
                          "text-blue-600"
                        }`}>
                          {d.status}
                        </span>
                      </div>
                      {d.notes && (
                        <div className="text-xs text-slate-600 mt-1 italic">{d.notes}</div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Calls */}
            <section>
              <h2 className="text-base font-semibold text-slate-900 mb-2 flex items-center gap-1.5">
                <Phone className="w-4 h-4" />
                Ligações ({data.calls.length})
              </h2>
              <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
                {data.calls.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center">Nenhuma</div>
                ) : (
                  data.calls.map((c) => (
                    <div key={c.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-900 flex items-center justify-between">
                        <span>{brDate(c.started_at)}</span>
                        <span className="text-xs text-slate-500">
                          {c.direction === "inbound" ? "↓" : "↑"} {c.call_type}
                        </span>
                      </div>
                      {c.summary && (
                        <div className="text-xs text-slate-600 mt-1">{c.summary}</div>
                      )}
                      {c.outcome && (
                        <div className="text-xs text-slate-500 mt-1">
                          outcome: {c.outcome} · {c.sentiment || "—"}
                        </div>
                      )}
                      {c.next_action && (
                        <div className="text-xs text-blue-700 mt-1">
                          → {c.next_action} ({brDate(c.next_action_at)})
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Proposals */}
            <section>
              <h2 className="text-base font-semibold text-slate-900 mb-2 flex items-center gap-1.5">
                <FileText className="w-4 h-4" />
                Propostas ({data.proposals.length})
              </h2>
              <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
                {data.proposals.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center">Nenhuma</div>
                ) : (
                  data.proposals.map((p) => (
                    <div key={p.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-900">
                        {p.plan_name}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {p.plan_sku} · enviada {brDate(p.sent_at)}
                      </div>
                      <div className="text-xs mt-1">
                        Status:{" "}
                        <span
                          className={`font-medium ${
                            p.status === "accepted"
                              ? "text-emerald-600"
                              : p.status === "rejected"
                              ? "text-red-600"
                              : p.status === "expired"
                              ? "text-slate-500"
                              : "text-blue-600"
                          }`}
                        >
                          {p.status}
                        </span>
                        {p.discount_percent && (
                          <span className="ml-2 text-amber-600">
                            -{p.discount_percent}%
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        Válida até {p.valid_until}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
