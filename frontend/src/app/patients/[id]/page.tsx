import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { ClassificationBadge } from "@/components/classification-badge";
import { calcAge, timeAgo } from "@/lib/utils";
import { ArrowLeft, Pill, User, AlertTriangle, Phone } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function PatientDetailPage({ params }: { params: { id: string } }) {
  let data;
  try {
    data = await api.getPatient(params.id);
  } catch {
    notFound();
  }

  const { patient, reports } = data;
  const age = calcAge(patient.birth_date);

  return (
    <div className="space-y-6 max-w-5xl">
      <Link href="/patients" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ArrowLeft className="h-4 w-4" /> Voltar aos pacientes
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg border p-6 flex items-start gap-5">
        {patient.photo_url ? (
          <Image
            src={patient.photo_url}
            alt={patient.full_name}
            width={96}
            height={96}
            className="rounded-full object-cover w-24 h-24"
          />
        ) : (
          <div className="w-24 h-24 rounded-full bg-slate-200 flex items-center justify-center">
            <User className="h-10 w-10 text-slate-500" />
          </div>
        )}
        <div className="flex-1">
          <h1 className="text-3xl font-bold">{patient.full_name}</h1>
          {patient.nickname && <p className="text-slate-500">Conhecido(a) como {patient.nickname}</p>}
          <p className="text-muted-foreground mt-1">
            {age && `${age} anos`}
            {patient.gender && ` · ${patient.gender === "F" ? "Feminino" : patient.gender === "M" ? "Masculino" : "Outro"}`}
            {patient.room_number && ` · Quarto ${patient.room_number}`}
            {patient.care_unit && ` · ${patient.care_unit}`}
          </p>
          {patient.care_level && (
            <span className="inline-block mt-2 px-2 py-0.5 text-xs rounded-full bg-indigo-100 text-indigo-800">
              {patient.care_level}
            </span>
          )}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Condições */}
        <div className="bg-white rounded-lg border p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-3">
            <AlertTriangle className="h-5 w-5 text-amber-600" /> Condições clínicas
          </h2>
          <ul className="space-y-2">
            {(patient.conditions || []).map((c, i) => (
              <li key={i} className="text-sm">
                <span className="font-medium">{c.description}</span>
                {c.code && <span className="text-muted-foreground text-xs"> ({c.code})</span>}
                {c.severity && (
                  <span className="ml-2 px-2 py-0.5 text-xs rounded bg-slate-100 text-slate-700">
                    {c.severity}
                  </span>
                )}
              </li>
            ))}
            {(patient.conditions || []).length === 0 && (
              <li className="text-sm text-muted-foreground">Nenhuma condição registrada</li>
            )}
          </ul>

          {patient.allergies && patient.allergies.length > 0 && (
            <div className="mt-4 pt-4 border-t">
              <h3 className="text-sm font-semibold mb-2">Alergias</h3>
              <div className="flex flex-wrap gap-1">
                {patient.allergies.map((a) => (
                  <span key={a} className="px-2 py-0.5 text-xs rounded-full bg-red-50 text-red-700 border border-red-200">
                    {a}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Medicações */}
        <div className="bg-white rounded-lg border p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-3">
            <Pill className="h-5 w-5 text-indigo-600" /> Medicações em uso
          </h2>
          <ul className="space-y-2">
            {(patient.medications || []).map((m, i) => (
              <li key={i} className="text-sm">
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-muted-foreground">{m.schedule} · {m.dose || ""}</div>
              </li>
            ))}
            {(patient.medications || []).length === 0 && (
              <li className="text-sm text-muted-foreground">Nenhuma medicação registrada</li>
            )}
          </ul>
        </div>
      </div>

      {/* Responsável */}
      {patient.responsible?.name && (
        <div className="bg-white rounded-lg border p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-3">
            <Phone className="h-5 w-5 text-teal-600" /> Responsável
          </h2>
          <p>
            <span className="font-medium">{patient.responsible.name}</span>
            {patient.responsible.relationship && <span className="text-muted-foreground"> · {patient.responsible.relationship}</span>}
          </p>
          {patient.responsible.phone && (
            <p className="text-sm text-muted-foreground mt-1">{patient.responsible.phone}</p>
          )}
        </div>
      )}

      {/* Histórico de relatos */}
      <div className="bg-white rounded-lg border">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">Histórico de relatos</h2>
          <p className="text-sm text-muted-foreground">{reports.length} registros</p>
        </div>
        <ul className="divide-y">
          {reports.length === 0 ? (
            <li className="p-10 text-center text-muted-foreground">Nenhum relato ainda para este paciente.</li>
          ) : (
            reports.map((r) => (
              <li key={r.id}>
                <Link href={`/reports/${r.id}`} className="flex items-center justify-between p-4 hover:bg-slate-50">
                  <div className="flex-1 min-w-0 mr-4">
                    <p className="text-sm font-medium truncate">
                      {r.analysis?.summary || r.transcription?.slice(0, 100) || "Processando…"}
                    </p>
                    <p className="text-xs text-muted-foreground">{timeAgo(r.received_at)}</p>
                  </div>
                  <ClassificationBadge classification={r.classification} />
                </Link>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
