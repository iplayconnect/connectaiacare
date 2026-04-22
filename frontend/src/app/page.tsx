import { AlertTriangle } from "lucide-react";

import { DashboardLive } from "@/components/dashboard-live";
import { api, type CareEventSummary } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// ═══════════════════════════════════════════════════════════════
// Dashboard — SSR pega estado inicial rápido; DashboardLive
// (client) faz polling a cada 5s atualizando KPIs, charts e feed.
// ═══════════════════════════════════════════════════════════════

export default async function DashboardPage() {
  let events: CareEventSummary[] = [];
  let patientsCount = 0;
  let apiError = false;
  try {
    events = await api.listActiveEvents();
    try {
      const resp = await api.listPatients();
      patientsCount = (resp.patients || []).filter((p) => p.active).length;
    } catch {
      patientsCount = 0;
    }
  } catch {
    apiError = true;
  }

  if (apiError) {
    return (
      <div className="glass-card rounded-2xl p-10 text-center max-w-md mx-auto mt-12">
        <AlertTriangle className="h-10 w-10 text-classification-attention mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-1">API indisponível</h2>
        <p className="text-sm text-muted-foreground">
          Verifique se o backend está rodando em demo.connectaia.com.br.
        </p>
      </div>
    );
  }

  return <DashboardLive initialEvents={events} patientsCount={patientsCount} />;
}
