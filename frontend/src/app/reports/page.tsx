import Link from "next/link";
import Image from "next/image";
import { api } from "@/lib/api";
import { ClassificationBadge } from "@/components/classification-badge";
import { timeAgo } from "@/lib/utils";
import { Users } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const { reports } = await api.listReports(100);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Relatos</h1>
        <p className="text-muted-foreground">
          Todas as observações registradas pelos cuidadores.
        </p>
      </div>

      <div className="bg-white rounded-lg border">
        <ul className="divide-y">
          {reports.map((r) => (
            <li key={r.id}>
              <Link
                href={`/reports/${r.id}`}
                className="flex items-center gap-4 p-4 hover:bg-slate-50 transition"
              >
                {r.patient_photo ? (
                  <Image
                    src={r.patient_photo}
                    alt={r.patient_name || ""}
                    width={56}
                    height={56}
                    className="rounded-full object-cover w-14 h-14"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-full bg-slate-200 flex items-center justify-center">
                    <Users className="h-6 w-6 text-slate-500" />
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold truncate">
                      {r.patient_name || "Paciente não identificado"}
                    </h3>
                    {r.patient_room && (
                      <span className="text-xs text-muted-foreground">Quarto {r.patient_room}</span>
                    )}
                    {r.caregiver_name_claimed && (
                      <span className="text-xs text-muted-foreground">
                        · por {r.caregiver_name_claimed}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {r.analysis?.summary || r.transcription?.slice(0, 160) || "Processando…"}
                  </p>
                </div>
                <div className="text-right flex flex-col items-end gap-1">
                  <ClassificationBadge classification={r.classification} />
                  <span className="text-xs text-muted-foreground">{timeAgo(r.received_at)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
