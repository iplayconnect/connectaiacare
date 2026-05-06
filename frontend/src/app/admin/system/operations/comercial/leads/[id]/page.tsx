"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Phone,
  Calendar,
  MessageCircle,
  FileText,
  Loader2,
  RefreshCw,
  AlertCircle,
  Bot,
  User,
  Settings,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type LeadTimeline,
  type LeadActivity,
} from "@/lib/api-commercial";

function brDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function actorIcon(actor_type: LeadActivity["actor_type"]) {
  const cls = "w-4 h-4";
  switch (actor_type) {
    case "sofia":
      return <Bot className={`${cls} text-cyan-400`} />;
    case "human":
      return <User className={`${cls} text-violet-400`} />;
    case "system":
      return <Settings className={`${cls} text-slate-500`} />;
    case "lead":
      return <MessageCircle className={`${cls} text-emerald-400`} />;
  }
}

const IMPORTANCE_CLS: Record<string, string> = {
  minor: "bg-white/[0.04] text-slate-400",
  normal: "bg-blue-500/15 text-blue-300",
  important: "bg-amber-500/20 text-amber-300",
  critical: "bg-red-500/20 text-red-300",
};

function importanceBadge(importance: LeadActivity["importance"]) {
  return (
    <span
      className={`text-[11px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
        IMPORTANCE_CLS[importance] ?? IMPORTANCE_CLS.normal
      }`}
    >
      {importance}
    </span>
  );
}

const STATUS_CLS: Record<string, string> = {
  scheduled: "text-blue-300",
  confirmed: "text-cyan-300",
  completed: "text-emerald-300",
  no_show: "text-red-300",
  cancelled: "text-slate-400",
  sent: "text-blue-300",
  viewed: "text-cyan-300",
  accepted: "text-emerald-300",
  rejected: "text-red-300",
  expired: "text-slate-400",
  withdrawn: "text-slate-400",
};

export default function LeadDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const leadId = params.id;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, leadId]);

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
    <div className="px-6 lg:px-8 pt-6 pb-8 max-w-6xl">
      <header className="mb-5">
        <Link
          href="/admin/system/operations/comercial/funil"
          className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:underline mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Voltar pro funil
        </Link>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-slate-100">
            Lead{" "}
            <code className="font-mono text-sm text-slate-400">
              {leadId.slice(0, 8)}
            </code>
          </h1>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-3 py-1.5 hover:bg-white/[0.07] disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
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

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Coluna 1: Timeline */}
          <section className="lg:col-span-2">
            <h2 className="text-sm font-semibold text-slate-200 mb-3">
              Timeline <span className="text-slate-500">({data.activities.length})</span>
            </h2>
            <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
              {data.activities.length === 0 ? (
                <div className="p-6 text-sm text-slate-500 text-center italic">
                  Sem atividades ainda
                </div>
              ) : (
                data.activities.map((a) => (
                  <div key={a.id} className="p-3.5 flex items-start gap-3">
                    <div className="mt-0.5 shrink-0">{actorIcon(a.actor_type)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-sm text-slate-100 leading-snug">
                          {a.summary}
                        </div>
                        {importanceBadge(a.importance)}
                      </div>
                      <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5 flex-wrap">
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
          <aside className="space-y-5">
            <section>
              <h2 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-blue-400" />
                Demos <span className="text-slate-500">({data.demos.length})</span>
              </h2>
              <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
                {data.demos.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center italic">Nenhuma</div>
                ) : (
                  data.demos.map((d) => (
                    <div key={d.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-100">{brDate(d.scheduled_at)}</div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {d.duration_minutes}min · {d.meeting_provider || "—"} ·{" "}
                        <span className={`font-medium ${STATUS_CLS[d.status] ?? "text-slate-400"}`}>
                          {d.status}
                        </span>
                      </div>
                      {d.notes && (
                        <div className="text-xs text-slate-500 mt-1 italic">{d.notes}</div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            <section>
              <h2 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-1.5">
                <Phone className="w-4 h-4 text-violet-400" />
                Ligações <span className="text-slate-500">({data.calls.length})</span>
              </h2>
              <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
                {data.calls.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center italic">Nenhuma</div>
                ) : (
                  data.calls.map((c) => (
                    <div key={c.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-100 flex items-center justify-between">
                        <span>{brDate(c.started_at)}</span>
                        <span className="text-xs text-slate-500">
                          {c.direction === "inbound" ? "↓" : "↑"} {c.call_type}
                        </span>
                      </div>
                      {c.summary && (
                        <div className="text-xs text-slate-400 mt-1">{c.summary}</div>
                      )}
                      {c.outcome && (
                        <div className="text-xs text-slate-500 mt-1">
                          outcome: {c.outcome} · {c.sentiment || "—"}
                        </div>
                      )}
                      {c.next_action && (
                        <div className="text-xs text-blue-300 mt-1">
                          → {c.next_action} ({brDate(c.next_action_at)})
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            <section>
              <h2 className="text-sm font-semibold text-slate-200 mb-2 flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-amber-400" />
                Propostas <span className="text-slate-500">({data.proposals.length})</span>
              </h2>
              <div className="rounded-lg border border-white/10 bg-white/[0.02] divide-y divide-white/[0.04]">
                {data.proposals.length === 0 ? (
                  <div className="p-3 text-xs text-slate-500 text-center italic">Nenhuma</div>
                ) : (
                  data.proposals.map((p) => (
                    <div key={p.id} className="p-3 text-sm">
                      <div className="font-medium text-slate-100">{p.plan_name}</div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {p.plan_sku} · enviada {brDate(p.sent_at)}
                      </div>
                      <div className="text-xs mt-1">
                        Status:{" "}
                        <span className={`font-medium ${STATUS_CLS[p.status] ?? "text-slate-400"}`}>
                          {p.status}
                        </span>
                        {p.discount_percent && (
                          <span className="ml-2 text-amber-300">-{p.discount_percent}%</span>
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
