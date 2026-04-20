import Image from "next/image";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  HeartPulse,
  Sparkles,
  Users,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { api } from "@/lib/api";
import { CLASSIFICATION_LABELS, timeAgo } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let summary;
  try {
    summary = await api.dashboardSummary();
  } catch {
    return (
      <div className="glass-card rounded-2xl p-10 text-center max-w-md mx-auto">
        <AlertTriangle className="h-10 w-10 text-classification-attention mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-1">API indisponível</h2>
        <p className="text-sm text-muted-foreground">
          Verifique se o backend está rodando na porta 5055.
        </p>
      </div>
    );
  }

  const counts = summary.last_24h_by_classification || {};
  const total24h = Object.values(counts).reduce((a, b) => a + b, 0);
  const criticalCount = (counts.urgent || 0) + (counts.critical || 0);

  return (
    <div className="space-y-8">
      {/* Hero / overview */}
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Dashboard Clínico
            </span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
            Visão em <span className="accent-gradient-text">tempo real</span>
          </h1>
          <p className="text-muted-foreground mt-1 max-w-xl">
            Equipe de enfermagem e corpo médico acompanham pacientes com insights
            estruturados de cada relato de cuidador.
          </p>
        </div>

        {criticalCount > 0 && (
          <div className="glass-card rounded-xl px-5 py-4 border-classification-urgent/40 glow-critical">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 bg-classification-critical rounded-full opacity-30 blur animate-pulse-soft" />
                <AlertTriangle className="relative h-5 w-5 text-classification-critical" />
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-classification-urgent">
                  Atenção imediata
                </div>
                <div className="text-sm text-foreground mt-0.5">
                  <span className="tabular font-bold text-lg">{criticalCount}</span>
                  {" "}
                  {criticalCount === 1 ? "alerta pendente" : "alertas pendentes"}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          icon={<Users className="h-5 w-5" />}
          iconBg="bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30"
          label="Pacientes monitorados"
          value={summary.active_patients}
          hint="em acompanhamento ativo"
        />
        <KPICard
          icon={<Activity className="h-5 w-5" />}
          iconBg="bg-accent-teal/10 text-accent-teal border-accent-teal/30"
          label="Relatos · 24h"
          value={total24h}
          hint="análises processadas"
        />
        <KPICard
          icon={<AlertTriangle className="h-5 w-5" />}
          iconBg="bg-classification-urgent/10 text-classification-urgent border-classification-urgent/30"
          label="Urgentes · 24h"
          value={criticalCount}
          hint="requerem atenção"
          highlight={criticalCount > 0}
        />
        <KPICard
          icon={<HeartPulse className="h-5 w-5" />}
          iconBg="bg-classification-routine/10 text-classification-routine border-classification-routine/30"
          label="Rotina · 24h"
          value={counts.routine || 0}
          hint="sem intercorrências"
        />
      </div>

      {/* Classification distribution */}
      <section className="glass-card rounded-2xl p-6 md:p-8">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-semibold">Distribuição de classificações</h2>
            <p className="text-xs text-muted-foreground">Últimas 24 horas</p>
          </div>
          <div className="gradient-divider flex-1 mx-6 hidden md:block" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {(["routine", "attention", "urgent", "critical"] as const).map((c) => {
            const count = counts[c] || 0;
            return (
              <div
                key={c}
                className="solid-card rounded-xl p-4 flex items-center justify-between"
              >
                <div>
                  <div className={`text-xs font-semibold uppercase tracking-wider text-classification-${c} mb-1`}>
                    {CLASSIFICATION_LABELS[c]}
                  </div>
                  <div className="tabular text-3xl font-bold">{count}</div>
                </div>
                <ClassificationBadge classification={c} />
              </div>
            );
          })}
        </div>
      </section>

      {/* Recent reports */}
      <section className="glass-card rounded-2xl overflow-hidden">
        <div className="p-6 border-b border-white/[0.05] flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Relatos recentes</h2>
            <p className="text-xs text-muted-foreground">
              Últimas observações dos cuidadores processadas pela IA
            </p>
          </div>
          <Link
            href="/reports"
            className="text-xs font-medium text-accent-cyan hover:text-accent-teal transition-colors flex items-center gap-1"
          >
            Ver todos <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>

        <ul className="divide-y divide-white/[0.04]">
          {summary.recent_reports.length === 0 ? (
            <li className="p-12 text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.03] border border-white/[0.06] mb-4">
                <HeartPulse className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="font-medium mb-1">Aguardando primeiro relato</h3>
              <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                Envie um áudio pelo WhatsApp para começar. A IA vai identificar
                o paciente e gerar a análise em poucos segundos.
              </p>
            </li>
          ) : (
            summary.recent_reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-center gap-4 p-5 hover:bg-white/[0.02] transition-colors group"
                >
                  {r.patient_photo ? (
                    <div className="relative">
                      <Image
                        src={r.patient_photo}
                        alt={r.patient_name || ""}
                        width={48}
                        height={48}
                        className="rounded-full object-cover w-12 h-12 ring-1 ring-white/10"
                      />
                      {r.classification === "critical" && (
                        <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-classification-critical border-2 border-background animate-pulse-glow" />
                      )}
                    </div>
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
                      <Users className="h-5 w-5 text-muted-foreground" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
                        {r.patient_name || "Paciente não identificado"}
                      </h3>
                      {r.patient_room && (
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                          · quarto {r.patient_room}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {r.analysis?.summary || r.transcription?.slice(0, 140) || "Aguardando análise…"}
                    </p>
                  </div>
                  <div className="text-right flex flex-col items-end gap-1.5">
                    <ClassificationBadge classification={r.classification} />
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {timeAgo(r.received_at)}
                    </span>
                  </div>
                </Link>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}

function KPICard({
  icon,
  iconBg,
  label,
  value,
  hint,
  highlight = false,
}: {
  icon: React.ReactNode;
  iconBg: string;
  label: string;
  value: number;
  hint: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`glass-card rounded-xl p-5 ${
        highlight ? "border-classification-urgent/40 glow-critical" : ""
      }`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 rounded-lg border ${iconBg}`}>{icon}</div>
        {highlight && (
          <span className="text-[10px] uppercase tracking-wider font-semibold text-classification-urgent animate-pulse-soft">
            • atenção
          </span>
        )}
      </div>
      <div className="tabular text-3xl font-bold leading-none mb-1">{value}</div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</div>
    </div>
  );
}
