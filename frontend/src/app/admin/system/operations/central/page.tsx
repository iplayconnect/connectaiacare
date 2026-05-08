"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Headphones,
  RefreshCw,
  Loader2,
  Power,
  PhoneOutgoing,
  AlertCircle,
  Clock,
  User,
  Users,
  Activity,
  Send,
  XCircle,
  CheckCircle2,
  Stethoscope,
  ArrowUpRight,
  Pill,
  HeartPulse,
  Building2,
  Shield,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  operatorApi,
  type QueueItem,
  type QueueStats,
  type OperatorState,
  type OperatorShift,
  type PatientContextResponse,
  type HandoffMessage,
} from "@/lib/api-operator";

const PRIORITY_CLS: Record<string, string> = {
  P1: "bg-red-500/20 text-red-300 border-red-500/40",
  P2: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  P3: "bg-blue-500/15 text-blue-300 border-blue-500/30",
};

const TYPE_CLS: Record<string, string> = {
  commercial: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  clinical: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  support: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  operator: "bg-slate-500/20 text-slate-200 border-slate-500/40",
};

const STATUS_CLS: Record<string, string> = {
  pending: "bg-amber-500/15 text-amber-300",
  claimed: "bg-cyan-500/15 text-cyan-300",
  resolved: "bg-emerald-500/15 text-emerald-300",
  expired: "bg-slate-500/15 text-slate-400",
};

function formatWaiting(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  if (min < 60) return `${min}min`;
  const hr = Math.floor(min / 60);
  const m = min % 60;
  return `${hr}h${m}m`;
}

function brDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

