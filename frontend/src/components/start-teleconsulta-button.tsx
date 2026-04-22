"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import {
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Share2,
  Stethoscope,
  TestTube2,
  Video,
  X,
} from "lucide-react";

import { api, type TeleconsultaStartResponse } from "@/lib/api";

// Persona médica demo — sincronizada com seed do backend (migration 006)
const DEMO_DOCTORS = [
  {
    id: "ana-silva",
    name: "Dra. Ana Silva",
    crm: "CRM/RS 12345",
    specialty: "Geriatria",
    isDemo: true,
  },
];

export function StartTeleconsultaButton({
  eventId,
  patientName,
  disabled = false,
}: {
  eventId: string;
  patientName: string;
  disabled?: boolean;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TeleconsultaStartResponse | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState(DEMO_DOCTORS[0]);

  async function handleStart() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.startTeleconsulta(eventId, {
        initiator_name: selectedDoctor.name,
        initiator_role: "doctor",
      });
      setResult(res);
      setConfirmOpen(false);
      setResultOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao iniciar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setConfirmOpen(true)}
        disabled={disabled}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-sm font-semibold hover:bg-accent-teal hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-glow-cyan"
      >
        <Video className="h-4 w-4" strokeWidth={2.5} />
        Iniciar Teleconsulta
      </button>

      {confirmOpen && (
        <ModalShell onClose={() => !loading && setConfirmOpen(false)}>
          <div className="max-w-md">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center">
                  <Video className="h-5 w-5 text-accent-cyan" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Iniciar teleconsulta</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Consulta com <span className="text-foreground">{patientName}</span>
                  </p>
                </div>
              </div>
              <button
                onClick={() => !loading && setConfirmOpen(false)}
                className="text-muted-foreground hover:text-foreground p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Seleção de médico */}
            <div className="mb-5">
              <label className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground mb-2 block">
                Profissional que conduzirá a consulta
              </label>
              <div className="space-y-2">
                {DEMO_DOCTORS.map((d) => (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDoctor(d)}
                    className={`
                      w-full flex items-center gap-3 p-3 rounded-lg border transition-all text-left
                      ${
                        selectedDoctor.id === d.id
                          ? "bg-accent-cyan/5 border-accent-cyan/30"
                          : "bg-white/[0.02] border-white/[0.05] hover:border-white/[0.12]"
                      }
                    `}
                  >
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-cyan/30 to-accent-teal/30 border border-white/10 flex items-center justify-center text-xs font-bold flex-shrink-0">
                      {initials(d.name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium">{d.name}</span>
                        {d.isDemo && (
                          <span className="text-[9px] uppercase tracking-wider bg-classification-attention/15 text-classification-attention px-1 py-0.5 rounded">
                            demo
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {d.crm} · {d.specialty}
                      </div>
                    </div>
                    {selectedDoctor.id === d.id && (
                      <Check className="h-4 w-4 text-accent-cyan flex-shrink-0" />
                    )}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-2.5 italic">
                Em produção, qualquer médico cadastrado com CRM ativo acessa.
              </p>
            </div>

            {/* Disclaimer compliance */}
            <div className="mb-5 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05] text-[11px] text-muted-foreground leading-relaxed">
              <div className="flex items-start gap-2">
                <Stethoscope className="h-3.5 w-3.5 text-accent-teal mt-0.5 flex-shrink-0" />
                <div>
                  Ao iniciar, será solicitado ao paciente <strong className="text-foreground">consentimento de gravação</strong> e
                  <strong className="text-foreground"> verificação de identidade</strong> (CFM 2.314/2022, LGPD Art. 11).
                </div>
              </div>
            </div>

            {error && (
              <div className="mb-3 text-xs text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmOpen(false)}
                disabled={loading}
                className="px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleStart}
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors disabled:opacity-50 inline-flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Criando sala...
                  </>
                ) : (
                  <>
                    <Video className="h-3.5 w-3.5" />
                    Iniciar
                  </>
                )}
              </button>
            </div>
          </div>
        </ModalShell>
      )}

      {resultOpen && result && (
        <TeleconsultaReadyModal
          result={result}
          patientName={patientName}
          doctorName={selectedDoctor.name}
          onClose={() => setResultOpen(false)}
        />
      )}
    </>
  );
}

function TeleconsultaReadyModal({
  result,
  patientName,
  doctorName,
  onClose,
}: {
  result: TeleconsultaStartResponse;
  patientName: string;
  doctorName: string;
  onClose: () => void;
}) {
  const [copiedPatient, setCopiedPatient] = useState(false);

  async function copyPatientLink() {
    try {
      await navigator.clipboard.writeText(result.patient_url);
      setCopiedPatient(true);
      setTimeout(() => setCopiedPatient(false), 2000);
    } catch {
      // fallback silencioso
    }
  }

  return (
    <ModalShell onClose={onClose}>
      <div className="max-w-md">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-classification-routine/10 border border-classification-routine/25 flex items-center justify-center">
            <Check className="h-5 w-5 text-classification-routine" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">Sala pronta</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Teleconsulta <span className="font-mono text-foreground">{result.room_name}</span>
            </p>
          </div>
        </div>

        {/* Médico */}
        <div className="mb-3 p-4 rounded-xl border border-accent-cyan/25 bg-accent-cyan/[0.03]">
          <div className="text-[10px] uppercase tracking-[0.15em] text-accent-cyan mb-2">
            Link do profissional
          </div>
          <div className="text-sm font-medium mb-1">{doctorName}</div>
          <div className="text-[11px] text-muted-foreground mb-3">
            Abra este link agora no navegador para entrar como profissional.
          </div>
          <a
            href={result.doctor_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-accent-cyan text-slate-900 text-xs font-semibold hover:bg-accent-teal transition-colors w-full justify-center"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Abrir minha sala
          </a>
        </div>

        {/* Paciente */}
        <div className="mb-5 p-4 rounded-xl border border-white/[0.06] bg-white/[0.02]">
          <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-2">
            Link do paciente · WhatsApp
          </div>
          <div className="text-sm font-medium mb-1">{patientName}</div>
          <div className="text-[11px] text-muted-foreground mb-3 break-all font-mono bg-black/20 p-2 rounded">
            {result.patient_url.length > 80
              ? result.patient_url.slice(0, 80) + "..."
              : result.patient_url}
          </div>
          <button
            onClick={copyPatientLink}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] transition-colors w-full justify-center"
          >
            {copiedPatient ? (
              <>
                <Check className="h-3.5 w-3.5 text-classification-routine" />
                Copiado!
              </>
            ) : (
              <>
                <Share2 className="h-3.5 w-3.5" />
                Copiar link
              </>
            )}
          </button>
        </div>

        <p className="text-[11px] text-muted-foreground italic mb-4 leading-relaxed">
          Envie o link ao paciente/familiar pelo WhatsApp. Expira em 2h ·
          sala destruída após 5min sem participantes.
        </p>

        <div className="flex items-center justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] transition-colors"
          >
            Fechar
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ═══════════════════════════════════════════════════════════════
// ModalShell — overlay + card via portal, com ESC pra fechar
// ═══════════════════════════════════════════════════════════════
function ModalShell({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-up"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="glass-card rounded-2xl p-6 w-full shadow-2xl border border-white/[0.1]"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

function initials(name: string): string {
  return name
    .replace(/^(Dr\.?|Dra\.?)\s+/i, "")
    .split(" ")
    .filter((n) => n.length > 1)
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();
}
