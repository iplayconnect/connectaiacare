"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ShieldAlert,
  Loader2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Activity,
  Brain,
  PhoneCall,
  Stethoscope,
  ZapOff,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  api,
  type SafetyQueueItem,
  type SafetySeverity,
  type SafetyActionType,
  type SafetyCircuitState,
  ApiError,
} from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/seguranca/fila-revisao — Fila de revisão do Safety Guardrail.
// Toda ação clínica que a Sofia produz e que precisa de revisão humana
// cai aqui. Médico/enfermeiro/admin aprova ou rejeita.
// Acessível a: super_admin, admin_tenant, medico, enfermeiro,
// cuidador_pro, familia (mas decisão clínica preferencialmente
// médico/enfermeiro).
// ═══════════════════════════════════════════════════════════════════

const REFRESH_INTERVAL_MS = 30_000;

const SEVERITY_ORDER: Record<SafetySeverity, number> = {
  critical: 0,
  urgent: 1,
  attention: 2,
  info: 3,
};

const ACTION_LABELS: Record<SafetyActionType, string> = {
  informative: "Informativa",
  register_history: "Registrar histórico",
  invoke_attendant: "Acionar atendente",
  emergency_realtime: "Emergência",
  modify_prescription: "Modificar prescrição",
};

const ACTION_ICONS: Record<SafetyActionType, React.ComponentType<{ className?: string }>> = {
  informative: Brain,
  register_history: Activity,
  invoke_attendant: PhoneCall,
  emergency_realtime: AlertTriangle,
  modify_prescription: Stethoscope,
};