export default function CentralOperatorPage() {
  const { user, loading: authLoading } = useAuth();
  const allowed = hasRole(user, "super_admin", "operador_central");

  // ─── Operator state ─────────────────────────────────────────────
  const [me, setMe] = useState<{
    operator: OperatorState;
    shift: OperatorShift | null;
    current_handoff: QueueItem | null;
  } | null>(null);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("");
  const [filterPriority, setFilterPriority] = useState<string>("");
  const [selectedHandoff, setSelectedHandoff] = useState<QueueItem | null>(null);

  // ─── Heartbeat ──────────────────────────────────────────────────
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [meRes, statsRes, queueRes] = await Promise.all([
        operatorApi.getMe(),
        operatorApi.getQueueStats(),
        operatorApi.getQueue({
          status: "pending,claimed",
          type: filterType || undefined,
          priority: filterPriority || undefined,
          limit: 60,
        }),
      ]);
      setMe({
        operator: meRes.operator,
        shift: meRes.shift,
        current_handoff: meRes.current_handoff,
      });
      setStats(statsRes);
      setQueue(queueRes.items || []);
    } catch (e: any) {
      setError(e.message || "Erro carregando central");
    } finally {
      setLoading(false);
    }
  }, [filterType, filterPriority]);

  useEffect(() => {
    if (!authLoading && allowed) refresh();
  }, [authLoading, allowed, refresh]);

  // Auto-refresh queue a cada 15s
  useEffect(() => {
    if (!allowed || authLoading) return;
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, [allowed, authLoading, refresh]);

  // Heartbeat a cada 60s quando online
  useEffect(() => {
    if (!me?.operator?.is_online) {
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      return;
    }
    if (heartbeatRef.current) return;
    heartbeatRef.current = setInterval(() => {
      operatorApi.heartbeat().catch(() => {});
    }, 60_000);
    return () => {
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
    };
  }, [me?.operator?.is_online]);

  if (authLoading)
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );

  if (!allowed)
    return (
      <div className="p-8">
        <h1 className="text-xl font-semibold text-slate-100">Acesso negado</h1>
        <p className="text-slate-400 mt-1 text-sm">
          Apenas operadores da central (operador_central) ou super admin.
        </p>
      </div>
    );

  async function handleToggleOnline() {
    if (!me) return;
    setBusy("toggle");
    try {
      if (me.operator.is_online) {
        await operatorApi.goOffline();
      } else {
        await operatorApi.goOnline();
      }
      await refresh();
    } catch (e: any) {
      setError(e.message || "Erro");
    } finally {
      setBusy(null);
    }
  }

  async function handleClaim(handoff: QueueItem) {
    setBusy(handoff.id);
    try {
      await operatorApi.claim(handoff.id);
      await refresh();
      setSelectedHandoff({ ...handoff, status: "claimed" });
    } catch (e: any) {
      setError(e.message || "Erro ao reivindicar");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8 max-w-[1600px]">
      {/* HEADER + STATE */}
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
            <Headphones className="w-5 h-5 text-cyan-400" />
            Central · ATENT 24/7
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Fila cross-tenant. Reivindicar handoff atribui o atendimento a você
            e abre o painel de contexto + chat.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleOnline}
            disabled={busy === "toggle" || loading}
            className={`text-xs rounded px-3 py-1.5 flex items-center gap-1.5 border ${
              me?.operator?.is_online
                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/20"
                : "bg-white/[0.04] border-white/10 text-slate-300 hover:bg-white/[0.07]"
            } disabled:opacity-50`}
          >
            {busy === "toggle" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Power className="w-3.5 h-3.5" />
            )}
            {me?.operator?.is_online ? "Online · sair de plantão" : "Entrar de plantão"}
          </button>
          <button
            onClick={refresh}
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

      {/* STATS BAR */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-5">
          <Stat label="Pendentes" value={stats.queue.pending} accent="text-amber-300" />
          <Stat label="Em atendimento" value={stats.queue.claimed} accent="text-cyan-300" />
          <Stat label="P1 abertos" value={stats.queue.p1_open} accent="text-red-300" />
          <Stat label="SLA estourado" value={stats.queue.sla_breached} accent="text-red-300" />
          <Stat label="Resolvidos 24h" value={stats.queue.resolved_24h} accent="text-emerald-300" />
          <Stat label="Operadores online" value={stats.operators_online} accent="text-violet-300" />
        </div>
      )}

      {/* CURRENT HANDOFF (operador atendendo) */}
      {me?.current_handoff && (
        <div className="mb-5 p-4 rounded-lg border border-cyan-500/40 bg-cyan-500/[0.06]">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <PhoneOutgoing className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-semibold text-slate-100">
                Atendimento em curso
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                PRIORITY_CLS[me.current_handoff.priority]
              }`}>
                {me.current_handoff.priority}
              </span>
            </div>
            <button
              onClick={() => setSelectedHandoff(me.current_handoff)}
              className="text-xs text-cyan-300 hover:underline inline-flex items-center gap-1"
            >
              Abrir painel <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
          <div className="text-sm text-slate-200">
            {me.current_handoff.context_summary?.slice(0, 200)}
            {me.current_handoff.context_summary?.length > 200 && "…"}
          </div>
          <div className="text-xs text-slate-500 font-mono mt-1">
            phone: {me.current_handoff.phone}
          </div>
        </div>
      )}

      {/* FILTROS */}
      <div className="flex flex-wrap gap-2 items-center mb-3">
        <div className="text-xs text-slate-500 mr-1">Tipo:</div>
        {[
          ["", "Todos"],
          ["operator", "Operador"],
          ["clinical", "Clínico"],
          ["commercial", "Comercial"],
          ["support", "Suporte"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilterType(v as string)}
            className={`px-2.5 py-1 text-xs rounded-full border transition ${
              filterType === v
                ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                : "border-white/10 hover:bg-white/[0.04] text-slate-400 hover:text-slate-200"
            }`}
          >
            {l}
          </button>
        ))}
        <div className="text-xs text-slate-500 mx-2">·</div>
        <div className="text-xs text-slate-500 mr-1">Prioridade:</div>
        {[
          ["", "Todas"],
          ["P1", "P1"],
          ["P2", "P2"],
          ["P3", "P3"],
        ].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setFilterPriority(v as string)}
            className={`px-2.5 py-1 text-xs rounded-full border transition ${
              filterPriority === v
                ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                : "border-white/10 hover:bg-white/[0.04] text-slate-400 hover:text-slate-200"
            }`}
          >
            {l}
          </button>
        ))}
      </div>

      {/* QUEUE TABLE */}
      <div className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading && queue.length === 0 ? (
          <div className="p-10 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-500" />
          </div>
        ) : queue.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500 italic">
            Fila vazia — sem handoffs nesse filtro.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Tipo</th>
                <th className="text-center px-3 py-2.5 font-medium">P</th>
                <th className="text-left px-3 py-2.5 font-medium">Phone</th>
                <th className="text-left px-3 py-2.5 font-medium">Razão</th>
                <th className="text-left px-3 py-2.5 font-medium">Resumo</th>
                <th className="text-center px-3 py-2.5 font-medium">Status</th>
                <th className="text-right px-3 py-2.5 font-medium">Espera</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {queue.map((h) => {
                const slaBreached =
                  h.sla_target_seconds && h.waiting_seconds > h.sla_target_seconds;
                return (
                  <tr
                    key={h.id}
                    className={`border-t border-white/[0.04] hover:bg-white/[0.03] cursor-pointer transition ${
                      slaBreached ? "bg-red-500/[0.03]" : ""
                    }`}
                    onClick={() => setSelectedHandoff(h)}
                  >
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                        TYPE_CLS[h.handoff_type] || "bg-white/[0.04] border-white/10"
                      }`}>
                        {h.handoff_type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                        PRIORITY_CLS[h.priority]
                      }`}>
                        {h.priority}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs font-mono text-slate-300">
                      {h.phone}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-300">
                      {h.reason}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-400 max-w-[300px] truncate">
                      {h.context_summary}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <span className={`text-[11px] px-2 py-0.5 rounded ${
                        STATUS_CLS[h.status] || ""
                      }`}>
                        {h.status}
                      </span>
                    </td>
                    <td className={`px-3 py-2.5 text-xs text-right tabular-nums ${
                      slaBreached ? "text-red-300 font-semibold" : "text-slate-500"
                    }`}>
                      {formatWaiting(h.waiting_seconds)}
                      {slaBreached && " ⚠"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {h.status === "pending" ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleClaim(h);
                          }}
                          disabled={busy === h.id || !me?.operator?.is_online}
                          title={!me?.operator?.is_online ? "Entre de plantão primeiro" : "Reivindicar"}
                          className="text-[11px] bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 rounded px-2 py-1 hover:bg-cyan-500/20 disabled:opacity-50"
                        >
                          {busy === h.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            "Pegar"
                          )}
                        </button>
                      ) : (
                        <span className="text-[11px] text-slate-500">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selectedHandoff && (
        <HandoffPanel
          handoff={selectedHandoff}
          isMe={selectedHandoff.id === me?.current_handoff?.id}
          onClose={() => setSelectedHandoff(null)}
          onUpdate={() => {
            refresh();
          }}
          onClaim={() => handleClaim(selectedHandoff)}
        />
      )}
    </div>
  );
}

function Stat({
  label, value, accent,
}: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3.5">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider">
        {label}
      </div>
      <div className={`text-2xl font-bold mt-1 tabular-nums ${accent}`}>
        {value}
      </div>
    </div>
  );
}

// ────── PAINEL DE ATENDIMENTO ──────

function HandoffPanel({
  handoff,
  isMe,
  onClose,
  onUpdate,
  onClaim,
}: {
  handoff: QueueItem;
  isMe: boolean;
  onClose: () => void;
  onUpdate: () => void;
  onClaim: () => void;
}) {
  const [ctx, setCtx] = useState<PatientContextResponse | null>(null);
  const [messages, setMessages] = useState<HandoffMessage[]>([]);
  const [loadingCtx, setLoadingCtx] = useState(true);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [escalating, setEscalating] = useState(false);
  const [showResolve, setShowResolve] = useState(false);
  const [showEscalate, setShowEscalate] = useState(false);

  const loadAll = useCallback(async () => {
    setLoadingCtx(true);
    try {
      const [ctxRes, msgsRes] = await Promise.all([
        operatorApi.getPatientContext(handoff.id),
        operatorApi.getMessages(handoff.id),
      ]);
      setCtx(ctxRes);
      setMessages(msgsRes.items || []);
    } catch {
      // graceful
    } finally {
      setLoadingCtx(false);
    }
  }, [handoff.id]);

  useEffect(() => {
    loadAll();
    const id = setInterval(() => {
      operatorApi.getMessages(handoff.id).then((r) =>
        setMessages(r.items || []),
      ).catch(() => {});
    }, 10_000);
    return () => clearInterval(id);
  }, [loadAll, handoff.id]);

  async function handleSend() {
    if (!text.trim()) return;
    setSending(true);
    try {
      await operatorApi.sendMessage(handoff.id, text.trim());
      setText("");
      const r = await operatorApi.getMessages(handoff.id);
      setMessages(r.items || []);
    } catch (e: any) {
      alert(e.message || "Erro ao enviar");
    } finally {
      setSending(false);
    }
  }

  async function handleResolve(payload: {
    outcome_category?: string;
    resolution_summary?: string;
  }) {
    setResolving(true);
    try {
      await operatorApi.resolve(handoff.id, payload);
      onUpdate();
      onClose();
    } catch (e: any) {
      alert(e.message || "Erro ao resolver");
    } finally {
      setResolving(false);
    }
  }

  async function handleEscalate(reason: string, urgency: "P1" | "P2" | "P3") {
    setEscalating(true);
    try {
      const r = await operatorApi.escalateClinical(handoff.id, { reason, urgency });
      alert(`Escalado pra clínico. Novo handoff: ${r.to_handoff_id} (${r.urgency})`);
      onUpdate();
    } catch (e: any) {
      alert(e.message || "Erro ao escalar");
    } finally {
      setEscalating(false);
      setShowEscalate(false);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed inset-x-4 top-4 bottom-4 z-[101] bg-slate-950 border border-white/10 rounded-xl shadow-2xl flex flex-col max-w-[1500px] mx-auto overflow-hidden">
        {/* HEADER */}
        <div className="px-5 py-3 border-b border-white/10 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3 min-w-0">
            <Headphones className="w-5 h-5 text-cyan-400 shrink-0" />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-slate-100">
                  Atendimento {handoff.id.slice(0, 8)}
                </h2>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  TYPE_CLS[handoff.handoff_type]
                }`}>
                  {handoff.handoff_type}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                  PRIORITY_CLS[handoff.priority]
                }`}>
                  {handoff.priority}
                </span>
                <span className={`text-[11px] px-2 py-0.5 rounded ${
                  STATUS_CLS[handoff.status]
                }`}>
                  {handoff.status}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                {handoff.phone} · iniciado {brDateTime(handoff.created_at)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {handoff.status === "pending" && (
              <button
                onClick={onClaim}
                className="text-xs bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 rounded px-3 py-1.5 hover:bg-cyan-500/20 inline-flex items-center gap-1.5"
              >
                <PhoneOutgoing className="w-3.5 h-3.5" />
                Pegar atendimento
              </button>
            )}
            {handoff.status === "claimed" && isMe && (
              <>
                <button
                  onClick={() => setShowEscalate(true)}
                  disabled={escalating}
                  className="text-xs bg-amber-500/15 border border-amber-500/40 text-amber-300 rounded px-3 py-1.5 hover:bg-amber-500/20 inline-flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Stethoscope className="w-3.5 h-3.5" />
                  Escalar pra clínico
                </button>
                <button
                  onClick={() => setShowResolve(true)}
                  disabled={resolving}
                  className="text-xs bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 rounded px-3 py-1.5 hover:bg-emerald-500/20 inline-flex items-center gap-1.5 disabled:opacity-50"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Resolver
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded border border-white/10 hover:bg-white/[0.04] text-slate-400"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* BODY: 3 columns */}
        <div className="flex-1 grid grid-cols-12 overflow-hidden">
          {/* CONTEXT */}
          <aside className="col-span-4 border-r border-white/10 overflow-y-auto p-4 space-y-4 bg-white/[0.01]">
            <ContextSection
              ctx={ctx}
              loading={loadingCtx}
              handoffSummary={handoff.context_summary}
            />
          </aside>

          {/* CHAT */}
          <section className="col-span-8 flex flex-col">
            <ChatHistory messages={messages} />
            <ChatInput
              value={text}
              onChange={setText}
              onSend={handleSend}
              disabled={sending || !isMe || handoff.status !== "claimed"}
              hint={
                !isMe
                  ? "Você não está atendendo este handoff"
                  : handoff.status !== "claimed"
                  ? "Handoff não está em atendimento ativo"
                  : ""
              }
            />
          </section>
        </div>
      </div>

      {showResolve && (
        <ResolveDialog
          onClose={() => setShowResolve(false)}
          onConfirm={(p) => {
            setShowResolve(false);
            handleResolve(p);
          }}
        />
      )}
      {showEscalate && (
        <EscalateDialog
          onClose={() => setShowEscalate(false)}
          onConfirm={handleEscalate}
        />
      )}
    </>
  );
}

function ContextSection({
  ctx,
  loading,
  handoffSummary,
}: {
  ctx: PatientContextResponse | null;
  loading: boolean;
  handoffSummary: string;
}) {
  if (loading)
    return (
      <div className="p-6 text-center">
        <Loader2 className="w-5 h-5 animate-spin mx-auto text-slate-500" />
      </div>
    );

  return (
    <>
      {/* SUMMARY (do handoff) */}
      <div>
        <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
          <Activity className="w-3 h-3" />
          Contexto do handoff
        </h3>
        <p className="text-xs text-slate-300 bg-white/[0.04] border border-white/10 rounded p-2 whitespace-pre-wrap">
          {handoffSummary || "(sem resumo)"}
        </p>
      </div>

      {/* PATIENT */}
      {ctx?.patient ? (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
            <User className="w-3 h-3" />
            Paciente
          </h3>
          <div className="bg-white/[0.04] border border-white/10 rounded p-3 space-y-1 text-xs">
            <div className="font-semibold text-slate-100 text-sm">
              {ctx.patient.full_name || "(sem nome)"}
            </div>
            {ctx.patient.cpf && (
              <div className="text-slate-400">CPF: {ctx.patient.cpf}</div>
            )}
            {ctx.patient.birth_date && (
              <div className="text-slate-400">
                Nasc: {ctx.patient.birth_date}
              </div>
            )}
            {ctx.patient.care_unit && (
              <div className="text-slate-400">
                <Building2 className="w-3 h-3 inline mr-1" />
                {ctx.patient.care_unit}
                {ctx.patient.room_number && ` · qto ${ctx.patient.room_number}`}
              </div>
            )}
            {ctx.patient.care_level && (
              <div className="text-slate-400">
                Nível: {ctx.patient.care_level}
              </div>
            )}
            {ctx.patient.allergies && Array.isArray(ctx.patient.allergies) && ctx.patient.allergies.length > 0 && (
              <div className="text-amber-300 mt-2">
                <Shield className="w-3 h-3 inline mr-1" />
                Alergias: {ctx.patient.allergies.join(", ")}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-xs text-slate-500 italic">
          Handoff sem paciente vinculado.
        </div>
      )}

      {/* RESPONSIBLE */}
      {ctx?.patient?.responsible && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Users className="w-3 h-3" />
            Responsável
          </h3>
          <div className="bg-white/[0.04] border border-white/10 rounded p-3 text-xs">
            <ResponsibleBlock data={ctx.patient.responsible} />
          </div>
        </div>
      )}

      {/* MEDICATIONS */}
      {ctx?.patient?.medications &&
        Array.isArray(ctx.patient.medications) &&
        ctx.patient.medications.length > 0 && (
          <div>
            <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
              <Pill className="w-3 h-3" />
              Medicações ({ctx.patient.medications.length})
            </h3>
            <div className="space-y-1">
              {ctx.patient.medications.slice(0, 8).map((m: any, i: number) => (
                <div
                  key={i}
                  className="text-[11px] bg-white/[0.04] border border-white/10 rounded px-2 py-1 text-slate-300"
                >
                  {typeof m === "string" ? m : (m.name || JSON.stringify(m))}
                </div>
              ))}
            </div>
          </div>
      )}

      {/* RECENT VITAL SIGNS */}
      {ctx?.recent_vital_signs && ctx.recent_vital_signs.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
            <HeartPulse className="w-3 h-3" />
            Vital signs recentes
          </h3>
          <div className="space-y-1">
            {ctx.recent_vital_signs.slice(0, 6).map((v) => (
              <div
                key={v.id}
                className="text-[11px] bg-white/[0.04] border border-white/10 rounded px-2 py-1 flex justify-between"
              >
                <span className="text-slate-300">
                  {v.vital_type}: {v.value_numeric}
                  {v.value_secondary != null && `/${v.value_secondary}`} {v.unit}
                </span>
                <span className="text-slate-500 font-mono">
                  {brDateTime(v.measured_at).slice(0, 16)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* RECENT EVENTS */}
      {ctx?.recent_events && ctx.recent_events.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 flex items-center gap-1.5">
            <Activity className="w-3 h-3" />
            Eventos recentes ({ctx.recent_events.length})
          </h3>
          <div className="space-y-1.5">
            {ctx.recent_events.slice(0, 5).map((e) => (
              <div
                key={e.id}
                className="text-[11px] bg-white/[0.04] border border-white/10 rounded p-2"
              >
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className={`px-1 py-0 rounded text-[10px] ${
                    e.current_classification === "critical" ? "bg-red-500/20 text-red-300" :
                    e.current_classification === "urgent" ? "bg-amber-500/20 text-amber-300" :
                    e.current_classification === "attention" ? "bg-blue-500/20 text-blue-300" :
                    "bg-white/[0.06] text-slate-400"
                  }`}>
                    {e.current_classification}
                  </span>
                  <span className="text-slate-500 font-mono">
                    {brDateTime(e.opened_at).slice(0, 16)}
                  </span>
                </div>
                <div className="text-slate-300">{e.summary || e.event_type}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function ResponsibleBlock({ data }: { data: any }) {
  if (!data) return <div className="text-slate-500">—</div>;
  if (typeof data === "string") return <div className="text-slate-300">{data}</div>;
  if (Array.isArray(data)) {
    return (
      <div className="space-y-2">
        {data.map((r, i) => (
          <ResponsibleBlock key={i} data={r} />
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-0.5">
      {data.name && <div className="text-slate-100 font-medium">{data.name}</div>}
      {data.phone && <div className="text-slate-300 font-mono">{data.phone}</div>}
      {data.relationship && (
        <div className="text-slate-500">{data.relationship}</div>
      )}
      {data.email && <div className="text-slate-400">{data.email}</div>}
    </div>
  );
}

function ChatHistory({ messages }: { messages: HandoffMessage[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages.length]);

  return (
    <div ref={ref} className="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-950">
      {messages.length === 0 && (
        <div className="text-center text-xs text-slate-500 italic py-12">
          Sem mensagens ainda. Escreva abaixo pra iniciar a conversa.
        </div>
      )}
      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex ${m.direction === "outbound" ? "justify-end" : "justify-start"}`}
        >
          <div className={`max-w-[70%] rounded-lg px-3 py-2 ${
            m.direction === "outbound"
              ? "bg-cyan-500/15 border border-cyan-500/30 text-slate-100"
              : "bg-white/[0.04] border border-white/10 text-slate-200"
          }`}>
            <div className="text-sm whitespace-pre-wrap">{m.text}</div>
            <div className="flex items-center justify-between gap-2 mt-1">
              <span className="text-[10px] text-slate-500">
                {m.author_name || (m.direction === "outbound" ? "operador" : "lead")}
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                {new Date(m.created_at).toLocaleTimeString("pt-BR", {
                  hour: "2-digit", minute: "2-digit",
                })}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ChatInput({
  value, onChange, onSend, disabled, hint,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
  hint: string;
}) {
  return (
    <div className="border-t border-white/10 p-3 bg-slate-900/50">
      {hint && (
        <div className="text-[11px] text-slate-500 italic mb-2">{hint}</div>
      )}
      <div className="flex gap-2">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!disabled) onSend();
            }
          }}
          rows={2}
          placeholder="Digite a mensagem (Enter envia, Shift+Enter quebra linha)"
          disabled={disabled}
          className="flex-1 bg-white/[0.04] border border-white/10 rounded px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500/40 resize-none disabled:opacity-50"
        />
        <button
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className="px-3 py-2 text-xs rounded bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-50 inline-flex items-center gap-1"
        >
          <Send className="w-3.5 h-3.5" />
          Enviar
        </button>
      </div>
    </div>
  );
}

