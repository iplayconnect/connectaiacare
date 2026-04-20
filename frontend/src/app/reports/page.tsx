import Image from "next/image";
import Link from "next/link";
import { FileText, Users } from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const { reports } = await api.listReports(100);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Histórico completo
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="accent-gradient-text">Relatos</span> registrados
          </h1>
          <p className="text-muted-foreground mt-1">
            {reports.length} {reports.length === 1 ? "observação registrada" : "observações registradas"}
            {" "}pela equipe de cuidadores.
          </p>
        </div>
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        <ul className="divide-y divide-white/[0.04]">
          {reports.length === 0 ? (
            <li className="p-12 text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/[0.03] border border-white/[0.06] mb-4">
                <FileText className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="font-medium mb-1">Nenhum relato ainda</h3>
              <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                Envie um áudio pelo WhatsApp para começar.
              </p>
            </li>
          ) : (
            reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-center gap-4 p-5 hover:bg-white/[0.02] transition-colors group"
                >
                  {r.patient_photo ? (
                    <div className="relative">
                      <Image
                        src={r.patient_photo}
                        alt={r.patient_name || ""}
                        width={56}
                        height={56}
                        className="rounded-full object-cover w-14 h-14 ring-1 ring-white/10"
                      />
                      {r.classification === "critical" && (
                        <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-classification-critical border-2 border-background animate-pulse-glow" />
                      )}
                    </div>
                  ) : (
                    <div className="w-14 h-14 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
                      <Users className="h-6 w-6 text-muted-foreground" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
                        {r.patient_name || "Paciente não identificado"}
                      </h3>
                      {r.patient_room && (
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                          quarto {r.patient_room}
                        </span>
                      )}
                      {r.caregiver_name_claimed && (
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                          · por {r.caregiver_name_claimed}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {r.analysis?.summary || r.transcription?.slice(0, 180) || "Processando…"}
                    </p>
                  </div>
                  <div className="text-right flex flex-col items-end gap-1.5 flex-shrink-0">
                    <ClassificationBadge classification={r.classification} />
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
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
