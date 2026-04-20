import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  FileText,
  HeartPulse,
  Phone,
  Pill,
  User,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { api } from "@/lib/api";
import { calcAge, timeAgo } from "@/lib/utils";

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
    <div className="space-y-6 max-w-6xl mx-auto">
      <Link
        href="/patients"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-accent-cyan transition-colors"
      >
        <ArrowLeft className="h-4 w-4" /> Voltar aos pacientes
      </Link>

      {/* Header */}
      <div className="glass-card rounded-2xl p-6 flex items-start gap-5">
        {patient.photo_url ? (
          <Image
            src={patient.photo_url}
            alt={patient.full_name}
            width={112}
            height={112}
            className="rounded-full object-cover w-28 h-28 ring-2 ring-white/10"
          />
        ) : (
          <div className="w-28 h-28 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
            <User className="h-12 w-12 text-muted-foreground" />
          </div>
        )}

        <div className="flex-1">
          <h1 className="text-3xl font-bold tracking-tight">{patient.full_name}</h1>
          {patient.nickname && (
            <p className="text-muted-foreground text-sm mt-0.5">
              Conhecido(a) como <span className="text-foreground">{patient.nickname}</span>
            </p>
          )}
          <p className="text-muted-foreground text-sm mt-1.5">
            {age && <span className="tabular font-medium text-foreground/80">{age} anos</span>}
            {patient.gender && (
              <>
                <span className="mx-2 opacity-40">·</span>
                <span>{patient.gender === "F" ? "Feminino" : patient.gender === "M" ? "Masculino" : "Outro"}</span>
              </>
            )}
            {patient.room_number && (
              <>
                <span className="mx-2 opacity-40">·</span>
                <span className="uppercase tracking-wider text-[10px]">Quarto {patient.room_number}</span>
              </>
            )}
            {patient.care_unit && (
              <>
                <span className="mx-2 opacity-40">·</span>
                <span>{patient.care_unit}</span>
              </>
            )}
          </p>
          {patient.care_level && (
            <span className="inline-block mt-3 text-[10px] uppercase tracking-[0.15em] px-2.5 py-1 rounded-full bg-accent-purple/10 border border-accent-purple/30 text-accent-purple font-semibold">
              {patient.care_level}
            </span>
          )}
        </div>
      </div>

      {/* Condições + medicações */}
      <div className="grid md:grid-cols-2 gap-4">
        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-classification-attention/10 border border-classification-attention/30">
              <AlertTriangle className="h-4 w-4 text-classification-attention" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Condições clínicas
            </h2>
          </div>
          <ul className="space-y-2">
            {(patient.conditions || []).map((c, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <span className="status-dot status-dot-warning mt-1.5 flex-shrink-0" />
                <div>
                  <span className="font-medium text-foreground">{c.description}</span>
                  {c.code && (
                    <span className="text-[11px] text-muted-foreground ml-2 font-mono">({c.code})</span>
                  )}
                  {c.severity && (
                    <span className="text-[10px] ml-2 px-1.5 py-0.5 rounded bg-white/[0.04] text-muted-foreground">
                      {c.severity}
                    </span>
                  )}
                </div>
              </li>
            ))}
            {(patient.conditions || []).length === 0 && (
              <li className="text-sm text-muted-foreground">Nenhuma condição registrada</li>
            )}
          </ul>

          {patient.allergies && patient.allergies.length > 0 && (
            <div className="mt-5 pt-5 border-t border-white/[0.05]">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Alergias
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {patient.allergies.map((a) => (
                  <span
                    key={a}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-classification-critical/10 border border-classification-critical/30 text-classification-critical font-medium"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-accent-purple/10 border border-accent-purple/30">
              <Pill className="h-4 w-4 text-accent-purple" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Medicações em uso
            </h2>
          </div>
          <ul className="space-y-2">
            {(patient.medications || []).map((m, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <span className="status-dot status-dot-success mt-1.5 flex-shrink-0" />
                <div className="flex-1">
                  <div className="font-medium text-foreground">{m.name}</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    {m.schedule} {m.dose && `· ${m.dose}`}
                  </div>
                </div>
              </li>
            ))}
            {(patient.medications || []).length === 0 && (
              <li className="text-sm text-muted-foreground">Nenhuma medicação registrada</li>
            )}
          </ul>
        </section>
      </div>

      {/* Responsável */}
      {patient.responsible?.name && (
        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-accent-teal/10 border border-accent-teal/30">
              <Phone className="h-4 w-4 text-accent-teal" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Responsável
            </h2>
          </div>
          <div className="flex items-center gap-4 flex-wrap">
            <div>
              <div className="font-semibold">{patient.responsible.name}</div>
              {patient.responsible.relationship && (
                <div className="text-xs text-muted-foreground capitalize">
                  {patient.responsible.relationship}
                </div>
              )}
            </div>
            {patient.responsible.phone && (
              <div className="tabular text-sm text-accent-teal font-mono">
                {patient.responsible.phone}
              </div>
            )}
          </div>
        </section>
      )}

      {/* Histórico de relatos */}
      <section className="glass-card rounded-2xl overflow-hidden">
        <div className="p-6 border-b border-white/[0.05] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30">
              <FileText className="h-4 w-4 text-accent-cyan" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Histórico de relatos
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                <span className="tabular font-medium text-foreground">{reports.length}</span> registros
              </p>
            </div>
          </div>
        </div>

        <ul className="divide-y divide-white/[0.04]">
          {reports.length === 0 ? (
            <li className="p-12 text-center">
              <HeartPulse className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                Nenhum relato ainda para este paciente.
              </p>
            </li>
          ) : (
            reports.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reports/${r.id}`}
                  className="flex items-center justify-between gap-4 p-5 hover:bg-white/[0.02] transition-colors group"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-accent-cyan transition-colors">
                      {r.analysis?.summary || r.transcription?.slice(0, 120) || "Processando…"}
                    </p>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1">
                      {timeAgo(r.received_at)}
                    </p>
                  </div>
                  <ClassificationBadge classification={r.classification} />
                </Link>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