export default function FilaRevisaoPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<SafetyQueueItem[]>([]);
  const [stats, setStats] = useState<{
    pending: number;
    last_24h: number;
    approved: number;
    rejected: number;
    auto_executed: number;
  } | null>(null);
  const [circuit, setCircuit] = useState<SafetyCircuitState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<SafetySeverity | "all">("all");
  const [activeItem, setActiveItem] = useState<SafetyQueueItem | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const allowed = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
    "cuidador_pro",
    "familia",
  );
  const canResetCircuit = hasRole(user, "super_admin");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [queueRes, statsRes, circuitRes] = await Promise.all([
        api.safetyListQueue(100),
        api.safetyStats().catch(() => null),
        api.safetyCircuitStatus().catch(() => null),
      ]);
      const sorted = [...queueRes.items].sort((a, b) => {
        const so = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        if (so !== 0) return so;
        return (
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
      });
      setItems(sorted);
      if (statsRes?.stats) setStats(statsRes.stats as typeof stats);
      if (circuitRes) setCircuit(circuitRes);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Erro carregando fila";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
    const t = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(t);
  }, [allowed, load]);

  // tick para countdown de auto-execute
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(t);
  }, []);

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((i) => i.severity === filter);
  }, [items, filter]);

  async function decide(
    item: SafetyQueueItem,
    decision: "approved" | "rejected",
  ) {
    const notes = decision === "rejected"
      ? prompt("Motivo da rejeição (opcional):")
      : undefined;
    try {
      await api.safetyDecideQueueItem(item.id, decision, notes || undefined);
      setActiveItem(null);
      await load();
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    }
  }

  async function resetCircuit() {
    const reason = prompt("Motivo do reset do circuit breaker:");
    if (!reason) return;
    try {
      await api.safetyCircuitReset(undefined, reason);
      await load();
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    }
  }

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm text-muted-foreground">
          Sem permissão para revisar fila de segurança.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldAlert className="h-6 w-6 text-accent-cyan" />
            Fila de Revisão Clínica
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ações da Sofia que precisam de revisão humana antes de executar.
            Crítica/urgente tem timeout de auto-execução. Sofia tem inteligência;
            decisão é sua.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
        >
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </header>

      {circuit && circuit.state !== "closed" && (
        <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/30 flex items-start gap-3">
          <ZapOff className="h-5 w-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold text-red-300">
              Circuit breaker {circuit.state === "open" ? "ABERTO" : "MEIO-ABERTO"}
            </div>
            <div className="text-sm text-red-200/80 mt-1">
              Sofia auto-pausou neste tenant. Razão:{" "}
              {circuit.open_reason || "queue_rate_excedido"}.
              {circuit.open_until && (
                <> Reabre automaticamente em{" "}
                  <CountdownTo target={circuit.open_until} now={now} />.
                </>
              )}
            </div>
          </div>
          {canResetCircuit && (
            <button
              onClick={resetCircuit}
              className="px-3 py-1.5 text-xs rounded-md bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 text-red-200"
            >
              Forçar reset
            </button>
          )}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <StatCard
            label="Pendentes"
            value={stats.pending}
            highlight={stats.pending > 0}
          />
          <StatCard label="Últimas 24h" value={stats.last_24h} />
          <StatCard label="Aprovadas" value={stats.approved} />
          <StatCard label="Rejeitadas" value={stats.rejected} />
          <StatCard label="Auto-executadas" value={stats.auto_executed} />
        </div>
      )}

      <div className="flex items-center gap-2 mb-4">
        {(["all", "critical", "urgent", "attention", "info"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-xs rounded-md border transition ${
              filter === f
                ? "bg-accent-cyan text-slate-900 border-accent-cyan"
                : "border-white/10 hover:bg-white/5 text-muted-foreground"
            }`}
          >
            {f === "all"
              ? `Todas (${items.length})`
              : `${SEVERITY_LABELS[f]} (${items.filter((i) => i.severity === f).length})`}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando fila…
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center p-16 text-muted-foreground border border-dashed border-white/10 rounded-lg">
          <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-emerald-500/60" />
          <p className="text-sm">Nada para revisar.</p>
          <p className="text-xs mt-1">Sofia não enfileirou ações na seleção.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((item) => (
            <QueueRow
              key={item.id}
              item={item}
              now={now}
              onClick={() => setActiveItem(item)}
              onApprove={() => decide(item, "approved")}
              onReject={() => decide(item, "rejected")}
            />
          ))}
        </div>
      )}

      {activeItem && (
        <DetailDrawer
          item={activeItem}
          onClose={() => setActiveItem(null)}
          onApprove={() => decide(activeItem, "approved")}
          onReject={() => decide(activeItem, "rejected")}
        />
      )}
    </div>
  );
}

const SEVERITY_LABELS: Record<SafetySeverity, string> = {
  critical: "Crítica",
  urgent: "Urgente",
  attention: "Atenção",
  info: "Info",
};

const SEVERITY_BADGE: Record<SafetySeverity, string> = {
  critical: "bg-red-500/20 text-red-300 border-red-500/40",
  urgent: "bg-orange-500/20 text-orange-300 border-orange-500/40",
  attention: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  info: "bg-sky-500/15 text-sky-200 border-sky-500/30",
};

function StatCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`p-3 rounded-lg border ${
        highlight
          ? "border-accent-cyan/40 bg-accent-cyan/5"
          : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div
        className={`text-2xl font-bold ${
          highlight ? "text-accent-cyan" : "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function QueueRow({
  item,
  now,
  onClick,
  onApprove,
  onReject,
}: {
  item: SafetyQueueItem;
  now: number;
  onClick: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  const ActionIcon = ACTION_ICONS[item.action_type];
  const created = new Date(item.created_at).getTime();
  const ageMin = Math.floor((now - created) / 60000);
  const autoExec = item.auto_execute_after
    ? new Date(item.auto_execute_after).getTime()
    : null;
  const autoExecMs = autoExec ? autoExec - now : null;
  const timeoutSoon = autoExecMs !== null && autoExecMs > 0 && autoExecMs < 5 * 60_000;

  return (
    <div
      className={`p-4 rounded-lg border transition cursor-pointer hover:bg-white/[0.03] ${
        timeoutSoon
          ? "border-red-500/40 bg-red-500/5"
          : "border-white/10 bg-white/[0.02]"
      }`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <ActionIcon className="h-5 w-5 mt-0.5 text-accent-cyan flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span
              className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${SEVERITY_BADGE[item.severity]}`}
            >
              {SEVERITY_LABELS[item.severity]}
            </span>
            <span className="text-xs text-muted-foreground">
              {ACTION_LABELS[item.action_type]}
            </span>
            {item.patient_name && (
              <span className="text-xs text-muted-foreground">
                · {item.patient_name}
              </span>
            )}
            <span className="text-xs text-muted-foreground ml-auto">
              {ageMin < 1
                ? "agora"
                : ageMin < 60
                  ? `${ageMin}min atrás`
                  : `${Math.floor(ageMin / 60)}h${ageMin % 60}min atrás`}
            </span>
          </div>
          <div className="text-sm text-foreground/90 mb-1.5 line-clamp-2">
            {item.summary}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            {item.triggered_by_tool && (
              <span className="font-mono">{item.triggered_by_tool}</span>
            )}
            {item.triggered_by_persona && <span>· {item.triggered_by_persona}</span>}
            {item.sofia_confidence !== null && (
              <span>· conf {Math.round(item.sofia_confidence * 100)}%</span>
            )}
            {autoExecMs !== null && autoExecMs > 0 && (
              <span
                className={`flex items-center gap-1 ml-auto ${timeoutSoon ? "text-red-300" : ""}`}
              >
                <Clock className="h-3 w-3" />
                auto-exec em {formatDur(autoExecMs)}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-1.5 ml-2 flex-shrink-0">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onApprove();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-200"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Aprovar
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onReject();
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-200"
          >
            <XCircle className="h-3.5 w-3.5" />
            Rejeitar
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailDrawer({
  item,
  onClose,
  onApprove,
  onReject,
}: {
  item: SafetyQueueItem;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-2xl max-h-[90vh] overflow-y-auto rounded-t-xl sm:rounded-xl bg-slate-900 border border-white/10 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-white/10 p-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${SEVERITY_BADGE[item.severity]}`}
              >
                {SEVERITY_LABELS[item.severity]}
              </span>
              <span className="text-xs text-muted-foreground">
                {ACTION_LABELS[item.action_type]}
              </span>
            </div>
            <h2 className="text-lg font-semibold">
              {item.patient_name || "Sem paciente vinculado"}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <Field label="Resumo">
            <p className="text-sm whitespace-pre-wrap">{item.summary}</p>
          </Field>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Origem">
              <span className="font-mono text-xs">
                {item.triggered_by_tool || "—"}
              </span>
            </Field>
            <Field label="Persona">
              <span>{item.triggered_by_persona || "—"}</span>
            </Field>
            <Field label="Sessão Sofia">
              <span className="font-mono text-xs">
                {item.sofia_session_id?.slice(0, 8) || "—"}
              </span>
            </Field>
            <Field label="Confiança Sofia">
              <span>
                {item.sofia_confidence !== null
                  ? `${Math.round(item.sofia_confidence * 100)}%`
                  : "—"}
              </span>
            </Field>
            <Field label="Criado">
              <span className="text-xs">
                {new Date(item.created_at).toLocaleString("pt-BR")}
              </span>
            </Field>
            <Field label="Auto-exec após">
              <span className="text-xs">
                {item.auto_execute_after
                  ? new Date(item.auto_execute_after).toLocaleString("pt-BR")
                  : "—"}
              </span>
            </Field>
          </div>

          {item.details && Object.keys(item.details).length > 0 && (
            <Field label="Detalhes">
              <pre className="text-xs font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(item.details, null, 2)}
              </pre>
            </Field>
          )}
        </div>

        <div className="sticky bottom-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-4 flex gap-2 justify-end">
          <button
            onClick={onReject}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-red-500/15 hover:bg-red-500/25 border border-red-500/30 text-red-200"
          >
            <XCircle className="h-4 w-4" />
            Rejeitar
          </button>
          <button
            onClick={onApprove}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-200"
          >
            <CheckCircle2 className="h-4 w-4" />
            Aprovar
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

function CountdownTo({ target, now }: { target: string; now: number }) {
  const ms = new Date(target).getTime() - now;
  if (ms <= 0) return <span>já reabriu</span>;
  return <span>{formatDur(ms)}</span>;
}

function formatDur(ms: number): string {
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}min ${sec % 60}s`;
  const h = Math.floor(min / 60);
  return `${h}h ${min % 60}min`;
}
