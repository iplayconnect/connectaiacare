import Link from "next/link";
import Image from "next/image";
import { api } from "@/lib/api";
import { calcAge } from "@/lib/utils";
import { User } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function PatientsPage() {
  const { patients } = await api.listPatients();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Pacientes</h1>
        <p className="text-muted-foreground">
          {patients.length} idoso{patients.length !== 1 ? "s" : ""} em monitoramento ativo.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {patients.map((p) => {
          const age = calcAge(p.birth_date);
          return (
            <Link
              key={p.id}
              href={`/patients/${p.id}`}
              className="bg-white rounded-lg border p-4 hover:shadow-md transition flex items-center gap-4"
            >
              {p.photo_url ? (
                <Image
                  src={p.photo_url}
                  alt={p.full_name}
                  width={56}
                  height={56}
                  className="rounded-full object-cover w-14 h-14"
                />
              ) : (
                <div className="w-14 h-14 rounded-full bg-slate-200 flex items-center justify-center">
                  <User className="h-6 w-6 text-slate-500" />
                </div>
              )}
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold truncate">{p.full_name}</h3>
                <p className="text-sm text-muted-foreground">
                  {age && `${age} anos`}
                  {p.room_number && ` · Quarto ${p.room_number}`}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {(p.conditions || []).slice(0, 2).map((c) => c.description).join(" · ") || "Sem condições registradas"}
                </p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
