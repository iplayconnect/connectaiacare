"use client";

import { useEffect, useState } from "react";
import { Phone, PhoneCall, Loader2, X, CheckCircle2 } from "lucide-react";

import { api, type CallScenario } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// Botão "Ligar via Sofia" contextual no prontuário do paciente.
// Abre modal pra escolher cenário, pré-preenche destino com o
// telefone do responsável (vindo do PatientHero).
// ═══════════════════════════════════════════════════════════════

interface Props {
  patientId: string;
  patientName: string;
  responsibleName?: string | null;
  responsiblePhone?: string | null;
}

export function SofiaCallButton({
  patientId,
  patientName,
  responsibleName,
  responsiblePhone,
}: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl border border-accent-cyan/40 text-accent-cyan font-semibold text-sm hover:bg-accent-cyan/10 transition-all"
        aria-label={`Ligar via Sofia sobre ${patientName}`}
      >
        <PhoneCall className="h-4 w-4" strokeWidth={2.5} />
        Ligar via Sofia
      </button>
      {open && (
        <SofiaCallModal
          patientId={patientId}
          patientName={patientName}
          responsibleName={responsibleName}
          responsiblePhone={responsiblePhone}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function SofiaCallModal({
  patientId,
  patientName,
  responsibleName,
  responsiblePhone,
  onClose,
}: Props & { onClose: () => void }) {
  const [scenarios, setScenarios] = useState<CallScenario[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [destination, setDestination] = useState(
    (responsiblePhone || "").replace(/\D/g, ""),
  );
  const [calleeName, setCalleeName] = useState(responsibleName || "");
  const [loading, setLoading] = useState(true);
  const [dialing, setDialing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .communicationsScenarios()
      .then((r) => {
        // Filtra só cenários relevantes pra ligações sobre paciente
        const relevant = r.scenarios.filter(
          (s) =>
            s.direction === "outbound" &&
            s.active &&
            ["familia", "cuidador_pro"].includes(s.persona),
        );
        const fallback = r.scenarios.filter(
          (s) => s.direction === "outbound" && s.active,
        );
        const list = relevant.length > 0 ? relevant : fallback;
        setScenarios(list);
        if (list.length > 0) setScenarioId(list[0].id);
      })
      .catch((e) => setError(e?.message || "Erro carregando cenários"))
      .finally(() => setLoading(false));
  }, []);

  async function handleDial() {
    if (!destination.trim() || !scenarioId) return;
    setDialing(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.communicationsDial({
        scenario_id: scenarioId,
        destination: destination.trim().replace(/\D/g, ""),
        patient_id: patientId,
        full_name: calleeName.trim() || undefined,
      });
      setResult(`Discando · ${r.call_id}`);
      // Polling: confirma se a call estabilizou no _active_calls.
      // Se sumir em <5s sem ter aparecido = trunk bloqueou ou rejeitou rapidinho.
      const callId = r.call_id;
      let appeared = false;
      const startTs = Date.now();
      const interval = setInterval(async () => {
        const elapsed = Date.now() - startTs;
        try {
          const a = await api.communicationsActiveCalls();
          const present = (a.calls || []).includes(callId);
          if (present) appeared = true;
          if (elapsed > 6000) {
            clearInterval(interval);
            setDialing(false);
            if (!appeared) {
              setError(
                "Ligação caiu antes de tocar. Pode ser bloqueio do operador (verifique saldo/status do trunk SIP).",
              );
              setResult(null);
            } else {
              setResult("Ligação em curso");
              setTimeout(onClose, 1500);
            }
          }
        } catch {
          // ignora erro de polling
        }
      }, 1200);
    } catch (e: any) {
      setError(e?.message || "Falha ao iniciar ligação");
      setDialing(false);
      return;
    } finally {
      // Mantém dialing=true até o polling resolver, pra desabilitar o botão
    }
  }

  const selected = scenarios.find((s) => s.id === scenarioId);

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[hsl(222,47%,7%)] border border-white/10 rounded-xl w-full max-w-md">
        <header className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
          <div className="flex items-center gap-2">
            <Phone className="h-4 w-4 text-accent-cyan" />
            <h2 className="font-semibold text-sm">
              Ligar via Sofia · {patientName}
            </h2>
          </div>
          <button onClick={onClose}>
            <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
          </button>
        </header>

        <div className="p-5 space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground py-4 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" />
              Carregando…
            </div>
          ) : (
            <>
              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Cenário
                </label>
                <select
                  value={scenarioId}
                  onChange={(e) => setScenarioId(e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 outline-none text-sm"
                >
                  {scenarios.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
                {selected?.description && (
                  <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
                    {selected.description}
                  </p>
                )}
              </div>

              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Telefone destino
                </label>
                <input
                  type="tel"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                  placeholder="5551996161700"
                  className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 outline-none text-sm font-mono"
                />
              </div>

              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Nome de quem atende
                </label>
                <input
                  type="text"
                  value={calleeName}
                  onChange={(e) => setCalleeName(e.target.value)}
                  placeholder={responsibleName || "Nome"}
                  className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 outline-none text-sm"
                />
              </div>

              {result && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300">
                  <CheckCircle2 className="h-4 w-4" />
                  {result}
                </div>
              )}
              {error && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-300">
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        <footer className="flex justify-end gap-2 px-5 py-3 border-t border-white/[0.06]">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded border border-white/10 hover:bg-white/[0.04]"
          >
            Cancelar
          </button>
          <button
            onClick={handleDial}
            disabled={dialing || loading || !destination.trim() || !scenarioId}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90 disabled:opacity-50"
          >
            {dialing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <PhoneCall className="h-3.5 w-3.5" />
            )}
            Ligar
          </button>
        </footer>
      </div>
    </div>
  );
}
