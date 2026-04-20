import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  AlertOctagon,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Mic,
  Pill,
  Sparkles,
  Stethoscope,
  User,
} from "lucide-react";

import { ClassificationBadge } from "@/components/classification-badge";
import { api } from "@/lib/api";
import { calcAge, formatDateTime } from "@/lib/utils";

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
  const age = calcAge(report.patient_birth_date ?? null);
  const alerts = analysis.alerts || [];

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <Link
        href="/reports"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-accent-cyan transition-colors"
      >
        <ArrowLeft className="h-4 w-4" /> Voltar aos relatos
      </Link>

      {/* Header paciente */}
      <div className="glass-card rounded-2xl p-6 flex items-start gap-5">
        {report.patient_photo ? (
          <div className="relative">
            <Image
              src={report.patient_photo}
              alt={report.patient_name || ""}
              width={96}
              height={96}
              className="rounded-full object-cover w-24 h-24 ring-2 ring-white/10"
            />
            {report.classification === "critical" && (
              <span className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-classification-critical border-2 border-background animate-pulse-glow" />
            )}
          </div>
        ) : (
          <div className="w-24 h-24 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center">
            <User className="h-10 w-10 text-muted-foreground" />
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
                {report.patient_name || "Paciente não identificado"}
              </h1>
              <p className="text-muted-foreground mt-1 text-sm">
                {age && (
                  <span className="tabular font-medium text-foreground">{age} anos</span>
                )}
                {report.patient_room && (
                  <>
                    <span className="mx-2 opacity-40">·</span>
                    <span className="uppercase tracking-wider text-[10px]">
                      Quarto {report.patient_room}
                    </span>
                  </>
                )}
                {report.patient_care_unit && (
                  <>
                    <span className="mx-2 opacity-40">·</span>
                    <span>{report.patient_care_unit}</span>
                  </>
                )}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <ClassificationBadge classification={report.classification} />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {formatDateTime(report.received_at)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Áudio */}
      {report.audio_url && (
        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30">
              <Mic className="h-4 w-4 text-accent-cyan" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Áudio original do cuidador
            </h2>
          </div>
          <audio controls src={report.audio_url} className="w-full" />
        </section>
      )}

      {/* Transcrição */}
      {report.transcription && (
        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-accent-teal/10 border border-accent-teal/30">
              <Sparkles className="h-4 w-4 text-accent-teal" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Transcrição · pt-BR clínico
            </h2>
          </div>
          <blockquote className="text-foreground/90 leading-relaxed italic text-[15px] border-l-2 border-accent-cyan/30 pl-4">
            &ldquo;{report.transcription}&rdquo;
          </blockquote>
        </section>
      )}

      {/* Análise IA */}
      {analysis.summary && (
        <section className="glass-card rounded-2xl p-6 space-y-5 border-accent-cyan/20">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg accent-gradient shadow-glow-cyan">
                <Bot className="h-4 w-4 text-slate-900" strokeWidth={2.5} />
              </div>
              <h2 className="text-sm font-semibold uppercase tracking-wider">
                <span className="accent-gradient-text">Análise IA</span>
              </h2>
            </div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Raciocínio clínico · modelo de última geração
            </span>
          </div>

          <p className="text-foreground leading-relaxed">{analysis.summary}</p>

          {analysis.classification_reasoning && (
            <div className="text-sm text-muted-foreground italic border-l-2 border-accent-teal/30 pl-4">
              {analysis.classification_reasoning}
            </div>
          )}

          {/* Alertas */}
          {alerts.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                <AlertOctagon className="h-3.5 w-3.5" />
                Alertas
              </h3>
              <ul className="space-y-2.5">
                {alerts.map((a, i) => (
                  <li
                    key={i}
                    className={`solid-card rounded-xl p-4 ${
                      a.level === "critico"
                        ? "border-classification-critical/40 glow-critical"
                        : a.level === "alto"
                        ? "border-classification-urgent/40"
                        : "border-classification-attention/30"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <span
                        className={`status-dot mt-1.5 flex-shrink-0 ${
                          a.level === "critico"
                            ? "status-dot-danger"
                            : a.level === "alto"
                            ? "status-dot-warning"
                            : "status-dot-warning"
                        }`}
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-foreground">{a.title}</div>
                        <div className="text-sm text-muted-foreground mt-0.5">
                          {a.description}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recomendações */}
          {analysis.recommendations_caregiver && analysis.recommendations_caregiver.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-2">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Recomendações ao cuidador
              </h3>
              <ul className="space-y-1.5">
                {analysis.recommendations_caregiver.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-accent-cyan mt-0.5">›</span>
                    <span className="text-foreground/90">{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tags */}
          {analysis.tags && analysis.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-2">
              {analysis.tags.map((t) => (
                <span
                  key={t}
                  className="text-[11px] px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-muted-foreground font-mono"
                >
                  #{t}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Contexto clínico do paciente */}
      {report.patient_conditions && Array.isArray(report.patient_conditions) && report.patient_conditions.length > 0 && (
        <section className="glass-card rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-2 rounded-lg bg-accent-purple/10 border border-accent-purple/30">
              <Stethoscope className="h-4 w-4 text-accent-purple" />
            </div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Contexto clínico
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                Condições
              </h3>
              <ul className="space-y-1.5">
                {(report.patient_conditions as any[]).map((c, i) => (
                  <li key={i} className="text-sm flex items-start gap-2">
                    <span className="status-dot status-dot-warning mt-1.5 flex-shrink-0" />
                    <div>
                      <span className="font-medium text-foreground">{c.description}</span>
                      {c.severity && (
                        <span className="text-[11px] ml-2 px-1.5 py-0.5 rounded bg-white/[0.04] text-muted-foreground">
                          {c.severity}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {report.patient_medications && Array.isArray(report.patient_medications) && report.patient_medications.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Pill className="h-3 w-3" />
                  Medicações em uso
                </h3>
                <ul className="space-y-1.5">
                  {(report.patient_medications as any[]).map((m, i) => (
                    <li key={i} className="text-sm flex items-start gap-2">
                      <span className="status-dot status-dot-success mt-1.5 flex-shrink-0" />
                      <div>
                        <span className="font-medium text-foreground">{m.name}</span>
                        {m.schedule && (
                          <span className="text-[11px] text-muted-foreground ml-2">
                            {m.schedule}
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
