"use client";

import { Check } from "lucide-react";

const STATES: { id: string; label: string }[] = [
  { id: "greeting", label: "Saudação" },
  { id: "role_selection", label: "Quem cuida" },
  { id: "collect_payer_name", label: "Nome" },
  { id: "collect_payer_cpf", label: "CPF" },
  { id: "collect_beneficiary", label: "Paciente" },
  { id: "collect_conditions", label: "Condições" },
  { id: "collect_medications", label: "Medicações" },
  { id: "collect_contacts", label: "Contatos" },
  { id: "collect_address", label: "Endereço" },
  { id: "plan_selection", label: "Plano" },
  { id: "payment_method", label: "Pagamento" },
  { id: "payment_pending", label: "Confirmação" },
  { id: "consent_lgpd", label: "LGPD" },
  { id: "active", label: "Ativo" },
];

interface Props {
  currentState: string;
}

/**
 * Visualização da state machine da Sofia em tempo real.
 * Nodos iluminam conforme Sofia avança pelos 14 estados do onboarding.
 */
export function StateMachineViz({ currentState }: Props) {
  const currentIndex = STATES.findIndex((s) => s.id === currentState);

  return (
    <section className="glass-card rounded-2xl p-5">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-semibold">
            Sofia · state machine
          </div>
          <h3 className="text-sm font-semibold mt-0.5">Fluxo de onboarding</h3>
        </div>
        <div className="text-xs text-muted-foreground tabular">
          <span className="text-accent-cyan font-semibold">
            {Math.max(0, currentIndex + 1)}
          </span>
          <span className="opacity-60"> / {STATES.length}</span>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-1.5">
        {STATES.map((s, idx) => {
          const isActive = idx === currentIndex;
          const isDone = idx < currentIndex;
          const isPending = idx > currentIndex;

          return (
            <div
              key={s.id}
              className={`
                flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs border transition-all
                ${isActive
                  ? "bg-accent-cyan/10 border-accent-cyan/40 text-accent-cyan glow-cyan animate-pulse-soft"
                  : isDone
                    ? "bg-classification-routine/5 border-classification-routine/25 text-foreground/80"
                    : "bg-white/[0.02] border-white/5 text-muted-foreground"
                }
              `}
              aria-current={isActive ? "step" : undefined}
              aria-label={`${s.label} ${isDone ? "concluído" : isActive ? "em andamento" : "pendente"}`}
            >
              <div
                className={`w-4 h-4 rounded-full flex items-center justify-center flex-shrink-0 ${
                  isDone
                    ? "bg-classification-routine/15 border border-classification-routine/40"
                    : isActive
                      ? "bg-accent-cyan/20 border border-accent-cyan/50"
                      : "bg-white/[0.03] border border-white/10"
                }`}
              >
                {isDone ? (
                  <Check className="h-2.5 w-2.5 text-classification-routine" strokeWidth={3} aria-hidden />
                ) : isActive ? (
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse" />
                ) : (
                  <span className="text-[9px] text-muted-foreground/60 font-semibold tabular">
                    {idx + 1}
                  </span>
                )}
              </div>
              <span className={`truncate ${isActive ? "font-semibold" : ""}`}>
                {s.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="mt-4 h-1 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full accent-gradient transition-all duration-500 ease-out"
          style={{
            width: `${Math.max(0, ((currentIndex + 1) / STATES.length) * 100)}%`,
          }}
        />
      </div>
    </section>
  );
}
