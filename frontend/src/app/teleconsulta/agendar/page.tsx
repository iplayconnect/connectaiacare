"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Calendar,
  Check,
  Clock,
  Copy,
  Link as LinkIcon,
  MessageSquare,
  Share2,
  Stethoscope,
  Video,
} from "lucide-react";

import { getPatient } from "@/hooks/use-patient";
import type { Patient } from "@/mocks/patients";

// ═══════════════════════════════════════════════════════════════════
// /teleconsulta/agendar — formulário de agendamento + link compartilhável
//
// Fluxo:
//   /patients/[id] → botão "Agendar teleconsulta" → este formulário
//   Usuário escolhe: médico, data/hora, duração, motivo
//   → "Agendar" gera um link compartilhável (para paciente/família)
//   → Show confirmação + opções de envio (WhatsApp/email/copiar)
// ═══════════════════════════════════════════════════════════════════

const DEMO_DOCTORS = [
  { id: "ana-silva", name: "Dra. Ana Silva", crm: "CRM/RS 12345", specialty: "Geriatria" },
  { id: "carlos-mendes", name: "Dr. Carlos Mendes", crm: "CRM/SP 67890", specialty: "Neurologia" },
  { id: "fernanda-lima", name: "Dra. Fernanda Lima", crm: "CRM/MG 54321", specialty: "Cardiologia" },
];

const DURATIONS = [
  { value: 30, label: "30 min — consulta breve" },
  { value: 45, label: "45 min — rotina (padrão)" },
  { value: 60, label: "60 min — investigação" },
];

export default function AgendarPage() {
  return (
    <div className="max-w-3xl mx-auto py-8">
      <Suspense fallback={<div className="text-muted-foreground">Carregando…</div>}>
        <AgendarForm />
      </Suspense>
    </div>
  );
}

