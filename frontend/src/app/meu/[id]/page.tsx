import { Suspense } from "react";

import { PatientPortal } from "@/components/patient-portal/patient-portal";

export const dynamic = "force-dynamic";

// ═══════════════════════════════════════════════════════════════
// /meu/[id] — Portal do paciente (rota PÚBLICA, sem auth CRM)
// Acesso por PIN 6 dígitos enviado via WhatsApp
// Mobile-first
// ═══════════════════════════════════════════════════════════════

export default async function MeuPortalPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
          Carregando…
        </div>
      }
    >
      <PatientPortal teleconsultaId={id} />
    </Suspense>
  );
}
