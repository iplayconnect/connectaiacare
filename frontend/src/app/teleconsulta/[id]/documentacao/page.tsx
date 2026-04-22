import { Suspense } from "react";

import { TeleconsultaDocumentation } from "@/components/teleconsulta/teleconsulta-documentation";

export const dynamic = "force-dynamic";

// ═══════════════════════════════════════════════════════════════
// Rota /teleconsulta/[id]/documentacao — tela de pós-consulta
// 1. Cola/edita a transcrição
// 2. Gera SOAP via Claude Opus
// 3. Edita SOAP (4 seções)
// 4. Adiciona prescrições com validação Beers+interações
// 5. Assina + gera FHIR Bundle + sync TotalCare
// ═══════════════════════════════════════════════════════════════

export default async function DocumentacaoPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <Suspense
      fallback={
        <div className="p-12 text-sm text-muted-foreground">
          Carregando documentação…
        </div>
      }
    >
      <TeleconsultaDocumentation teleconsultaId={id} />
    </Suspense>
  );
}
