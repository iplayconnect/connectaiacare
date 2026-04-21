"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";

import { api, type ClosedReason } from "@/lib/api";

const REASON_OPTIONS: { value: ClosedReason; label: string; description: string }[] = [
  {
    value: "cuidado_iniciado",
    label: "Cuidado iniciado",
    description: "Equipe assumiu o atendimento presencial.",
  },
  {
    value: "paciente_estavel",
    label: "Paciente estável",
    description: "Quadro clínico controlado, sem intercorrências.",
  },
  {
    value: "encaminhado_hospital",
    label: "Encaminhado ao hospital",
    description: "Paciente transportado para unidade externa.",
  },
  {
    value: "transferido",
    label: "Transferido internamente",
    description: "Mudança de ala ou unidade dentro da instituição.",
  },
  {
    value: "sem_intercorrencia",
    label: "Sem intercorrência",
    description: "Observação rotineira encerrada normalmente.",
  },
  {
    value: "falso_alarme",
    label: "Falso alarme",
    description: "Situação não confirmada pela equipe.",
  },
  {
    value: "obito",
    label: "Óbito",
    description: "Registro de desfecho fatal.",
  },
  {
    value: "outro",
    label: "Outro motivo",
    description: "Descrever nas observações.",
  },
];

export function CloseEventButton({
  eventId,
  humanId,
}: {
  eventId: string;
  humanId: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ClosedReason | "">("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const router = useRouter();

  const humanLabel = humanId
    ? `#${humanId.toString().padStart(4, "0")}`
    : "evento";

  async function handleClose() {
    if (!reason) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.closeEvent(eventId, {
        closed_by: "operator",
        closed_reason: reason,
        closure_notes: notes || undefined,
      });
      const syncMsg = result.medmonitor_sync.created
        ? ` Sincronizado no TotalCare (nota #${result.medmonitor_sync.note_id}).`
        : result.medmonitor_sync.attempted
        ? " Tentativa de sync no TotalCare (ver log)."
        : "";
      setSuccess(`Evento ${humanLabel} encerrado.${syncMsg}`);
      setTimeout(() => {
        setOpen(false);
        router.refresh();
      }, 1500);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao encerrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="px-4 py-2 rounded-lg bg-classification-routine/10 border border-classification-routine/30 text-classification-routine text-xs font-semibold uppercase tracking-wider hover:bg-classification-routine/20 transition-colors inline-flex items-center gap-2"
      >
        <Check className="h-3.5 w-3.5" />
        Encerrar evento
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => !loading && setOpen(false)}
        >
          <div
            className="glass-card rounded-2xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">
                  Encerrar evento {humanLabel}
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Ao fechar, sincronizamos automaticamente com o TotalCare como nota de cuidado.
                </p>
              </div>
              <button
                onClick={() => !loading && setOpen(false)}
                className="text-muted-foreground hover:text-foreground p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 mb-4">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Motivo do encerramento
              </label>
              <div className="grid grid-cols-1 gap-2">
                {REASON_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                      reason === opt.value
                        ? "border-accent-cyan/60 bg-accent-cyan/5"
                        : "border-white/[0.05] hover:border-white/[0.12]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="reason"
                      value={opt.value}
                      checked={reason === opt.value}
                      onChange={() => setReason(opt.value)}
                      className="sr-only"
                    />
                    <div className="flex items-start gap-3">
                      <div
                        className={`mt-0.5 w-4 h-4 rounded-full border-2 flex-shrink-0 ${
                          reason === opt.value
                            ? "border-accent-cyan bg-accent-cyan"
                            : "border-white/20"
                        }`}
                      />
                      <div>
                        <div className="font-medium text-sm">{opt.label}</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {opt.description}
                        </div>
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-1.5 mb-5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Observações (opcional)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Ex: Enfermeira João avaliou às 22h, PA 120x80 aferida, paciente lúcido e orientado."
                className="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:border-accent-cyan/40 placeholder:text-muted-foreground/50"
                rows={3}
                disabled={loading}
              />
            </div>

            {error && (
              <div className="mb-3 text-xs text-classification-critical bg-classification-critical/10 border border-classification-critical/30 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
            {success && (
              <div className="mb-3 text-xs text-classification-routine bg-classification-routine/10 border border-classification-routine/30 rounded-lg px-3 py-2">
                ✓ {success}
              </div>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setOpen(false)}
                disabled={loading}
                className="px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={handleClose}
                disabled={!reason || loading || !!success}
                className="px-4 py-2 rounded-lg bg-accent-cyan text-background text-xs font-semibold hover:bg-accent-teal transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Encerrando...
                  </>
                ) : (
                  <>
                    <Check className="h-3.5 w-3.5" />
                    Confirmar encerramento
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
