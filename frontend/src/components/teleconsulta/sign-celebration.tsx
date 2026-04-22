"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Download, FileText, Share2, Sparkles } from "lucide-react";

// ═══════════════════════════════════════════════════════════════
// Modal celebração pós-assinatura:
//   ✓ Confirmação visual
//   ✓ Download do FHIR Bundle (JSON)
//   ✓ Info da sync com TotalCare
//   ✓ CTAs: ver prontuário longitudinal, voltar ao dashboard
// ═══════════════════════════════════════════════════════════════

export function SignCelebration({
  teleconsultaId,
  patientName,
  doctorName,
  onClose,
}: {
  teleconsultaId: string;
  patientName: string;
  doctorName: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

  // Confete lite — círculos pulsando
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  async function downloadFhir() {
    try {
      const res = await fetch(`${apiBase}/api/teleconsulta/${teleconsultaId}`);
      const data = await res.json();
      const bundle = data?.teleconsulta?.fhir_bundle;
      if (!bundle) return;
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/fhir+json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `teleconsulta-${teleconsultaId.slice(0, 8)}.fhir.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("fhir_download_failed", e);
    }
  }

  async function copyFhirId() {
    try {
      await navigator.clipboard.writeText(teleconsultaId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // silencioso
    }
  }

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[10000] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-up"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Confete lite */}
      {mounted && (
        <div className="pointer-events-none fixed inset-0 overflow-hidden">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="absolute rounded-full bg-accent-cyan/20 animate-ping"
              style={{
                width: `${8 + Math.random() * 14}px`,
                height: `${8 + Math.random() * 14}px`,
                left: `${Math.random() * 100}%`,
                top: `${20 + Math.random() * 40}%`,
                animationDelay: `${Math.random() * 1.5}s`,
                animationDuration: `${1.5 + Math.random() * 2}s`,
              }}
            />
          ))}
        </div>
      )}

      <div
        className="relative glass-card rounded-3xl p-6 md:p-8 w-full max-w-md shadow-2xl border border-accent-cyan/25 bg-gradient-to-br from-accent-cyan/[0.03] to-accent-teal/[0.02]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Ícone central */}
        <div className="flex justify-center mb-5">
          <div className="relative">
            <div className="absolute inset-0 bg-classification-routine/30 rounded-full blur-xl animate-pulse" />
            <div className="relative w-16 h-16 rounded-full bg-classification-routine/15 border-2 border-classification-routine/40 flex items-center justify-center">
              <Check className="h-8 w-8 text-classification-routine" strokeWidth={3} />
            </div>
          </div>
        </div>

        {/* Título */}
        <div className="text-center mb-5">
          <h2 className="text-xl font-semibold mb-1 flex items-center justify-center gap-2">
            <Sparkles className="h-4 w-4 text-accent-cyan" />
            Prontuário assinado
          </h2>
          <p className="text-[14px] text-foreground/85 leading-relaxed">
            A teleconsulta com <span className="text-foreground font-semibold">{patientName}</span> foi
            assinada eletronicamente por{" "}
            <span className="text-foreground font-semibold">{doctorName}</span>.
          </p>
        </div>

        {/* Passos confirmados */}
        <div className="space-y-2 mb-5">
          <ConfirmStep label="Bundle FHIR R4 gerado">
            Estrutura padrão interoperável (Patient, Encounter, Condition, MedicationRequest,
            ClinicalImpression).
          </ConfirmStep>
          <ConfirmStep label="Sincronizado com TotalCare">
            Nota clínica criada na central de cuidadores com resumo acessível ao cuidador.
          </ConfirmStep>
          <ConfirmStep label="Evento de cuidado encerrado">
            Classificado como <span className="font-mono text-[11px]">cuidado_iniciado</span>.
          </ConfirmStep>
        </div>

        {/* Ações */}
        <div className="space-y-2">
          <button
            onClick={downloadFhir}
            className="w-full px-4 py-2.5 rounded-lg bg-accent-cyan text-slate-900 text-sm font-semibold hover:bg-accent-teal transition-colors inline-flex items-center justify-center gap-2 shadow-glow-cyan"
          >
            <Download className="h-4 w-4" />
            Baixar FHIR Bundle
          </button>

          <button
            onClick={copyFhirId}
            className="w-full px-4 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.07] transition-colors inline-flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-classification-routine" />
                ID copiado
              </>
            ) : (
              <>
                <Share2 className="h-3.5 w-3.5" />
                Copiar ID da consulta
              </>
            )}
          </button>

          <a
            href="/dashboard"
            className="w-full px-4 py-2 rounded-lg bg-transparent border border-white/[0.06] text-xs font-medium hover:border-white/[0.12] transition-colors inline-flex items-center justify-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <FileText className="h-3.5 w-3.5" />
            Voltar ao Dashboard
          </a>
        </div>

        <div className="text-center mt-4 text-[10px] text-muted-foreground/60 italic">
          Demo · assinatura mocked. Produção: Vidaas / ICP-Brasil / CFM 2.314/2022.
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ConfirmStep({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="w-4 h-4 rounded-full bg-classification-routine/20 border border-classification-routine/40 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Check className="h-2.5 w-2.5 text-classification-routine" strokeWidth={3.5} />
      </div>
      <div>
        <div className="text-[13px] font-semibold text-foreground">{label}</div>
        <div className="text-[12px] text-foreground/75 leading-relaxed">
          {children}
        </div>
      </div>
    </div>
  );
}
