"use client";

import { useCallback, useEffect, useState } from "react";
import {
  MessageSquare,
  Search,
  RefreshCw,
  Loader2,
  Clock,
  Phone,
  ChevronRight,
  Hash,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

interface RecentItem {
  phone_or_redacted: string;
  tenant_id: string | null;
  last_at: string;
  events: number;
  last_sub_agent: string | null;
  last_intent: string | null;
}

interface AuditEvent {
  action: string;
  payload: any;
  actor: string | null;
  tenant_id: string | null;
  trace_id: string | null;
  session_id: string | null;
  resource_type: string | null;
  resource_id: string | null;
  at: string;
}

export default function ConversationsPage() {
  const { user } = useAuth();
  const allowed = hasRole(user, "super_admin", "admin_tenant");

  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [searchPhone, setSearchPhone] = useState("");
  const [searchTrace, setSearchTrace] = useState("");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [activeQuery, setActiveQuery] = useState<{ type: "phone" | "trace"; value: string } | null>(null);

  const loadRecent = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.request<{ items: RecentItem[] }>(
        "/api/admin/conversations/recent?days=7&limit=50",
      );
      setRecent(r.items || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) loadRecent();
  }, [allowed, loadRecent]);

  const searchByPhone = async (phone: string) => {
    setSearching(true);
    setActiveQuery({ type: "phone", value: phone });
    try {
      const r = await api.request<{ events: AuditEvent[] }>(
        `/api/admin/conversations/by-phone/${encodeURIComponent(phone)}?days=14`,
      );
      setEvents(r.events || []);
    } finally {
      setSearching(false);
    }
  };

  const searchByTrace = async () => {
    if (!searchTrace.trim()) return;
    setSearching(true);
    setActiveQuery({ type: "trace", value: searchTrace.trim() });
    try {
      const r = await api.request<{ events: AuditEvent[] }>(
        `/api/admin/conversations/by-trace/${encodeURIComponent(searchTrace.trim())}`,
      );
      setEvents(r.events || []);
    } finally {
      setSearching(false);
    }
  };

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
            <MessageSquare className="h-6 w-6 text-accent-cyan" />
            Conversas · Replay
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Reconstrói conversação Sofia a partir do audit log. Busca
            por phone (todos os eventos do número) ou trace_id (1
            evento webhook completo).
          </p>
        </div>
        <button
          onClick={loadRecent}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
        >
          <RefreshCw className="h-4 w-4" />
          Recarregar recentes
        </button>
      </header>

      {/* Search bars */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="flex items-center gap-2 px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg">
          <Phone className="h-4 w-4 text-muted-foreground" />
          <input
            value={searchPhone}
            onChange={(e) => setSearchPhone(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && searchPhone.trim())
                searchByPhone(searchPhone.trim());
            }}
            placeholder="busca por phone (E.164 ou parcial)"
            className="bg-transparent outline-none text-sm flex-1"
          />
          <button
            onClick={() => searchByPhone(searchPhone.trim())}
            disabled={!searchPhone.trim() || searching}
            className="text-xs px-2 py-1 rounded bg-white/[0.05] hover:bg-white/[0.08] disabled:opacity-50"
          >
            buscar
          </button>
        </div>
        <div className="flex items-center gap-2 px-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg">
          <Hash className="h-4 w-4 text-muted-foreground" />
          <input
            value={searchTrace}
            onChange={(e) => setSearchTrace(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") searchByTrace();
            }}
            placeholder="trace_id (UUID)"
            className="bg-transparent outline-none text-sm flex-1 font-mono"
          />
          <button
            onClick={searchByTrace}
            disabled={!searchTrace.trim() || searching}
            className="text-xs px-2 py-1 rounded bg-white/[0.05] hover:bg-white/[0.08] disabled:opacity-50"
          >
            buscar
          </button>
        </div>
      </div>

      {/* Search results */}
      {activeQuery && (
        <div className="rounded-xl border border-white/10 overflow-hidden">
          <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
            <div className="text-sm font-semibold">
              Eventos · {activeQuery.type} = {activeQuery.value}
            </div>
            <button
              onClick={() => {
                setActiveQuery(null);
                setEvents([]);
              }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Limpar
            </button>
          </div>
          {searching ? (
            <div className="p-8 text-center">
              <Loader2 className="h-6 w-6 animate-spin mx-auto" />
            </div>
          ) : events.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              Nenhum evento encontrado.
            </div>
          ) : (
            <ul className="divide-y divide-white/[0.04]">
              {events.map((e, i) => (
                <li key={i} className="px-4 py-3 text-sm">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.05]">
                      {e.action}
                    </span>
                    {e.actor && (
                      <span className="text-xs text-muted-foreground">
                        {e.actor}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground ml-auto font-mono">
                      {e.at?.slice(0, 19).replace("T", " ")}
                    </span>
                  </div>
                  {e.payload && Object.keys(e.payload).length > 0 && (
                    <pre className="mt-2 text-[11px] text-foreground/70 bg-black/20 rounded p-2 overflow-x-auto">
                      {JSON.stringify(e.payload, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Recent activity */}
      <div className="rounded-xl border border-white/10 overflow-hidden">
        <div className="px-4 py-3 border-b border-white/[0.06] text-sm font-semibold">
          Phones com atividade recente (últimos 7d)
        </div>
        {loading ? (
          <div className="p-8 text-center">
            <Loader2 className="h-6 w-6 animate-spin mx-auto" />
          </div>
        ) : recent.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Nenhuma atividade recente.
          </div>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {recent.map((r, i) => (
              <li
                key={i}
                onClick={() => searchByPhone(r.phone_or_redacted)}
                className="px-4 py-3 hover:bg-white/[0.02] cursor-pointer flex items-center gap-3"
              >
                <Phone className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm">{r.phone_or_redacted}</div>
                  <div className="text-xs text-muted-foreground flex gap-3">
                    {r.last_sub_agent && (
                      <span>agent: {r.last_sub_agent}</span>
                    )}
                    {r.last_intent && <span>intent: {r.last_intent}</span>}
                    <span>{r.events} eventos</span>
                  </div>
                </div>
                <span className="text-xs text-muted-foreground">
                  {timeAgo(r.last_at)}
                </span>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
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
