"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { FileText, Users, Loader2 } from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import type { Report } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════
// Lista de relatos client-side — reage a searchParams em tempo real
// Evita o quirk do Next 14 de Server Components não re-executarem
// quando só searchParams mudam.
// ═══════════════════════════════════════════════════════════════

export function ReportsListLive({
  initialReports,
}: {
  initialReports: Report[];
}) {
  const searchParams = useSearchParams();
  const [reports, setReports] = useState<Report[]>(initialReports);
  const [loading, setLoading] = useState(false);

  const search = searchParams.get("search") || "";
  const classification = searchParams.get("classification") || "";
  const days = searchParams.get("days") || "30";

  useEffect(() => {
    let mounted = true;
    setLoading(true);

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
    const params = new URLSearchParams();
    params.set("limit", "200");
    if (search) params.set("search", search);
    if (classification) params.set("classification", classification);
    if (days) params.set("days", days);

    async function load() {
      try {
        const res = await fetch(`${apiBase}/api/reports?${params.toString()}`, {
          cache: "no-store",
        });
        if (!mounted || !res.ok) return;
        const data = await res.json();
        setReports(data.reports || []);
      } catch {
        // silencioso — mantém última lista carregada
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [search, classification, days]);

  const hasFilters = !!search || !!classification || days !== "30";

  return (
    <div className="glass-card rounded-xl overflow-hidden relative">
      {loading && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-accent-cyan to-transparent animate-pulse-soft z-10" />
      )}

      <ul className="divide-y divide-white/[0.04]">
        {reports.length === 0 && !loading ? (
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
        ) : reports.length === 0 && loading ? (
          <li className="p-12 text-center">
            <Loader2 className="h-5 w-5 mx-auto animate-spin text-muted-foreground" />
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
  );
}
