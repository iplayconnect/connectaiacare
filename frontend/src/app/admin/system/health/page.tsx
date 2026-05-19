"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  AlertCircle,
  XCircle,
  RefreshCw,
  Database,
  Zap,
  PhoneCall,
  Brain,
  Stethoscope,
  Clock,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api } from "@/lib/api";

interface ServiceCheck {
  status: "ok" | "degraded" | "down";
  latency_ms?: number;
  http_status?: number;
  detail?: string | object | null;
  synced_24h?: number;
  errors_24h?: number;
  quota_alerts_1h?: number;
}

interface HealthResponse {
  status: "ok" | "degraded" | "down";
  checked_at: number;
  total_elapsed_ms: number;
  services: Record<string, ServiceCheck>;
}

const SERVICE_META: Record<string, { label: string; icon: React.ElementType }> = {
  postgres: { label: "PostgreSQL", icon: Database },
  redis: { label: "Redis", icon: Zap },
  voice_call: { label: "Voice Call Service", icon: PhoneCall },
  sofia_service: { label: "Sofia Service", icon: Brain },
  tecnosenior_local: { label: "Parceiro CareNote Sync (24h)", icon: Stethoscope },
  voice_provider_quota: { label: "xAI Voice Quota", icon: Activity },
};

const REFRESH_MS = 15_000;

export default function HealthPage() {
  const { user } = useAuth();
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number | null>(null);

  const allowed = hasRole(user, "super_admin", "admin_tenant");

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.request<HealthResponse>("/api/admin/health");
      setData(res);
      setLastFetch(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro carregando saúde");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!allowed) return;
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center text-muted-foreground">
        Sem permissão para acessar saúde do sistema.
      </div>
    );
  }

  const overallTone =
    data?.status === "ok"
      ? "text-classification-routine"
      : data?.status === "degraded"
      ? "text-classification-attention"
      : "text-classification-critical";

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-6 space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className={`h-6 w-6 ${overallTone}`} />
            Saúde do Sistema
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Estado agregado dos serviços críticos. Atualiza a cada 15s.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastFetch && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {new Date(lastFetch).toLocaleTimeString("pt-BR")}
            </span>
          )}
          <button
            onClick={load}
            className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Atualizar
          </button>
        </div>
      </header>

      {/* Overall status banner */}
      {data && (
        <div
          className={`rounded-xl border p-4 flex items-start gap-3 ${
            data.status === "ok"
              ? "border-classification-routine/30 bg-classification-routine/5"
              : data.status === "degraded"
              ? "border-classification-attention/30 bg-classification-attention/5"
              : "border-classification-critical/30 bg-classification-critical/10"
          }`}
        >
          <StatusIcon status={data.status} className="h-5 w-5 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold capitalize">
              Sistema {data.status === "ok" ? "operacional" : data.status === "degraded" ? "degradado" : "fora do ar"}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Verificação completou em {data.total_elapsed_ms}ms
            </div>
          </div>
        </div>
      )}

      {/* Cards por serviço */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {data &&
          Object.entries(data.services).map(([name, check]) => {
            const meta = SERVICE_META[name] || { label: name, icon: Activity };
            const Icon = meta.icon;
            return (
              <div
                key={name}
                className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{meta.label}</span>
                  </div>
                  <StatusIcon status={check.status} className="h-4 w-4" />
                </div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-muted-foreground">Latência</span>
                  <span className="tabular font-medium">
                    {check.latency_ms ?? "—"}ms
                  </span>
                </div>
                {typeof check.synced_24h === "number" && (
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="text-muted-foreground">Synced 24h</span>
                    <span className="tabular font-medium">{check.synced_24h}</span>
                  </div>
                )}
                {typeof check.errors_24h === "number" && check.errors_24h > 0 && (
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="text-classification-attention">Erros 24h</span>
                    <span className="tabular font-medium text-classification-attention">
                      {check.errors_24h}
                    </span>
                  </div>
                )}
                {typeof check.quota_alerts_1h === "number" && (
                  <div className="flex items-baseline justify-between text-xs">
                    <span className={check.quota_alerts_1h > 0 ? "text-classification-critical" : "text-muted-foreground"}>
                      Quota alerts 1h
                    </span>
                    <span className="tabular font-medium">{check.quota_alerts_1h}</span>
                  </div>
                )}
                {check.detail && typeof check.detail === "string" && (
                  <div className="text-xs text-muted-foreground border-t border-white/[0.06] pt-2">
                    {check.detail}
                  </div>
                )}
              </div>
            );
          })}
      </div>

      {loading && !data && (
        <div className="text-center py-12 text-muted-foreground">
          <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
          Carregando...
        </div>
      )}

      {error && (
        <div className="rounded-md border border-classification-urgent/40 bg-classification-urgent/10 p-3 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}

function StatusIcon({
  status,
  className = "",
}: {
  status: "ok" | "degraded" | "down";
  className?: string;
}) {
  if (status === "ok")
    return <CheckCircle2 className={`text-classification-routine ${className}`} />;
  if (status === "degraded")
    return <AlertCircle className={`text-classification-attention ${className}`} />;
  return <XCircle className={`text-classification-critical ${className}`} />;
}
