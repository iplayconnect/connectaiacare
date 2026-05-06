"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  RefreshCw,
  Loader2,
  Phone,
  Building2,
  TrendingUp,
  Calendar,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  commercialApi,
  type FunnelData,
  type FunnelLead,
  type LeadStatus,
} from "@/lib/api-commercial";

const COLUMNS: { key: LeadStatus; label: string; accent: string }[] = [
  { key: "new", label: "Novos", accent: "bg-slate-500/20 text-slate-200" },
  { key: "qualified", label: "Qualificados", accent: "bg-cyan-500/20 text-cyan-200" },
  { key: "demo_scheduled", label: "Demo agendada", accent: "bg-blue-500/20 text-blue-200" },
  { key: "in_demo", label: "Em demo", accent: "bg-indigo-500/20 text-indigo-200" },
  { key: "proposal_sent", label: "Proposta enviada", accent: "bg-violet-500/20 text-violet-200" },
];

function brDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

function scoreBadge(score: number | null): string {
  if (score === null) return "bg-white/[0.04] text-slate-400";
  if (score >= 80) return "bg-emerald-500/20 text-emerald-300";
  if (score >= 60) return "bg-amber-500/20 text-amber-300";
  if (score >= 30) return "bg-orange-500/20 text-orange-300";
  return "bg-red-500/20 text-red-300";
}

function LeadCard({
  lead,
  onDragStart,
  onDragEnd,
  isDragging,
}: {
  lead: FunnelLead;
  onDragStart: (e: React.DragEvent, leadId: string, fromStatus: LeadStatus) => void;
  onDragEnd: () => void;
  isDragging: boolean;
}) {
  const days = daysSince(lead.created_at);
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, lead.id, lead.status)}
      onDragEnd={onDragEnd}
      className={`block bg-white/[0.04] hover:bg-white/[0.07] border border-white/10 hover:border-cyan-500/40 rounded-lg p-3 transition cursor-grab active:cursor-grabbing ${
        isDragging ? "opacity-40" : ""
      }`}
    >
      <Link
        href={`/admin/system/operations/comercial/leads/${lead.id}`}
        // ao clicar abrimos detalhe; arrasto é o mousedown sustentado
        className="block"
        onClick={(e) => {
          // Evita navegar quando o usuário está completando um drag
          if (isDragging) e.preventDefault();
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="text-sm font-medium text-slate-100 leading-tight truncate">
            {lead.full_name || "(sem nome)"}
          </div>
          <span className={`text-xs px-2 py-0.5 rounded font-medium shrink-0 ${scoreBadge(lead.qualification_score)}`}>
            {lead.qualification_score ?? "—"}
          </span>
        </div>
        {lead.organization && (
          <div className="text-xs text-slate-400 mt-1 flex items-center gap-1 truncate">
            <Building2 className="w-3 h-3 shrink-0" />
            <span className="truncate">{lead.organization}</span>
          </div>
        )}
        <div className="text-xs text-slate-500 mt-1 flex items-center gap-1 truncate">
          <Phone className="w-3 h-3 shrink-0" />
          <span className="truncate">{lead.phone}</span>
        </div>
        {lead.demo_scheduled_at && (
          <div className="text-xs text-blue-300 mt-1.5 flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            <span>{brDate(lead.demo_scheduled_at)}</span>
          </div>
        )}
        <div className="text-[11px] text-slate-500 mt-1.5 flex justify-between items-center">
          <span>há {days}d</span>
          <span className="font-mono opacity-70">{lead.intent}</span>
        </div>
      </Link>
    </div>
  );
}

