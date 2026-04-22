import Image from "next/image";
import Link from "next/link";
import { FileText, Users } from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { ReportsFilters } from "@/components/reports-filters";
import { type Report } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

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

  const hasFilters =
    !!params.search ||
    !!params.classification ||
    (!!params.days && params.days !== "30");

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

      {/* Lista */}
      <div className="glass-card rounded-xl overflow-hidden">
        <ul className="divide-y divide-white/[0.04]">
          {reports.length === 0 ? (
            <li className="p-12 text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.03] border border-white/[0.06] mb-4">
                <FileText className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="font-medium mb-1">
                {hasFilters
                  ? "Nenhum relato encontrado com estes filtros"
                  : "Nenhum relato ainda"}
              </h3>
              <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                {hasFilters
                  ? "Tente afrouxar os critérios — limpar filtros ou ampliar o período."
                  : "Envie um áudio pelo WhatsApp para começar."}
              </p>
            </li>
          ) : (
            reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors group"
                >
                  {r.patient_photo ? (
                    <div className="relative flex-shrink-0">
                      <Image
                        src={r.patient_photo}
                        alt={r.patient_name || ""}
                        width={48}
                        height={48}
                        className="rounded-xl object-cover w-12 h-12 ring-1 ring-white/10"
                      />
                      {r.classification === "critical" && (
                        <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-classification-critical border-2 border-background animate-pulse-glow" />
                      )}
                    </div>
                  ) : (
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-accent-cyan/10 to-accent-teal/10 border border-white/[0.05] flex items-center justify-center flex-shrink-0">
                      <Users className="h-5 w-5 text-muted-foreground" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                      <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
                        {r.patient_name || "Paciente não identificado"}
                      </h3>
                      {r.patient_room && (
                        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                          · Q{r.patient_room}
                        </span>
                      )}
                      {r.caregiver_name_claimed && (
                        <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                          · por {r.caregiver_name_claimed}
                        </span>
                      )}
                    </div>
                    <p className="text-[13px] text-foreground/80 line-clamp-2">
                      {r.analysis?.summary ||
                        r.transcription?.slice(0, 180) ||
                        "Processando…"}
                    </p>
                  </div>

                  <div className="text-right flex flex-col items-end gap-1.5 flex-shrink-0">
                    <ClassificationBadge classification={r.classification} compact />
                    <span className="text-[11px] text-muted-foreground tabular">
                      {timeAgo(r.received_at)}
                    </span>
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
