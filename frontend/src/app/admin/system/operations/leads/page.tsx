"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Sparkles,
  Search,
  Filter,
  RefreshCw,
  Loader2,
  Mail,
  Building2,
  Phone,
  Calendar,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  TrendingUp,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

// /admin/system/operations/leads — funil B2B/B2C capturado pela Super Sofia.

interface Lead {
  id: string;
  phone: string;
  full_name: string | null;
  email: string | null;
  organization: string | null;
  role_self_declared: string | null;
  intent: string;
  confidence: number | null;
  source_channel: string;
  status: string;
  qualification_score: number | null;
  demo_link: string | null;
  demo_scheduled_at: string | null;
  qualified_at: string | null;
  converted_at: string | null;
  converted_to_tenant_id: string | null;
  lost_reason: string | null;
  last_contact_at: string | null;
  created_at: string;
  notes_count: number;
}

interface Stats {
  totals: {
    total: number;
    qualified: number;
    demo_scheduled: number;
    converted: number;
    lost: number;
  };
  by_intent: { intent: string; n: number }[];
}

const STATUS_COLORS: Record<string, string> = {
  new: "#3b82f6",
  qualified: "#10b981",
  demo_scheduled: "#06b6d4",
  in_demo: "#8b5cf6",
  proposal_sent: "#f59e0b",
  converted: "#22c55e",
  lost: "#94a3b8",
};

const INTENT_LABELS: Record<string, string> = {
  interesse_servico_b2c: "B2C · Serviço",
  interesse_servico_b2b: "B2B · Serviço",
  agendar_demo: "Demo",
  suporte_cliente: "Suporte",
  spam_abuso: "Spam",
  unclear: "Não classificado",
};

