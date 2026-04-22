import { FileText } from "lucide-react";

import { ReportsFilters } from "@/components/reports-filters";
import { ReportsListLive } from "@/components/reports-list-live";
import { type Report } from "@/lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

// ═══════════════════════════════════════════════════════════════
// Lista de Relatos com filtros via URL params
// Server component faz o fetch baseado nos searchParams
// Client (ReportsFilters) atualiza URL e React Server re-renderiza
// ═══════════════════════════════════════════════════════════════

type SearchParams = {
  search?: string;
  classification?: string;
  days?: string;
  patient_id?: string;
  caregiver_phone?: string;
};

async function fetchFiltered(searchParams: SearchParams) {
  const params = new URLSearchParams();
  params.set("limit", "200");
  if (searchParams.search) params.set("search", searchParams.search);
  if (searchParams.classification)
    params.set("classification", searchParams.classification);
  if (searchParams.days) params.set("days", searchParams.days);
  if (searchParams.patient_id) params.set("patient_id", searchParams.patient_id);
  if (searchParams.caregiver_phone)
    params.set("caregiver_phone", searchParams.caregiver_phone);

  try {
    const res = await fetch(`${API_BASE}/api/reports?${params.toString()}`, {
      cache: "no-store",
    });
    if (!res.ok) return { reports: [] as Report[], total: 0 };
    const data = await res.json();
    return {
      reports: (data.reports || []) as Report[],
      total: data.total_returned || 0,
    };
  } catch {
    return { reports: [] as Report[], total: 0 };
  }
}

export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const { reports } = await fetchFiltered(params);

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Hero */}
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Histórico · Cuidador → Íris → Equipe
            </span>
          </div>
          <h1 className="text-[2rem] md:text-[2.25rem] font-bold tracking-tight leading-[1.15]">
            <span className="accent-gradient-text">Relatos</span> registrados
          </h1>
          <p className="text-muted-foreground mt-2 text-sm max-w-2xl">
            Cada relato passou por transcrição Deepgram, análise clínica da Íris e classificação.
            Use os filtros para encontrar rapidamente observações por classificação, período ou texto.
          </p>
        </div>
      </div>

      {/* Barra de filtros */}
      <ReportsFilters totalFiltered={reports.length} />

      {/* Lista client-side (reage a searchParams em tempo real) */}
      <ReportsListLive initialReports={reports} />
    </div>
  );
}
