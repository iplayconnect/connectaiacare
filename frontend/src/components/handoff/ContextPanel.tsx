"use client";

/**
 * ContextPanel — sidebar esquerda do chat handoff.
 *
 * Agrega 4 cards pra o operador entender o contexto sem ler todo o
 * histórico:
 *  1. Lead — phone, primeiro contato, total de turnos com Sofia
 *  2. Sofia snapshot — stage do CSM, lead_data extraído, intent
 *  3. Timing — created/claimed há X, SLA target, predição de breach
 *  4. Capabilities — whitelist anti-invenção (highlight pelo intent
 *     inferido do handoff.reason)
 *
 * Backend: GET /api/admin/handoff/<id>/context (admin_handoff_routes.py).
 * Polling 15s — dados mudam pouco vs chat polling 3s. Não vamos lá
 * com mais frequência pra não estressar CSM/capabilities cache.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Flag,
  Layers,
  Loader2,
  ShieldCheck,
  User as UserIcon,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CapabilityItem {
  code: string;
  label: string;
  category: string;
  requires_consent: boolean;
  highlighted: boolean;
}

interface CSMBlock {
  current_stage: string | null;
  current_agent: string | null;
  warmup_complete: boolean;
  qualification_complete: boolean;
  pending_question: string | null;
  lead_data: Record<string, unknown>;
  interactions_count: number;
  last_activity_at: string | null;
}

interface LeadBlock {
  phone: string;
  tenant_id: string;
  reason: string | null;
  context_summary: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  lead_msgs: number;
  sofia_msgs: number;
  total_msgs: number;
}

interface TimingBlock {
  created_at: string | null;
  claimed_at: string | null;
  resolved_at: string | null;
  sla_target_seconds: number;
  sla_breached_at: string | null;
  age_seconds: number;
  claim_age_seconds: number | null;
  sla_at_risk: boolean;
}

interface ContextPayload {
  status: "ok";
  handoff_id: string;
  intent_inferred: string;
  lead: LeadBlock;
  csm: CSMBlock | null;
  capabilities: CapabilityItem[];
  timing: TimingBlock;
}

const POLL_MS = 15000;

const INTENT_LABEL: Record<string, string> = {
  emergencia: "Emergência",
  medicacao: "Medicação",
  comercial: "Comercial",
  geral: "Geral",
};
const INTENT_TONE: Record<string, string> = {
  emergencia: "bg-rose-500/15 text-rose-500 border-rose-500/30",
  medicacao: "bg-amber-500/15 text-amber-500 border-amber-500/30",
  comercial: "bg-sky-500/15 text-sky-500 border-sky-500/30",
  geral: "bg-muted text-muted-foreground border-border",
};

interface Props {
  handoffId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ContextPanel({ handoffId, isOpen, onClose }: Props) {
  const [data, setData] = useState<ContextPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!handoffId) return;
    try {
      const res = await api.request<ContextPayload>(
        `/api/admin/handoff/${handoffId}/context`,
      );
      setData(res);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "erro carregando");
    } finally {
      setLoading(false);
    }
  }, [handoffId]);

  useEffect(() => {
    if (!isOpen) return;
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [isOpen, load]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 left-0 w-full sm:w-[320px] bg-background border-r border-border shadow-2xl z-40 flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Layers className="h-4 w-4 text-primary shrink-0" />
          <h3 className="font-semibold text-sm truncate">Contexto do lead</h3>
          {data?.intent_inferred && (
            <span
              className={cn(
                "text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase shrink-0",
                INTENT_TONE[data.intent_inferred] || INTENT_TONE.geral,
              )}
            >
              {INTENT_LABEL[data.intent_inferred] || data.intent_inferred}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
          title="Fechar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {loading && !data && (
          <div className="text-center py-8 text-muted-foreground text-sm">
            <Loader2 className="h-5 w-5 animate-spin inline" />
          </div>
        )}
        {error && (
          <div className="px-3 py-2 rounded-md bg-rose-500/10 text-rose-500 text-xs border border-rose-500/30">
            {error}
          </div>
        )}
        {data && (
          <>
            <LeadCard lead={data.lead} />
            <TimingCard timing={data.timing} />
            <SofiaCard csm={data.csm} />
            <CapabilitiesCard items={data.capabilities} />
          </>
        )}
      </div>
    </div>
  );
}

// ─── Cards ─────────────────────────────────────────────────────

function LeadCard({ lead }: { lead: LeadBlock }) {
  return (
    <Card title="Lead" icon={<UserIcon className="h-3.5 w-3.5" />}>
      <Row label="Telefone" value={<code className="text-xs">{lead.phone}</code>} />
      <Row label="Primeiro contato" value={fmtDate(lead.first_seen_at)} />
      <Row label="Última msg" value={fmtRelative(lead.last_seen_at)} />
      <Row
        label="Turnos"
        value={
          <span>
            <span className="text-foreground font-medium">{lead.lead_msgs}</span>
            <span className="text-muted-foreground"> lead · </span>
            <span className="text-foreground font-medium">{lead.sofia_msgs}</span>
            <span className="text-muted-foreground"> Sofia</span>
          </span>
        }
      />
      {lead.context_summary && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1">
            Resumo do escalate
          </p>
          <p className="text-xs text-muted-foreground line-clamp-4">
            {lead.context_summary}
          </p>
        </div>
      )}
    </Card>
  );
}

function TimingCard({ timing }: { timing: TimingBlock }) {
  const slaSecs = timing.sla_target_seconds;
  const ageVsSla =
    slaSecs > 0 ? Math.min(100, Math.round((timing.age_seconds / slaSecs) * 100)) : 0;
  return (
    <Card title="Timing" icon={<Clock className="h-3.5 w-3.5" />}>
      <Row label="Aberto há" value={fmtDuration(timing.age_seconds)} />
      <Row
        label="Reivindicado há"
        value={timing.claim_age_seconds !== null
          ? fmtDuration(timing.claim_age_seconds)
          : <em className="text-muted-foreground/60">não claimed</em>}
      />
      {slaSecs > 0 && (
        <>
          <Row label="SLA alvo" value={fmtDuration(slaSecs)} />
          <div className="mt-2">
            <div className="h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all",
                  timing.sla_breached_at
                    ? "bg-rose-500"
                    : timing.sla_at_risk
                    ? "bg-amber-500"
                    : "bg-emerald-500",
                )}
                style={{ width: `${ageVsSla}%` }}
              />
            </div>
            {timing.sla_breached_at && (
              <p className="text-[10px] text-rose-500 mt-1 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                SLA estourou em {fmtRelative(timing.sla_breached_at)}
              </p>
            )}
            {timing.sla_at_risk && !timing.sla_breached_at && (
              <p className="text-[10px] text-amber-500 mt-1 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                Risco de breach
              </p>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function SofiaCard({ csm }: { csm: CSMBlock | null }) {
  if (!csm) {
    return (
      <Card title="Sofia (CSM)" icon={<Bot className="h-3.5 w-3.5" />}>
        <p className="text-[11px] text-muted-foreground/60 italic">
          Sem state CSM pra esse lead. Provavelmente é um contato anterior à
          Phase C v2 ou ainda no warmup.
        </p>
      </Card>
    );
  }

  const ld = csm.lead_data || {};
  const knownFields: Array<[string, string]> = [
    ["primeiro_nome", "Nome"],
    ["nome", "Nome completo"],
    ["email", "Email"],
    ["cidade", "Cidade"],
    ["estado", "UF"],
    ["relacao", "Relação"],
    ["count_idosos", "Idosos sob cuidado"],
    ["organizacao", "Organização"],
    ["cargo_b2b", "Cargo"],
    ["intent_b2c_b2b", "Intent"],
  ];

  return (
    <Card title="Sofia (CSM)" icon={<Bot className="h-3.5 w-3.5" />}>
      {csm.current_stage && (
        <Row label="Stage" value={<code className="text-xs">{csm.current_stage}</code>} />
      )}
      {csm.current_agent && (
        <Row label="Agent" value={<code className="text-xs">{csm.current_agent}</code>} />
      )}
      <Row
        label="Status"
        value={
          <span className="flex items-center gap-1">
            {csm.warmup_complete ? (
              <CheckCircle2 className="h-3 w-3 text-emerald-500" />
            ) : (
              <Clock className="h-3 w-3 text-muted-foreground/60" />
            )}
            warmup
            <span className="text-muted-foreground">/</span>
            {csm.qualification_complete ? (
              <CheckCircle2 className="h-3 w-3 text-emerald-500" />
            ) : (
              <Clock className="h-3 w-3 text-muted-foreground/60" />
            )}
            qualif
          </span>
        }
      />

      {csm.pending_question && (
        <div className="mt-2 px-2 py-1.5 rounded bg-amber-500/5 border border-amber-500/20">
          <p className="text-[10px] uppercase tracking-wider text-amber-600/80 mb-0.5 flex items-center gap-1">
            <Flag className="h-2.5 w-2.5" /> Pergunta pendente
          </p>
          <p className="text-[11px] text-foreground line-clamp-3">
            {csm.pending_question}
          </p>
        </div>
      )}

      {Object.keys(ld).length > 0 && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1.5">
            Dados extraídos
          </p>
          <div className="space-y-0.5">
            {knownFields.map(([key, label]) => {
              const v = ld[key];
              if (v === undefined || v === null || v === "") return null;
              return (
                <div key={key} className="flex items-baseline gap-1.5 text-[11px]">
                  <span className="text-muted-foreground/70 w-24 shrink-0">
                    {label}
                  </span>
                  <span className="text-foreground font-medium truncate">
                    {String(v)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}

function CapabilitiesCard({ items }: { items: CapabilityItem[] }) {
  const visible = useMemo(
    () => items.slice(0, 12),
    [items],
  );
  if (visible.length === 0) {
    return (
      <Card title="Capabilities" icon={<ShieldCheck className="h-3.5 w-3.5" />}>
        <p className="text-[11px] text-muted-foreground/60 italic">
          Whitelist vazia ou indisponível.
        </p>
      </Card>
    );
  }
  return (
    <Card
      title="Capabilities (whitelist)"
      icon={<ShieldCheck className="h-3.5 w-3.5" />}
    >
      <p className="text-[10px] text-muted-foreground/60 mb-1.5">
        Anti-invenção · destacadas pelo intent
      </p>
      <div className="space-y-1">
        {visible.map((c) => (
          <div
            key={c.code}
            className={cn(
              "flex items-start gap-1.5 px-2 py-1 rounded text-[11px]",
              c.highlighted
                ? "bg-primary/10 border border-primary/30"
                : "bg-muted/30 border border-transparent",
            )}
          >
            <span
              className={cn(
                "mt-0.5 inline-block w-1 h-1 rounded-full shrink-0",
                c.highlighted ? "bg-primary" : "bg-muted-foreground/40",
              )}
            />
            <span className="flex-1 truncate text-foreground">
              {c.label}
            </span>
            {c.requires_consent && (
              <span
                className="text-[9px] text-amber-600/80 shrink-0"
                title="Requer consentimento LGPD"
              >
                ⚖
              </span>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── Primitivos ─────────────────────────────────────────────────

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-card/30 p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground/80 mb-2">
        {icon}
        <span className="font-semibold">{title}</span>
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Row({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-[11px]">
      <span className="text-muted-foreground/70 shrink-0">{label}</span>
      <span className="text-foreground text-right truncate">{value}</span>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function fmtRelative(iso: string | null): string {
  if (!iso) return "—";
  try {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    return fmtDuration(diff) + " atrás";
  } catch {
    return "—";
  }
}

function fmtDuration(secs: number | null): string {
  if (secs === null || secs === undefined || !Number.isFinite(secs))
    return "—";
  const s = Math.max(0, Math.floor(secs));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}