export default function LeadsPage() {
  const { user } = useAuth();
  const allowed = hasRole(user, "super_admin", "admin_tenant");

  const [leads, setLeads] = useState<Lead[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const qs = new URLSearchParams({ limit: "100", days: "30" });
      if (filter) qs.set("status", filter);
      if (search.trim()) qs.set("search", search.trim());
      const [listRes, statsRes] = await Promise.all([
        api.request<{ leads: Lead[] }>(`/api/admin/leads?${qs.toString()}`),
        api.request<Stats>("/api/admin/leads/stats?days=30"),
      ]);
      setLeads(listRes.leads || []);
      setStats(statsRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro carregando leads");
    } finally {
      setLoading(false);
    }
  }, [filter, search]);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Apenas super_admin / admin_tenant.
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-accent-cyan" />
            Leads · Funil
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Leads capturados pela Super Sofia via WhatsApp. B2B
            (gestores ILPI/clínica), B2C (família interessada) e
            agendamentos de demo. Last 30 dias.
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

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Total" value={stats.totals.total} color="#3b82f6" />
          <Stat label="Qualificados" value={stats.totals.qualified} color="#10b981" />
          <Stat label="Demo agendada" value={stats.totals.demo_scheduled} color="#06b6d4" />
          <Stat label="Convertidos" value={stats.totals.converted} color="#22c55e" />
          <Stat label="Perdidos" value={stats.totals.lost} color="#94a3b8" />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex items-center gap-2 px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="phone, nome ou empresa…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") load();
            }}
            className="bg-transparent outline-none text-sm w-64"
          />
        </div>
        {[
          ["", "Todos"],
          ["new", "Novos"],
          ["qualified", "Qualificados"],
          ["demo_scheduled", "Demo agendada"],
          ["converted", "Convertidos"],
          ["lost", "Perdidos"],
        ].map(([value, label]) => (
          <button
            key={value}
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

      {/* List */}
      <div className="rounded-xl border border-white/10 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="h-6 w-6 animate-spin mx-auto" />
          </div>
        ) : leads.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            Nenhum lead com esse filtro.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.02] text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Lead</th>
                <th className="text-left px-3 py-2 font-medium">Empresa / Papel</th>
                <th className="text-left px-3 py-2 font-medium">Intent</th>
                <th className="text-center px-3 py-2 font-medium">Status</th>
                <th className="text-left px-3 py-2 font-medium">Quando</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr
                  key={lead.id}
                  className="border-t border-white/[0.04] hover:bg-white/[0.02] cursor-pointer"
                  onClick={() => setSelectedLead(lead)}
                >
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="font-medium">
                        {lead.full_name || (
                          <em className="text-muted-foreground">
                            sem nome
                          </em>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        {lead.phone}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-xs">
                    {lead.organization && (
                      <div className="flex items-center gap-1">
                        <Building2 className="h-3 w-3" />
                        {lead.organization}
                      </div>
                    )}
                    {lead.role_self_declared && (
                      <div className="text-muted-foreground">
                        {lead.role_self_declared}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs">
                    <span className="px-2 py-0.5 rounded-full bg-white/[0.04]">
                      {INTENT_LABELS[lead.intent] || lead.intent}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-[11px]"
                      style={{
                        background: `${STATUS_COLORS[lead.status] || "#94a3b8"}20`,
                        color: STATUS_COLORS[lead.status] || "#94a3b8",
                        border: `1px solid ${STATUS_COLORS[lead.status] || "#94a3b8"}40`,
                      }}
                    >
                      {lead.status}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {timeAgo(lead.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}

      {selectedLead && (
        <LeadDrawer
          lead={selectedLead}
          onClose={() => setSelectedLead(null)}
          onUpdate={load}
        />
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
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

function LeadDrawer({
  lead,
  onClose,
  onUpdate,
}: {
  lead: Lead;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [detail, setDetail] = useState<{ lead: Lead; timeline: any[] } | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .request<{ lead: Lead; timeline: any[] }>(`/api/admin/leads/${lead.id}`)
      .then(setDetail)
      .catch(() => {});
  }, [lead.id]);

  const handleStatus = async (status: string) => {
    setSaving(true);
    try {
      await api.request(`/api/admin/leads/${lead.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      onUpdate();
      onClose();
    } catch (e) {
      alert(e instanceof Error ? e.message : "erro");
    } finally {
      setSaving(false);
    }
  };

  const handleAddNote = async () => {
    if (!note.trim()) return;
    setSaving(true);
    try {
      await api.request(`/api/admin/leads/${lead.id}`, {
        method: "PATCH",
        body: JSON.stringify({ note }),
      });
      setNote("");
      const refreshed = await api.request<{ lead: Lead; timeline: any[] }>(
        `/api/admin/leads/${lead.id}`,
      );
      setDetail(refreshed);
    } catch (e) {
      alert(e instanceof Error ? e.message : "erro");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <aside className="fixed top-0 right-0 bottom-0 z-[101] w-[min(640px,50vw)] bg-[hsl(222,47%,7%)]/98 border-l border-white/10 flex flex-col">
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold">{lead.full_name || lead.phone}</h2>
            <p className="text-xs text-muted-foreground font-mono">{lead.phone}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg border border-white/10 hover:bg-white/5"
          >
            <XCircle className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
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
              value={lead.confidence != null ? `${Math.round(lead.confidence * 100)}%` : null}
              icon={null}
            />
            <Field
              label="Demo"
              value={
                lead.demo_link
                  ? `${lead.demo_scheduled_at?.slice(0, 10) || ""} · ${lead.demo_link}`
                  : null
              }
              icon={Calendar}
            />
          </div>

          {/* Timeline */}
          {detail && detail.timeline.length > 0 && (
            <div>
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                Timeline
              </h3>
              <ul className="space-y-2 text-xs">
                {detail.timeline.map((ev, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 pl-2 border-l-2 border-accent-cyan/30"
                  >
                    <div className="flex-1">
                      <div className="font-mono text-muted-foreground">
                        {ev.at?.slice(11, 19) || ""} · {ev.action}
                      </div>
                      {ev.payload?.intent && (
                        <div className="text-foreground/80">
                          intent: {ev.payload.intent}
                        </div>
                      )}
                      {ev.payload?.sub_agent && (
                        <div className="text-foreground/80">
                          agent: {ev.payload.sub_agent}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Notas */}
          {detail?.lead.notes_count !== undefined && (
            <div>
              <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                Adicionar nota
              </h3>
              <div className="flex gap-2">
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="ex: liguei e marquei demo segunda 10h"
                  className="flex-1 bg-white/[0.03] border border-white/10 rounded-md px-3 py-1.5 text-sm"
                />
                <button
                  onClick={handleAddNote}
                  disabled={saving || !note.trim()}
                  className="px-3 py-1.5 text-xs rounded-md border border-white/10 hover:bg-white/5 disabled:opacity-50"
                >
                  Salvar
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-white/10 flex gap-2 flex-wrap">
          {lead.status === "new" && (
            <button
              onClick={() => handleStatus("qualified")}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-classification-routine/30 text-classification-routine hover:bg-classification-routine/10 disabled:opacity-50"
            >
              <CheckCircle2 className="h-4 w-4" />
              Qualificar
            </button>
          )}
          {lead.status !== "lost" && lead.status !== "converted" && (
            <button
              onClick={() => handleStatus("lost")}
              disabled={saving}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5 disabled:opacity-50"
            >
              <XCircle className="h-4 w-4" />
              Descartar
            </button>
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
      {Icon && <Icon className="h-4 w-4 text-muted-foreground mt-0.5" />}
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="text-foreground break-words">{value}</div>
      </div>
    </div>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}min`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}d`;
}
