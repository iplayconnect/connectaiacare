"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  Users,
  Activity,
  AlertTriangle,
  Loader2,
  RefreshCw,
  ChevronRight,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

interface DashboardData {
  totals: {
    tenants_total: number;
    tenants_active: number;
    tenants_suspended: number;
    patients_total: number;
    users_total: number;
    caregivers_total: number;
    care_events_24h: number;
    care_events_open: number;
  };
  series_7d: { day: string; classification: string; n: number }[];
  top_open_tenants: {
    tenant_id: string;
    tenant_name: string;
    open_count: number;
  }[];
  classification_30d: { classification: string; n: number }[];
}

const CLASS_COLOR: Record<string, string> = {
  routine: "#34d399",
  attention: "#fbbf24",
  urgent: "#fb923c",
  critical: "#ef4444",
};

export default function SystemDashboardPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const allowed = hasRole(user, "super_admin");

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.request<{ status: string } & DashboardData>(
        "/api/system/dashboard",
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro carregando dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Apenas super_admin pode acessar o painel cross-tenant.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="text-center py-16">
        <Loader2 className="h-6 w-6 animate-spin mx-auto" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        {error || "Sem dados."}
      </div>
    );
  }

  const t = data.totals;

  // Agrupa série 7d em dias × classification, prepara matriz
  const days = Array.from(new Set(data.series_7d.map((s) => s.day))).sort();
  const classes = Array.from(
    new Set(data.series_7d.map((s) => s.classification)),
  );
  const seriesMaxN = Math.max(1, ...data.series_7d.map((s) => s.n));

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Building2 className="h-6 w-6 text-accent-cyan" />
            Sistema · Cross-tenant
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Visão agregada de todos os tenants ativos. Use para identificar
            tenants com volume anômalo de eventos abertos ou queda de
            atividade.
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

      {/* Totais */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Tenants ativos" value={t.tenants_active} hint={`${t.tenants_suspended} suspenso(s)`} icon={Building2} />
        <Stat label="Pacientes" value={t.patients_total} icon={Users} />
        <Stat label="Usuários" value={t.users_total} hint={`${t.caregivers_total} cuidadores`} icon={Users} />
        <Stat
          label="Eventos abertos"
          value={t.care_events_open}
          hint={`${t.care_events_24h} nas últimas 24h`}
          icon={AlertTriangle}
          tone="urgent"
        />
      </div>

      {/* Série 7d */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
        <h2 className="text-sm font-semibold flex items-center gap-2 mb-4">
          <Activity className="h-4 w-4 text-accent-cyan" />
          Eventos clínicos · últimos 7 dias
        </h2>
        {days.length === 0 ? (
          <div className="text-xs text-muted-foreground py-6 text-center">
            Nenhum evento registrado nos últimos 7 dias.
          </div>
        ) : (
          <div className="space-y-3">
            {days.map((day) => {
              const dayItems = data.series_7d.filter((s) => s.day === day);
              const dayTotal = dayItems.reduce((sum, i) => sum + i.n, 0);
              return (
                <div key={day} className="flex items-center gap-3">
                  <div className="w-20 text-xs text-muted-foreground tabular">
                    {new Date(day).toLocaleDateString("pt-BR", {
                      day: "2-digit",
                      month: "short",
                    })}
                  </div>
                  <div className="flex-1 h-6 rounded-md bg-white/[0.03] overflow-hidden flex">
                    {classes.map((cls) => {
                      const item = dayItems.find((i) => i.classification === cls);
                      const n = item?.n ?? 0;
                      if (!n) return null;
                      const pct = (n / seriesMaxN) * 100;
                      return (
                        <div
                          key={cls}
                          title={`${cls}: ${n}`}
                          className="h-full"
                          style={{
                            width: `${pct}%`,
                            background: CLASS_COLOR[cls] || "#94a3b8",
                            opacity: 0.8,
                          }}
                        />
                      );
                    })}
                  </div>
                  <div className="w-12 text-xs tabular text-right">{dayTotal}</div>
                </div>
              );
            })}
          </div>
        )}
        <div className="flex gap-3 mt-4 text-xs flex-wrap">
          {classes.map((cls) => (
            <div key={cls} className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-sm"
                style={{ background: CLASS_COLOR[cls] || "#94a3b8" }}
              />
              <span className="capitalize text-muted-foreground">{cls}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top tenants por eventos abertos */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <h2 className="text-sm font-semibold mb-3">
            Top tenants · eventos abertos
          </h2>
          {data.top_open_tenants.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center">
              Sem dados.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {data.top_open_tenants.map((tn) => (
                <li key={tn.tenant_id}>
                  <Link
                    href={`/admin/system/tenants/${tn.tenant_id}`}
                    className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.03] transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-sm truncate">{tn.tenant_name}</div>
                      <div className="text-xs text-muted-foreground font-mono truncate">
                        {tn.tenant_id}
                      </div>
                    </div>
                    <div className="text-sm tabular font-semibold">
                      {tn.open_count}
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Distribuição classification 30d */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
          <h2 className="text-sm font-semibold mb-3">
            Distribuição · últimos 30 dias
          </h2>
          {data.classification_30d.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center">
              Sem dados.
            </div>
          ) : (
            <div className="space-y-2">
              {(() => {
                const total = data.classification_30d.reduce(
                  (sum, c) => sum + c.n,
                  0,
                );
                return data.classification_30d.map((c) => {
                  const pct = total ? (c.n / total) * 100 : 0;
                  return (
                    <div key={c.classification}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="capitalize">{c.classification}</span>
                        <span className="tabular text-muted-foreground">
                          {c.n} ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="h-2 rounded bg-white/[0.04] overflow-hidden">
                        <div
                          className="h-full"
                          style={{
                            width: `${pct}%`,
                            background:
                              CLASS_COLOR[c.classification] || "#94a3b8",
                          }}
                        />
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <Link
          href="/admin/system/tenants"
          className="px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
        >
          Gerenciar tenants →
        </Link>
      </div>

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  tone?: "urgent";
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon
          className={`h-3.5 w-3.5 ${
            tone === "urgent" ? "text-classification-urgent" : "text-accent-cyan"
          }`}
        />
        {label}
      </div>
      <div className="text-2xl font-bold mt-1 tabular">{value}</div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}
