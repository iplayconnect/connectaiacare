"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Search,
  RefreshCw,
  Loader2,
  Mail,
  Building2,
  Phone,
  Calendar,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ArrowUpRight,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type LeadFull,
  type LeadStatsResponse,
  type AuditTimelineEntry,
} from "@/lib/api-commercial";

// /comercial/lista — substitui o antigo /admin/system/operations/leads.
// Lista plana com filtros + busca + drawer com timeline (audit_log Sofia)
// + notas livres. Complementa o kanban (/comercial/funil) que só mostra
// status ativos.

const STATUS_CLS: Record<string, string> = {
  new: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  qualified: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  demo_scheduled: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  in_demo: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  proposal_sent: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  converted: "bg-emerald-600/20 text-emerald-200 border-emerald-500/40",
  lost: "bg-slate-500/15 text-slate-400 border-slate-500/30",
};

const STATUS_LABELS: Record<string, string> = {
  new: "Novo",
  qualified: "Qualificado",
  demo_scheduled: "Demo agendada",
  in_demo: "Em demo",
  proposal_sent: "Proposta",
  converted: "Convertido",
  lost: "Perdido",
};

const INTENT_LABELS: Record<string, string> = {
  interesse_servico_b2c: "B2C · Serviço",
  interesse_servico_b2b: "B2B · Serviço",
  agendar_demo: "Demo",
  suporte_cliente: "Suporte",
  spam_abuso: "Spam",
  unclear: "Não classificado",
  duvida_geral: "Dúvida geral",
};

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "new", label: "Novos" },
  { value: "qualified", label: "Qualificados" },
  { value: "demo_scheduled", label: "Demo agendada" },
  { value: "in_demo", label: "Em demo" },
  { value: "proposal_sent", label: "Proposta" },
  { value: "converted", label: "Convertidos" },
  { value: "lost", label: "Perdidos" },
];

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}min`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}

export default function ComercialListaPage() {
  const { user, loading: authLoading } = useAuth();
  const allowed = hasRole(user, "super_admin", "admin_tenant", "comercial");

  const [leads, setLeads] = useState<LeadFull[]>([]);
  const [stats, setStats] = useState<LeadStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [days, setDays] = useState(30);
  const [selectedLead, setSelectedLead] = useState<LeadFull | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const [listRes, statsRes] = await Promise.all([
        commercialApi.listLeads({
          limit: 100,
          days,
          status: filter || undefined,
          search: search.trim() || undefined,
        }),
        commercialApi.leadStats(days),
      ]);
      setLeads(listRes.leads || []);
      setStats(statsRes);
    } catch (e: any) {
      setError(e.message || "Erro carregando leads");
    } finally {
      setLoading(false);
    }
  }, [filter, search, days]);

  useEffect(() => {
    if (!authLoading && allowed) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, allowed, filter, days]);

  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="p-8">
        <h1 className="text-xl font-semibold text-slate-100">Acesso negado</h1>
        <p className="text-slate-400 mt-1">super_admin, admin_tenant ou comercial.</p>
      </div>
    );
  }

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8 max-w-[1500px]">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">
            Lista de Leads
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Capturados pela Sofia (WhatsApp/voice/web) + criação manual.
            Inclui convertidos e perdidos.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5 hover:bg-white/[0.06]"
          >
            <option value={7}>Últimos 7 dias</option>
            <option value={30}>Últimos 30 dias</option>
            <option value={60}>Últimos 60 dias</option>
            <option value={90}>Últimos 90 dias</option>
            <option value={180}>Últimos 180 dias</option>
            <option value={365}>Último ano</option>
          </select>
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

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          <Stat label="Total" value={stats.totals.total} accent="text-blue-300" />
          <Stat
            label="Qualificados"
            value={stats.totals.qualified}
            accent="text-emerald-300"
          />
          <Stat
            label="Demo agendada"
            value={stats.totals.demo_scheduled}
            accent="text-cyan-300"
          />
          <Stat
            label="Convertidos"
            value={stats.totals.converted}
            accent="text-emerald-200"
          />
          <Stat
            label="Perdidos"
            value={stats.totals.lost}
            accent="text-slate-400"
          />
        </div>
      )}

      {/* Filtros */}
      <div className="flex flex-wrap gap-2 items-center mb-4">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-white/[0.04] border border-white/10 rounded">
          <Search className="w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="phone, nome ou empresa…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") load();
            }}
            className="bg-transparent outline-none text-xs w-64 text-slate-100 placeholder:text-slate-600"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`px-2.5 py-1 text-xs rounded-full border transition ${
                filter === value
                  ? "bg-cyan-500/15 border-cyan-500/40 text-cyan-300"
                  : "border-white/10 hover:bg-white/[0.04] text-slate-400 hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded text-sm text-red-300 flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Tabela */}
      <div className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading ? (
          <div className="p-10 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-500" />
          </div>
        ) : leads.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500 italic">
            Nenhum lead com esse filtro.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Lead</th>
                <th className="text-left px-3 py-2.5 font-medium">Empresa / Papel</th>
                <th className="text-left px-3 py-2.5 font-medium">Intent</th>
                <th className="text-center px-3 py-2.5 font-medium">Status</th>
                <th className="text-right px-3 py-2.5 font-medium">Score</th>
                <th className="text-left px-3 py-2.5 font-medium">Quando</th>
                <th className="px-3 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr
                  key={lead.id}
                  className="border-t border-white/[0.04] hover:bg-white/[0.03] cursor-pointer transition"
                  onClick={() => setSelectedLead(lead)}
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="font-medium text-slate-100">
                        {lead.full_name || (
                          <em className="text-slate-500">sem nome</em>
                        )}
                      </span>
                      <span className="text-[11px] text-slate-500 font-mono">
                        {lead.phone}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-xs">
                    {lead.organization && (
                      <div className="flex items-center gap-1 text-slate-300">
                        <Building2 className="w-3 h-3 shrink-0 text-slate-500" />
                        <span className="truncate">{lead.organization}</span>
                      </div>
                    )}
                    {lead.role_self_declared && (
                      <div className="text-slate-500 mt-0.5">
                        {lead.role_self_declared}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs">
                    <span className="px-2 py-0.5 rounded bg-white/[0.04] text-slate-300">
                      {INTENT_LABELS[lead.intent] || lead.intent}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-[11px] border ${
                        STATUS_CLS[lead.status] || STATUS_CLS.new
                      }`}
                    >
                      {STATUS_LABELS[lead.status] || lead.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right text-xs text-slate-300 font-mono">
                    {lead.qualification_score ?? "—"}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-500">
                    {timeAgo(lead.created_at)}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <Link
                      href={`/admin/system/operations/comercial/leads/${lead.id}`}
                      className="text-xs text-cyan-400 hover:underline inline-flex items-center gap-0.5"
                      onClick={(e) => e.stopPropagation()}
                    >
                      timeline
                      <ArrowUpRight className="w-3 h-3" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedLead && (
        <LeadDrawer
          lead={selectedLead}
          onClose={() => setSelectedLead(null)}
          onUpdate={() => {
            setSelectedLead(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
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

function LeadDrawer({
  lead,
  onClose,
  onUpdate,
}: {
  lead: LeadFull;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [detail, setDetail] = useState<{
    lead: LeadFull;
    timeline: AuditTimelineEntry[];
  } | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    commercialApi
      .leadDetailAudit(lead.id)
      .then((d) => setDetail({ lead: d.lead, timeline: d.timeline }))
      .catch((e) => setActionError(e.message || "Erro carregando detalhe"));
  }, [lead.id]);

  async function handleStatus(status: "qualified" | "lost") {
    setSaving(true);
    setActionError(null);
    try {
      await commercialApi.updateLead(lead.id, { status });
      onUpdate();
    } catch (e: any) {
      setActionError(e.message || "Erro ao atualizar status");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddNote() {
    if (!note.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await commercialApi.appendLeadNote(lead.id, note.trim());
      setNote("");
      const refreshed = await commercialApi.leadDetailAudit(lead.id);
      setDetail({ lead: refreshed.lead, timeline: refreshed.timeline });
    } catch (e: any) {
      setActionError(e.message || "Erro ao salvar nota");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <aside className="fixed top-0 right-0 bottom-0 z-[101] w-[min(640px,55vw)] bg-slate-950 border-l border-white/10 flex flex-col">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-100 truncate">
              {lead.full_name || lead.phone}
            </h2>
            <p className="text-[11px] text-slate-500 font-mono">{lead.phone}</p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Link
              href={`/admin/system/operations/comercial/leads/${lead.id}`}
              className="text-[11px] text-cyan-400 hover:underline inline-flex items-center gap-0.5 px-2"
            >
              timeline completa
              <ArrowUpRight className="w-3 h-3" />
            </Link>
            <button
              onClick={onClose}
              className="p-1.5 rounded border border-white/10 hover:bg-white/[0.04] text-slate-400"
              aria-label="Fechar"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div className="space-y-2 text-sm">
            <Field label="Empresa" value={lead.organization} icon={Building2} />
            <Field label="Papel" value={lead.role_self_declared} icon={null} />
            <Field label="Email" value={lead.email} icon={Mail} />
            <Field
              label="Intent"
              value={INTENT_LABELS[lead.intent] || lead.intent}
              icon={null}
            />
            <Field
              label="Confidence"
              value={
                lead.confidence != null
                  ? `${Math.round(lead.confidence * 100)}%`
                  : null
              }
              icon={null}
            />
            <Field
              label="Score"
              value={
                lead.qualification_score != null
                  ? String(lead.qualification_score)
                  : null
              }
              icon={null}
            />
            <Field
              label="Demo agendada"
              value={
                lead.demo_scheduled_at
                  ? `${new Date(lead.demo_scheduled_at).toLocaleString("pt-BR")} ${
                      lead.demo_link ? `· ${lead.demo_link}` : ""
                    }`
                  : null
              }
              icon={Calendar}
            />
            <Field label="Source" value={lead.source_channel} icon={Phone} />
            {lead.lost_reason && (
              <Field label="Lost reason" value={lead.lost_reason} icon={null} />
            )}
          </div>

          {/* Timeline (audit_log Sofia) */}
          {detail && detail.timeline.length > 0 && (
            <div>
              <h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
                Timeline (turns Sofia)
              </h3>
              <ul className="space-y-2 text-xs max-h-[300px] overflow-y-auto pr-1">
                {detail.timeline.map((ev, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 pl-2 border-l-2 border-cyan-500/30"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-slate-500">
                        {ev.at?.slice(11, 19) || ""} · {ev.action}
                      </div>
                      {ev.payload?.intent && (
                        <div className="text-slate-300">
                          intent: {ev.payload.intent}
                        </div>
                      )}
                      {ev.payload?.sub_agent && (
                        <div className="text-slate-300">
                          agent: {ev.payload.sub_agent}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Adicionar nota */}
          <div>
            <h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
              Adicionar nota livre
            </h3>
            <div className="flex gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="ex: liguei e marquei demo segunda 10h"
                className="flex-1 bg-white/[0.04] border border-white/10 rounded px-3 py-1.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none focus:border-cyan-500/40"
              />
              <button
                onClick={handleAddNote}
                disabled={saving || !note.trim()}
                className="px-3 py-1.5 text-xs rounded border border-white/10 hover:bg-white/[0.04] disabled:opacity-50 text-slate-200"
              >
                Salvar
              </button>
            </div>
          </div>

          {actionError && (
            <div className="p-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-300 flex items-center gap-2">
              <AlertCircle className="w-3.5 h-3.5" />
              {actionError}
            </div>
          )}
        </div>

        <div className="px-5 py-3.5 border-t border-white/10 flex gap-2 flex-wrap">
          {lead.status === "new" && (
            <button
              onClick={() => handleStatus("qualified")}
              disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              Qualificar
            </button>
          )}
          {lead.status !== "lost" && lead.status !== "converted" && (
            <button
              onClick={() => handleStatus("lost")}
              disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-white/10 hover:bg-white/[0.04] disabled:opacity-50 text-slate-300"
            >
              <XCircle className="w-3.5 h-3.5" />
              Descartar
            </button>
          )}
          {saving && (
            <Loader2 className="w-4 h-4 animate-spin text-slate-500 ml-auto self-center" />
          )}
        </div>
      </aside>
    </>
  );
}

function Field({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | null;
  icon: React.ComponentType<{ className?: string }> | null;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2">
      {Icon && <Icon className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />}
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">
          {label}
        </div>
        <div className="text-slate-200 break-words text-sm">{value}</div>
      </div>
    </div>
  );
}
