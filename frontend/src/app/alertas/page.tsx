import { AlertsPanel } from "@/components/alerts/alerts-panel";
import { getAlerts } from "@/hooks/use-alerts";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// ═══════════════════════════════════════════════════════════════
// /alertas — Painel de triagem de alertas (DEC-005)
//
// Opus Design handoff: AlertsPanel.jsx + AlertsPanelMocks.jsx
// Traduzido pra TSX moderno (hooks + types + tailwind tokens).
// ═══════════════════════════════════════════════════════════════

export default async function AlertasPage() {
  const alerts = await getAlerts();
  return (
    <div className="max-w-[1400px] mx-auto">
      <AlertsPanel initialAlerts={alerts} />
    </div>
  );
}
