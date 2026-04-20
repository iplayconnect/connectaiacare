import Image from "next/image";
import Link from "next/link";
import { HeartPulse, Users } from "lucide-react";

import { api } from "@/lib/api";
import { calcAge } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function PatientsPage() {
  const { patients } = await api.listPatients();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
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
            {patients.length === 1 ? "idoso em acompanhamento ativo" : "idosos em acompanhamento ativo"}.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {patients.map((p) => {
          const age = calcAge(p.birth_date);
          const conditions = (p.conditions || []).slice(0, 2);
          return (
            <Link
              key={p.id}
              href={`/patients/${p.id}`}
              className="glass-card rounded-2xl p-5 flex items-start gap-4 group"
            >
              {p.photo_url ? (
                <Image
                  src={p.photo_url}
                  alt={p.full_name}
                  width={64}
                  height={64}
                  className="rounded-full object-cover w-16 h-16 ring-1 ring-white/10 flex-shrink-0"
                />
              ) : (
                <div className="w-16 h-16 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center flex-shrink-0">
                  <Users className="h-7 w-7 text-muted-foreground" />
                </div>
              )}

              <div className="flex-1 min-w-0">
                <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
                  {p.full_name}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {age && (
                    <span className="tabular font-medium text-foreground/80">{age} anos</span>
                  )}
                  {p.room_number && (
                    <>
                      <span className="mx-1.5 opacity-40">·</span>
                      <span className="uppercase tracking-wider text-[10px]">Quarto {p.room_number}</span>
                    </>
                  )}
                </p>

                {conditions.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {conditions.map((c, i) => (
                      <span
                        key={i}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-accent-teal/10 border border-accent-teal/20 text-accent-teal font-medium"
                      >
                        {c.description}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