function ResolveDialog({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (p: { outcome_category?: string; resolution_summary?: string }) => void;
}) {
  const [category, setCategory] = useState("resolved_by_phone");
  const [summary, setSummary] = useState("");
  return (
    <>
      <div className="fixed inset-0 z-[200] bg-black/70" onClick={onClose} />
      <div className="fixed inset-0 z-[201] flex items-center justify-center p-4">
        <div className="bg-slate-950 border border-white/10 rounded-xl shadow-2xl w-full max-w-md p-5">
          <h3 className="text-base font-semibold text-slate-100 mb-3">
            Resolver atendimento
          </h3>
          <div className="space-y-3">
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 block">
                Desfecho
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-white/[0.04] border border-white/10 rounded px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-cyan-500/40"
              >
                <option value="resolved_by_phone">Resolvido via WhatsApp/voz</option>
                <option value="escalated_to_specialist">Escalado pra especialista</option>
                <option value="closed_by_lead">Encerrado pelo lead</option>
                <option value="lead_lost">Lead não respondeu</option>
                <option value="system_error">Falha técnica</option>
                <option value="other">Outro</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 block">
                Resumo da resolução
              </label>
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                placeholder="O que rolou? O que foi feito?"
                className="w-full bg-white/[0.04] border border-white/10 rounded px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-cyan-500/40 resize-y"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={onClose}
              className="text-xs border border-white/10 text-slate-300 rounded px-3 py-1.5 hover:bg-white/[0.04]"
            >
              Cancelar
            </button>
            <button
              onClick={() =>
                onConfirm({
                  outcome_category: category,
                  resolution_summary: summary || undefined,
                })
              }
              className="text-xs bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 rounded px-3 py-1.5 hover:bg-emerald-500/20"
            >
              Confirmar resolução
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function EscalateDialog({
  onClose,
  onConfirm,
}: {
  onClose: () => void;
  onConfirm: (reason: string, urgency: "P1" | "P2" | "P3") => void;
}) {
  const [reason, setReason] = useState("");
  const [urgency, setUrgency] = useState<"P1" | "P2" | "P3">("P1");
  return (
    <>
      <div className="fixed inset-0 z-[200] bg-black/70" onClick={onClose} />
      <div className="fixed inset-0 z-[201] flex items-center justify-center p-4">
        <div className="bg-slate-950 border border-white/10 rounded-xl shadow-2xl w-full max-w-md p-5">
          <h3 className="text-base font-semibold text-slate-100 mb-1 flex items-center gap-2">
            <Stethoscope className="w-4 h-4 text-amber-400" />
            Escalar pra equipe clínica
          </h3>
          <p className="text-xs text-slate-400 mb-3">
            Cria um novo handoff tipo clínico com urgência alta. Esse handoff
            permanece reivindicado por você até resolver formalmente.
          </p>
          <div className="space-y-3">
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 block">
                Motivo
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                placeholder="Ex: Paciente relata dor no peito + falta de ar há 30min, sinal vital instável."
                className="w-full bg-white/[0.04] border border-white/10 rounded px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-cyan-500/40 resize-y"
              />
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 block">
                Urgência
              </label>
              <div className="flex gap-2">
                {(["P1", "P2", "P3"] as const).map((u) => (
                  <button
                    key={u}
                    onClick={() => setUrgency(u)}
                    className={`flex-1 text-xs rounded border px-3 py-1.5 transition ${
                      urgency === u
                        ? PRIORITY_CLS[u]
                        : "bg-white/[0.04] border-white/10 text-slate-400 hover:bg-white/[0.07]"
                    }`}
                  >
                    {u} {u === "P1" ? "(<5min)" : u === "P2" ? "(<30min)" : "(<2h)"}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <button
              onClick={onClose}
              className="text-xs border border-white/10 text-slate-300 rounded px-3 py-1.5 hover:bg-white/[0.04]"
            >
              Cancelar
            </button>
            <button
              onClick={() => onConfirm(reason || "operator_escalation", urgency)}
              disabled={!reason.trim()}
              className="text-xs bg-amber-500/15 border border-amber-500/40 text-amber-300 rounded px-3 py-1.5 hover:bg-amber-500/20 disabled:opacity-50"
            >
              Escalar pra clínico
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
