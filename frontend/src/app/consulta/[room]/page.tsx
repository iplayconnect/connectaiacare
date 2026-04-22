import { Suspense } from "react";

import { ConsultaRoom } from "@/components/consulta-room";

export const dynamic = "force-dynamic";

// ═══════════════════════════════════════════════════════════════
// Rota /consulta/[room] — sala de teleconsulta
// SSR apenas da shell; LiveKit conecta client-side
// ═══════════════════════════════════════════════════════════════

export default async function ConsultaPage({
  params,
  searchParams,
}: {
  params: Promise<{ room: string }>;
  searchParams: Promise<{ token?: string; role?: string }>;
}) {
  const { room } = await params;
  const sp = await searchParams;

  return (
    <Suspense>
      <ConsultaRoom
        roomName={room}
        token={sp.token || ""}
        role={(sp.role as "doctor" | "patient") || "patient"}
      />
    </Suspense>
  );
}