function AgendarForm() {
  const params = useSearchParams();
  const patientIdFromUrl = params.get("patient");

  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);

  const [doctorId, setDoctorId] = useState(DEMO_DOCTORS[0].id);
  const [date, setDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  });
  const [time, setTime] = useState("14:30");
  const [duration, setDuration] = useState(45);
  const [reason, setReason] = useState("");
  const [submitted, setSubmitted] = useState<{
    id: string;
    link: string;
    scheduled_at: string;
  } | null>(null);

  useEffect(() => {
    if (!patientIdFromUrl) {
      setLoading(false);
      return;
    }
    getPatient(patientIdFromUrl)
      .then((r) => setPatient(r?.patient ?? null))
      .finally(() => setLoading(false));
  }, [patientIdFromUrl]);

  const doctor = DEMO_DOCTORS.find((d) => d.id === doctorId)!;

  if (loading) {
    return <div className="glass-card rounded-2xl p-8 text-center text-muted-foreground">Carregando paciente…</div>;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // TODO(coder): quando backend expuser POST /api/teleconsultas,
    // trocar por chamada real que retorna {id, room_name, share_url, scheduled_at}
    const scheduledAt = `${date}T${time}:00-03:00`;
    const id = `tc-${Math.random().toString(36).slice(2, 10)}`;
    const link = `${typeof window !== "undefined" ? window.location.origin : ""}/consulta/${id}`;
    setSubmitted({ id, link, scheduled_at: scheduledAt });
  };

  if (submitted) {
    return <AgendadoConfirmacao submitted={submitted} doctor={doctor} patient={patient} />;
  }

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Hero */}
      <header className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl accent-gradient flex items-center justify-center">
          <Video className="h-5 w-5 text-slate-900" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Agendar teleconsulta</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {patient
              ? `Para ${patient.nickname || patient.full_name}`
              : "Gera link compartilhável com paciente/família"}
          </p>
        </div>
      </header>

      {/* Resumo paciente */}
      {patient && (
        <section className="glass-card rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-accent-cyan/15 border border-accent-cyan/30 flex items-center justify-center font-bold text-accent-cyan">
            {patient.full_name.split(" ").slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold">{patient.full_name}</div>
            <div className="text-xs text-muted-foreground">
              {patient.care_unit ?? "—"}
              {patient.room_number ? ` · Qto ${patient.room_number}` : ""}
            </div>
          </div>
          {patient.conditions.length > 0 && (
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground text-right">
              {patient.conditions.length} condição(ões) ativa(s)
            </div>
          )}
        </section>
      )}

      {/* Formulário */}
      <form onSubmit={handleSubmit} className="glass-card rounded-2xl p-6 space-y-5">
        {/* Médico */}
        <div>
          <Label icon={<Stethoscope className="h-3.5 w-3.5" />}>Médico</Label>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
            {DEMO_DOCTORS.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setDoctorId(d.id)}
                className={`text-left p-3 rounded-xl border transition-all ${
                  doctorId === d.id
                    ? "border-accent-cyan/50 bg-accent-cyan/5"
                    : "border-white/10 bg-white/[0.02] hover:border-accent-cyan/30"
                }`}
              >
                <div className="text-sm font-semibold">{d.name}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5 font-mono">
                  {d.crm}
                </div>
                <div className="text-[11px] text-muted-foreground uppercase tracking-wider mt-0.5">
                  {d.specialty}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Data/hora/duração */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <Label icon={<Calendar className="h-3.5 w-3.5" />}>Data</Label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              min={new Date().toISOString().slice(0, 10)}
              required
              className="mt-1.5 w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-accent-cyan/50 focus:outline-none"
            />
          </div>
          <div>
            <Label icon={<Clock className="h-3.5 w-3.5" />}>Horário</Label>
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              required
              className="mt-1.5 w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-accent-cyan/50 focus:outline-none"
            />
          </div>
          <div>
            <Label>Duração</Label>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="mt-1.5 w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-accent-cyan/50 focus:outline-none"
            >
              {DURATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Motivo */}
        <div>
          <Label icon={<MessageSquare className="h-3.5 w-3.5" />}>Motivo da consulta</Label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex: Revisão de anti-hipertensivo após PA 160/95 ontem."
            rows={3}
            className="mt-1.5 w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg px-3 py-2 text-sm focus:border-accent-cyan/50 focus:outline-none resize-y"
          />
          <p className="text-[11px] text-muted-foreground mt-1">
            Opcional. O médico verá antes de entrar na sala.
          </p>
        </div>

        {/* Submit */}
        <div className="flex items-center justify-between pt-2">
          <Link
            href="/teleconsulta"
            className="text-xs text-muted-foreground hover:text-foreground underline"
          >
            ← Voltar
          </Link>
          <button
            type="submit"
            className="inline-flex items-center gap-2 accent-gradient text-slate-900 font-semibold px-5 py-2.5 rounded-xl hover:shadow-[0_0_24px_rgba(49,225,255,0.4)] transition-all"
          >
            <Video className="h-4 w-4" strokeWidth={2.5} />
            Agendar e gerar link
          </button>
        </div>
      </form>

      {/* Nota CFM */}
      <p className="text-center text-[11px] text-muted-foreground italic">
        Teleconsulta regulamentada pela Resolução CFM 2.314/2022 · médico responsável com CRM ativo
      </p>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Confirmação + link compartilhável
// ══════════════════════════════════════════════════════════════════

function AgendadoConfirmacao({
  submitted,
  doctor,
  patient,
}: {
  submitted: { id: string; link: string; scheduled_at: string };
  doctor: (typeof DEMO_DOCTORS)[0];
  patient: Patient | null;
}) {
  const [copied, setCopied] = useState(false);

  const scheduled = new Date(submitted.scheduled_at);
  const dateStr = scheduled.toLocaleString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(submitted.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const whatsappText = encodeURIComponent(
    `Olá! Sua teleconsulta com ${doctor.name} está agendada para ${dateStr}.\n\nEntre no link no horário:\n${submitted.link}`,
  );

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Success hero */}
      <div className="glass-card rounded-2xl p-8 text-center">
        <div className="w-16 h-16 rounded-full accent-gradient mx-auto flex items-center justify-center shadow-[0_0_40px_rgba(49,225,255,0.3)] mb-4">
          <Check className="h-8 w-8 text-slate-900" strokeWidth={3} />
        </div>
        <h1 className="text-2xl font-bold">Teleconsulta agendada 🎉</h1>
        <p className="text-muted-foreground mt-1">
          {doctor.name} · {doctor.specialty}
        </p>
        <p className="text-sm text-foreground mt-3 capitalize">{dateStr}</p>
      </div>

      {/* Link compartilhável */}
      <section className="glass-card rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <LinkIcon className="h-4 w-4 text-accent-cyan" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Link da sala
          </h2>
        </div>

        <div className="flex items-center gap-2 p-3 bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg">
          <input
            readOnly
            value={submitted.link}
            className="flex-1 bg-transparent text-sm font-mono text-foreground/90 outline-none truncate"
            onFocus={(e) => e.currentTarget.select()}
          />
          <button
            onClick={copyLink}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border border-accent-cyan/30 bg-accent-cyan/8 text-accent-cyan hover:bg-accent-cyan/15 transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3" /> Copiado
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" /> Copiar
              </>
            )}
          </button>
        </div>

        <p className="text-[11px] text-muted-foreground mt-2">
          Qualquer pessoa com esse link entra na sala. Ele fica válido por 24h após
          o horário agendado.
        </p>
      </section>

      {/* Opções de envio */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <ShareOption
          href={`https://wa.me/?text=${whatsappText}`}
          external
          icon={<MessageSquare className="h-4 w-4" />}
          label="Enviar pelo WhatsApp"
          hint={patient?.responsible[0]?.phone ? "Paciente/família" : ""}
        />
        <ShareOption
          href={`mailto:?subject=Teleconsulta agendada&body=Sua teleconsulta está agendada para ${dateStr}. Entre pelo link: ${submitted.link}`}
          external
          icon={<Share2 className="h-4 w-4" />}
          label="Enviar por email"
        />
        <Link
          href={submitted.link}
          className="solid-card rounded-xl p-4 flex items-center gap-3 hover:border-accent-cyan/40 transition-colors"
        >
          <div className="w-9 h-9 rounded-lg bg-accent-cyan/10 text-accent-cyan flex items-center justify-center">
            <Video className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold">Entrar agora</div>
            <div className="text-[11px] text-muted-foreground">Testar a sala</div>
          </div>
        </Link>
      </section>

      {/* Ações rodapé */}
      <footer className="flex items-center justify-between text-sm pt-2">
        <Link
          href="/teleconsulta"
          className="text-muted-foreground hover:text-foreground underline"
        >
          ← Voltar pra lista
        </Link>
        {patient && (
          <Link
            href={`/patients/${patient.id}`}
            className="text-accent-cyan hover:brightness-125"
          >
            Abrir prontuário de {patient.nickname || patient.full_name} →
          </Link>
        )}
      </footer>
    </div>
  );
}

function Label({
  icon,
  children,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-semibold">
      {icon}
      <span>{children}</span>
    </div>
  );
}

function ShareOption({
  href,
  external,
  icon,
  label,
  hint,
}: {
  href: string;
  external?: boolean;
  icon: React.ReactNode;
  label: string;
  hint?: string;
}) {
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      className="solid-card rounded-xl p-4 flex items-center gap-3 hover:border-accent-cyan/40 transition-colors"
    >
      <div className="w-9 h-9 rounded-lg bg-accent-cyan/10 text-accent-cyan flex items-center justify-center">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold">{label}</div>
        {hint && <div className="text-[11px] text-muted-foreground truncate">{hint}</div>}
      </div>
    </a>
  );
}
