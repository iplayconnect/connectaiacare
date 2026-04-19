import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { ClassificationBadge } from "@/components/classification-badge";
import { calcAge, formatDateTime } from "@/lib/utils";
import { AlertCircle, ArrowLeft, CheckCircle, Mic, Pill, Stethoscope, User } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function ReportDetailPage({ params }: { params: { id: string } }) {
  let report;
  try {
    const data = await api.getReport(params.id);
    report = data.report;
  } catch {
    notFound();
  }

  const analysis = report.analysis || {};
  const age = calcAge(report.patient?.birth_date ?? null);

  return (
    <div className="space-y-6 max-w-4xl">
      <Link href="/reports" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ArrowLeft className="h-4 w-4" /> Voltar aos relatos
      </Link>

      {/* Header do paciente */}
      <div className="bg-white rounded-lg border p-6 flex items-center gap-4">
        {report.patient_photo ? (
          <Image
            src={report.patient_photo}
            alt={report.patient_name || ""}
            width={80}
            height={80}
            className="rounded-full object-cover w-20 h-20"
          />
        ) : (
          <div className="w-20 h-20 rounded-full bg-slate-200 flex items-center justify-center">
            <User className="h-8 w-8 text-slate-500" />
          </div>
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{report.patient_name || "Paciente não identificado"}</h1>
          <p className="text-muted-foreground">
            {age && `${age} anos`}
            {report.patient_room && ` · Quarto ${report.patient_room}`}
            {report.patient?.care_unit && ` · ${report.patient.care_unit}`}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <ClassificationBadge classification={report.classification} />
            <span className="text-xs text-muted-foreground">
              registrado em {formatDateTime(report.received_at)}
            </span>
          </div>
        </div>
      </div>

      {/* Áudio */}
      {report.audio_url && (
        <div className="bg-white rounded-lg border p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-3">
            <Mic className="h-5 w-5 text-blue-600" /> Áudio original
          </h2>
          <audio controls src={report.audio_url} className="w-full" />
        </div>
      )}

      {/* Transcrição */}
      {report.transcription && (
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-3">Transcrição</h2>
          <p className="text-slate-700 leading-relaxed italic">&ldquo;{report.transcription}&rdquo;</p>
        </div>
      )}

      {/* Análise IA */}
      {analysis.summary && (
        <div className="bg-gradient-to-br from-blue-50 to-teal-50 rounded-lg border border-blue-200 p-6 space-y-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold mb-1">
              <Stethoscope className="h-5 w-5 text-blue-700" /> Análise IA
            </h2>
            <p className="text-slate-800">{analysis.summary}</p>
            {analysis.classification_reasoning && (
              <p className="text-sm text-slate-600 italic mt-2">{analysis.classification_reasoning}</p>
            )}
          </div>

          {analysis.alerts && analysis.alerts.length > 0 && (
            <div>
              <h3 className="font-semibold flex items-center gap-1 mb-2">
                <AlertCircle className="h-4 w-4 text-orange-600" /> Alertas
              </h3>
              <ul className="space-y-2">
                {analysis.alerts.map((a, i) => (
                  <li
                    key={i}
                    className={`p-3 rounded border ${
                      a.level === "critico"
                        ? "bg-red-50 border-red-200"
                        : a.level === "alto"
                        ? "bg-orange-50 border-orange-200"
                        : "bg-amber-50 border-amber-200"
                    }`}
                  >
                    <div className="font-medium">{a.title}</div>
                    <div className="text-sm text-slate-700">{a.description}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.recommendations_caregiver && analysis.recommendations_caregiver.length > 0 && (
            <div>
              <h3 className="font-semibold flex items-center gap-1 mb-2">
                <CheckCircle className="h-4 w-4 text-emerald-600" /> Recomendações ao cuidador
              </h3>
              <ul className="space-y-1 list-disc list-inside text-sm">
                {analysis.recommendations_caregiver.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {analysis.tags && analysis.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {analysis.tags.map((t) => (
                <span key={t} className="px-2 py-0.5 text-xs rounded-full bg-white border text-slate-600">
                  #{t}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Contexto do paciente */}
      {report.patient_conditions && Array.isArray(report.patient_conditions) && report.patient_conditions.length > 0 && (
        <div className="bg-white rounded-lg border p-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold mb-3">
            <Pill className="h-5 w-5 text-indigo-600" /> Condições e medicações
          </h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground mb-2">CONDIÇÕES</h3>
              <ul className="space-y-1 text-sm">
                {(report.patient_conditions as any[]).map((c, i) => (
                  <li key={i}>
                    <span className="font-medium">{c.description}</span>
                    {c.severity && <span className="text-muted-foreground"> — {c.severity}</span>}
                  </li>
                ))}
              </ul>
            </div>
            {report.patient_medications && Array.isArray(report.patient_medications) && (
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">MEDICAÇÕES</h3>
                <ul className="space-y-1 text-sm">
                  {(report.patient_medications as any[]).map((m, i) => (
                    <li key={i}>
                      <span className="font-medium">{m.name}</span>
                      {m.schedule && <span className="text-muted-foreground"> — {m.schedule}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
