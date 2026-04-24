import { HeartPulse } from "lucide-react";

import { PatientsList } from "@/components/patients/patients-list";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

// ═══════════════════════════════════════════════════════════════
// /patients — lista com filtros + busca
// SSR carrega inicial; <PatientsList/> (client) filtra reativamente
// ═══════════════════════════════════════════════════════════════

export default async function PatientsPage() {
  const { patients } = await api.listPatients();

  return (
    <div className="space-y-6 max-w-[1400px] animate-fade-up">
      <header>
        <div className="flex items-center gap-2 mb-2">
          <HeartPulse className="h-4 w-4 text-accent-teal" />
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Monitorados
          </span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="accent-gradient-text">Pacientes</span>
        </h1>
        <p className="text-muted-foreground mt-1">
          <span className="tabular font-medium text-foreground">{patients.length}</span>{" "}
          {patients.length === 1
            ? "idoso em acompanhamento ativo"
            : "idosos em acompanhamento ativo"}
          .
        </p>
      </header>

      <PatientsList patients={patients} />
    </div>
  );
}
