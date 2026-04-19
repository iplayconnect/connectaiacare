import Link from "next/link";
import Image from "next/image";
import { AlertTriangle, Heart, TrendingUp, Users } from "lucide-react";
import { api } from "@/lib/api";
import { ClassificationBadge } from "@/components/classification-badge";
import { timeAgo, CLASSIFICATION_LABELS } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let summary;
  try {
    summary = await api.dashboardSummary();
  } catch (err) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-amber-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold">API indisponível</h2>
          <p className="text-muted-foreground">Verifique se o backend está rodando na porta 5055.</p>
        </div>
      </div>
    );
  }

  const counts = summary.last_24h_by_classification || {};
  const total24h = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Dashboard Clínico</h1>
        <p className="text-muted-foreground">
          Visão em tempo real da equipe de enfermagem e corpo médico.
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <KPICard
          icon={<Users className="h-5 w-5 text-blue-600" />}
          label="Pacientes ativos"
          value={summary.active_patients}
          hint="monitorados"
        />
        <KPICard
          icon={<TrendingUp className="h-5 w-5 text-indigo-600" />}
          label="Relatos 24h"
          value={total24h}
          hint="análises feitas"
        />
        <KPICard
          icon={<AlertTriangle className="h-5 w-5 text-orange-600" />}
          label="Urgentes 24h"
          value={(counts.urgent || 0) + (counts.critical || 0)}
          hint="requerem atenção"
          highlight={((counts.urgent || 0) + (counts.critical || 0)) > 0}
        />
        <KPICard
          icon={<Heart className="h-5 w-5 text-emerald-600" />}
          label="Rotina 24h"
          value={counts.routine || 0}
          hint="sem intercorrências"
        />
      </div>

      {/* Distribuição */}
      <div className="bg-white rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-4">Distribuição de classificações (últimas 24h)</h2>
        <div className="grid grid-cols-4 gap-3">
          {(["routine", "attention", "urgent", "critical"] as const).map((c) => (
            <div key={c} className="flex items-center gap-3 p-3 rounded-lg bg-slate-50 border">
              <ClassificationBadge classification={c} />
              <span className="text-2xl font-bold">{counts[c] || 0}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Relatos recentes */}
      <div className="bg-white rounded-lg border">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">Relatos recentes</h2>
          <p className="text-sm text-muted-foreground">Últimas observações registradas pelos cuidadores</p>
        </div>
        <ul className="divide-y">
          {summary.recent_reports.length === 0 ? (
            <li className="p-10 text-center text-muted-foreground">
              Nenhum relato ainda. Envie um áudio pelo WhatsApp para começar.
            </li>
          ) : (
            summary.recent_reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-center gap-4 p-4 hover:bg-slate-50 transition"
                >
                  {r.patient_photo ? (
                    <Image
                      src={r.patient_photo}
                      alt={r.patient_name || ""}
                      width={48}
                      height={48}
                      className="rounded-full object-cover w-12 h-12"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-slate-200 flex items-center justify-center">
                      <Users className="h-5 w-5 text-slate-500" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold truncate">{r.patient_name || "Paciente não identificado"}</h3>
                      {r.patient_room && (
                        <span className="text-xs text-muted-foreground">Quarto {r.patient_room}</span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {r.analysis?.summary || r.transcription?.slice(0, 120) || "Aguardando análise…"}
                    </p>
                  </div>
                  <div className="text-right flex flex-col items-end gap-1">
                    <ClassificationBadge classification={r.classification} />
                    <span className="text-xs text-muted-foreground">{timeAgo(r.received_at)}</span>
                  </div>
                </Link>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

function KPICard({
  icon,
  label,
  value,
  hint,
  highlight = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  hint: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`bg-white rounded-lg border p-4 ${
        highlight ? "ring-2 ring-orange-400 bg-orange-50" : ""
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-muted-foreground">{label}</span>
      </div>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-xs text-muted-foreground">{hint}</div>
    </div>
  );
}
