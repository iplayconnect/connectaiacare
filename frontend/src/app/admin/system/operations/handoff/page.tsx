"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  HeartHandshake,
  RefreshCw,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Hand,
  Clock,
  XCircle,
  Phone,
  User,
  MessageSquare,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/toast";

interface Handoff {
  id: string;
  trace_id: string;
  phone: string;
  tenant_id: string | null;
  reason: string;
  priority: string;
  status: string;
  context_preview: string;
  msgs_count: number;
  notified_central_at: string | null;
  claimed_at: string | null;
  resolved_at: string | null;
  resolution_summary: string | null;
  sla_target_seconds: number;
  sla_breached_at: string | null;
  created_at: string;
}

const PRIORITY_COLORS: Record<string, string> = {
  P1: "#ef4444",
  P2: "#f59e0b",
  P3: "#94a3b8",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  claimed: "#06b6d4",
  resolved: "#10b981",
  expired: "#94a3b8",
};

export default function HandoffQueuePage() {
  const { user } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const allowed = hasRole(user, "super_admin", "admin_tenant", "medico", "enfermeiro");

  const [items, setItems] = useState<Handoff[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string>("pending");
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [resolveFor, setResolveFor] = useState<Handoff | null>(null);
  const [resolveSummary, setResolveSummary] = useState("");

  const load = useCallback(
    async (opts: { silent?: boolean } = {}) => {
      const silent = opts.silent ?? false;
      if (silent) setRefreshing(true);
      else setError(null);
      try {
        const qs = new URLSearchParams({ days: "7", limit: "100" });
        if (filter) qs.set("status", filter);
        const [listRes, statsRes] = await Promise.all([
          api.request<{ items: Handoff[] }>(`/api/admin/handoff?${qs.toString()}`),
          api.request<{ totals: any; by_priority: any[] }>("/api/admin/handoff/stats?days=7"),
        ]);
        setItems(listRes.items || []);
        setStats(statsRes);
        if (silent) setError(null); // só limpa erro se silent veio bem
      } catch (e) {
        // Em modo silent, não derruba a UI com banner de erro — só loga.
        // Reload manual ou próximo tick mostra se persiste.
        if (!silent) {
          setError(e instanceof Error ? e.message : "Erro carregando");
        }
      } finally {
        if (silent) setRefreshing(false);
        else setLoading(false);
      }
    },
    [filter],
  );

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  // Auto-refresh: polling a cada 10s pra não obrigar operador 24/7 a
  // ficar dando F5. Pausa quando:
  //   - aba em background (document.hidden) — sem motivo pra puxar dados
  //     que ninguém vai ver, e libera quota da API
  //   - modal "Resolver" aberto — não atrapalhar o operador escrevendo
  //   - claim em andamento — evita race do redirect pro chat
  // Refetch imediato quando aba volta a ficar visível.
  useEffect(() => {
    if (!allowed) return;

    const tick = () => {
      if (document.hidden) return;
      if (resolveFor) return;
      if (busyId) return;
      load({ silent: true });
    };

    const interval = setInterval(tick, 10000);
    const onVisible = () => {
      if (!document.hidden && !resolveFor && !busyId) {
        load({ silent: true });
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [allowed, load, resolveFor, busyId]);

  const claim = async (id: string) => {
    setBusyId(id);
    try {
      await api.request(`/api/admin/handoff/${id}/claim`, { method: "POST" });
      // Após reivindicar, vai direto pro chat — operador pode atender
      // o lead em tempo real sem extra clique. Padrão "Aba Leads"
      // do CRM ConnectaIA.
      router.push(`/admin/system/operations/handoff/${id}/chat`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "erro");
      setBusyId(null);
    }
  };

  const openChat = (id: string) => {
    // Pra handoffs já claimed pelo próprio user (continuar atendimento)
    router.push(`/admin/system/operations/handoff/${id}/chat`);
  };

  const resolve = async () => {
    if (!resolveFor || !resolveSummary.trim()) return;
    setBusyId(resolveFor.id);
    try {
      await api.request(`/api/admin/handoff/${resolveFor.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution_summary: resolveSummary.trim() }),
      });
      setResolveFor(null);
      setResolveSummary("");
      load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "erro");
    } finally {
      setBusyId(null);
    }
  };

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Sem acesso.
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <HeartHandshake className="h-6 w-6 text-accent-cyan" />
            Handoff · Atendimento Humano
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Pedidos disparados pela Sofia pra Central 24h. Reivindique
            (claim) pra começar a atender, depois marque resolvido com
            resumo da resolução.
          </p>
        </div>
        <button
          onClick={() => load()}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-60"
          title="Auto-refresh a cada 10s (pausa em background ou com modal aberto)"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Atualizando…" : "Atualizar"}
        </button>
      </header>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Total 7d" value={stats.totals.total} />
          <Stat label="Pendentes" value={stats.totals.pending} color="#f59e0b" />
          <Stat label="Em atendimento" value={stats.totals.claimed} color="#06b6d4" />
          <Stat label="Resolvidos" value={stats.totals.resolved} color="#10b981" />
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {[
          ["pending", "Pendentes"],
          ["claimed", "Em atendimento"],
          ["resolved", "Resolvidos"],
          ["", "Todos"],
        ].map(([value, label]) => (
          <button
            key={value || "all"}
            onClick={() => setFilter(value as string)}
            className={`px-3 py-1.5 text-xs rounded-full border ${
              filter === value
                ? "bg-accent-cyan/15 border-accent-cyan/40 text-accent-cyan"
                : "border-white/10 hover:bg-white/[0.03] text-muted-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="h-6 w-6 animate-spin mx-auto" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            Nenhum handoff com esse filtro.
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {items.map((h) => (
              <li key={h.id} className="p-4 hover:bg-white/[0.02]">
                <div className="flex items-start gap-3">
                  <span
                    className="px-2 py-0.5 rounded text-[10px] font-bold mt-0.5"
                    style={{
                      background: `${PRIORITY_COLORS[h.priority]}20`,
                      color: PRIORITY_COLORS[h.priority],
                      border: `1px solid ${PRIORITY_COLORS[h.priority]}40`,
                    }}
                  >
                    {h.priority}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-sm flex-wrap">
                      <span className="font-mono">{h.phone}</span>
                      <span className="text-muted-foreground">·</span>
                      <span className="font-medium">{h.reason}</span>
                      <span
                        className="ml-auto text-[10px] px-2 py-0.5 rounded-full"
                        style={{
                          background: `${STATUS_COLORS[h.status]}20`,
                          color: STATUS_COLORS[h.status],
                          border: `1px solid ${STATUS_COLORS[h.status]}40`,
                        }}
                      >
                        {h.status}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {h.context_preview}
                    </p>
                    <div className="text-[11px] text-muted-foreground mt-2 flex items-center gap-3">
                      <span>SLA: {h.sla_target_seconds / 60}min</span>
                      <span>·</span>
                      <span>criado {timeAgo(h.created_at)}</span>
                      {h.claimed_at && (
                        <>
                          <span>·</span>
                          <span>reivindicado {timeAgo(h.claimed_at)}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col gap-1">
                    {h.status === "pending" && (
                      <button
                        onClick={() => claim(h.id)}
                        disabled={busyId === h.id}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
                      >
                        <Hand className="h-3 w-3" />
                        Reivindicar
                      </button>
                    )}
                    {h.status === "claimed" && (
                      <>
                        <button
                          onClick={() => openChat(h.id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md accent-gradient text-slate-900 font-medium"
                        >
                          <MessageSquare className="h-3 w-3" />
                          Abrir chat
                        </button>
                        <button
                          onClick={() => setResolveFor(h)}
                          disabled={busyId === h.id}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-classification-routine/30 text-classification-routine hover:bg-classification-routine/10 disabled:opacity-50"
                        >
                          <CheckCircle2 className="h-3 w-3" />
                          Resolver
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}

      {resolveFor && (
        <ResolveModal
          handoff={resolveFor}
          summary={resolveSummary}
          onChange={setResolveSummary}
          onConfirm={resolve}
          onClose={() => {
            setResolveFor(null);
            setResolveSummary("");
          }}
          busy={busyId === resolveFor.id}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color = "#3b82f6",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div
      className="rounded-xl border bg-white/[0.02] p-4"
      style={{ borderColor: `${color}30` }}
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-1 tabular" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function ResolveModal({
  handoff,
  summary,
  onChange,
  onConfirm,
  onClose,
  busy,
}: {
  handoff: Handoff;
  summary: string;
  onChange: (v: string) => void;
  onConfirm: () => void;
  onClose: () => void;
  busy: boolean;
}) {
  return (
    <>
      <div
        className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed top-1/2 left-1/2 z-[101] w-[min(560px,90vw)] -translate-x-1/2 -translate-y-1/2 bg-[hsl(222,47%,7%)]/98 border border-white/10 rounded-xl shadow-2xl">
        <div className="px-6 py-4 border-b border-white/10">
          <h3 className="text-base font-semibold">
            Resolver handoff · {handoff.phone}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Motivo: {handoff.reason}
          </p>
        </div>
        <div className="px-6 py-4 space-y-3">
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Resumo da resolução *
          </label>
          <textarea
            value={summary}
            onChange={(e) => onChange(e.target.value)}
            rows={4}
            placeholder="ex: liguei pro João, agendei demo terça 14h, mandei link Calendly"
            className="w-full bg-white/[0.03] border border-white/10 rounded-md px-3 py-2 text-sm focus:outline-none focus:border-accent-cyan/40"
          />
        </div>
        <div className="px-6 py-3 border-t border-white/10 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-3 py-2 text-sm rounded-md border border-white/10 hover:bg-white/5"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            disabled={busy || !summary.trim()}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md accent-gradient text-slate-900 font-medium disabled:opacity-50"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            Marcar resolvido
          </button>
        </div>
      </div>
    </>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return `há ${sec}s`;
  if (sec < 3600) return `há ${Math.floor(sec / 60)}min`;
  if (sec < 86400) return `há ${Math.floor(sec / 3600)}h`;
  return `há ${Math.floor(sec / 86400)}d`;
}