export default function FunilPage() {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(60);

  // Drag state
  const [draggingLeadId, setDraggingLeadId] = useState<string | null>(null);
  const [draggingFromStatus, setDraggingFromStatus] = useState<LeadStatus | null>(null);
  const [hoverColumn, setHoverColumn] = useState<LeadStatus | null>(null);
  const [savingMove, setSavingMove] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await commercialApi.funnelKanban(days);
      setData(d);
    } catch (e: any) {
      setError(e.message || "Falha carregando funil");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && hasRole(user, "super_admin", "admin_tenant", "comercial")) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user, days]);

  // ─── Drag handlers ─────────────────────────────────────────────
  function handleDragStart(
    e: React.DragEvent,
    leadId: string,
    fromStatus: LeadStatus,
  ) {
    setDraggingLeadId(leadId);
    setDraggingFromStatus(fromStatus);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", leadId);
  }

  function handleDragEnd() {
    setDraggingLeadId(null);
    setDraggingFromStatus(null);
    setHoverColumn(null);
  }

  function handleDragOver(e: React.DragEvent, target: LeadStatus) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (hoverColumn !== target) setHoverColumn(target);
  }

  function handleDragLeave(target: LeadStatus) {
    if (hoverColumn === target) setHoverColumn(null);
  }

  async function handleDrop(e: React.DragEvent, target: LeadStatus) {
    e.preventDefault();
    setHoverColumn(null);
    const leadId = e.dataTransfer.getData("text/plain") || draggingLeadId;
    const from = draggingFromStatus;
    if (!leadId || !from || !data) return;
    if (from === target) return;

    // Optimistic update — move card no estado antes de chamar API
    const prev = data;
    const movedLead = prev.columns[from]?.find((l) => l.id === leadId);
    if (!movedLead) return;
    const next: FunnelData = {
      ...prev,
      columns: {
        ...prev.columns,
        [from]: prev.columns[from].filter((l) => l.id !== leadId),
        [target]: [{ ...movedLead, status: target }, ...(prev.columns[target] || [])],
      },
      totals: {
        ...prev.totals,
        [from]: Math.max(0, (prev.totals[from] || 0) - 1),
        [target]: (prev.totals[target] || 0) + 1,
      },
    };
    setData(next);
    setSavingMove(true);
    try {
      await commercialApi.updateLead(leadId, { status: target });
    } catch (err: any) {
      // Rollback se falhar
      setData(prev);
      setError(err.message || "Falha ao mover lead");
    } finally {
      setSavingMove(false);
    }
  }

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
        <p className="text-slate-400 mt-1">super_admin, admin_tenant ou comercial.</p>
      </div>
    );
  }

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">
            Funil Comercial
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {data
              ? `${data.total} leads ativos · arraste cards para mover`
              : "Carregando…"}
            {savingMove && (
              <span className="ml-2 text-cyan-300 inline-flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" />
                salvando…
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5 hover:bg-white/[0.06]"
          >
            <option value={30}>Últimos 30 dias</option>
            <option value={60}>Últimos 60 dias</option>
            <option value={90}>Últimos 90 dias</option>
            <option value={180}>Últimos 180 dias</option>
          </select>
          <button
            onClick={load}
            disabled={loading}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-3 py-1.5 hover:bg-white/[0.07] disabled:opacity-50 flex items-center gap-1.5"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
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
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {COLUMNS.map((col) => {
            const items = data.columns[col.key] || [];
            const isHover = hoverColumn === col.key;
            const isSource = draggingFromStatus === col.key;
            return (
              <div
                key={col.key}
                onDragOver={(e) => handleDragOver(e, col.key)}
                onDragLeave={() => handleDragLeave(col.key)}
                onDrop={(e) => handleDrop(e, col.key)}
                className={`rounded-lg border bg-white/[0.02] p-3 transition ${
                  isHover && !isSource
                    ? "border-cyan-400/60 bg-cyan-500/[0.05] ring-1 ring-cyan-400/40"
                    : "border-white/10"
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-200">
                    {col.label}
                  </h3>
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${col.accent}`}>
                    {items.length}
                  </span>
                </div>
                <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
                  {items.length === 0 ? (
                    <div className="text-xs text-slate-600 text-center py-8 italic">
                      {isHover && !isSource ? "Solte aqui" : "Vazio"}
                    </div>
                  ) : (
                    items.map((lead) => (
                      <LeadCard
                        key={lead.id}
                        lead={lead}
                        onDragStart={handleDragStart}
                        onDragEnd={handleDragEnd}
                        isDragging={draggingLeadId === lead.id}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <footer className="mt-6 pt-4 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span>
          Status `converted` e `lost` ficam fora —{" "}
          <Link
            href="/admin/system/operations/leads"
            className="text-cyan-400 hover:underline"
          >
            ver lista completa
          </Link>
        </span>
        <span className="flex items-center gap-1">
          <TrendingUp className="w-3 h-3" />
          score: ≥80 quente · ≥60 morno · ≥30 frio
        </span>
      </footer>
    </div>
  );
}
