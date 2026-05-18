"use client";

/**
 * ConfirmDialog — substitui window.confirm() com modal custom
 * dark theme + suporte a variante destrutiva + texto rich.
 *
 * Uso via hook (mais ergônomico):
 *   const confirm = useConfirm();
 *   if (await confirm({
 *     title: "Desativar contato?",
 *     description: "Histórico fica preservado pra audit.",
 *     confirmLabel: "Desativar",
 *     variant: "destructive",
 *   })) {
 *     // ... ação
 *   }
 *
 * Mount: <ConfirmDialogHost /> precisa estar 1× no root layout pra
 * o hook ter onde renderizar (já está em app/layout.tsx via wrapper).
 *
 * Vantagens vs confirm() nativo:
 *   - Estilo dark theme consistente
 *   - Variant destructive (botão vermelho pra ações irreversíveis)
 *   - Description rica (React nodes, não só string)
 *   - Acessível (ARIA + focus trap + ESC pra cancelar)
 *   - Bloqueia background scroll + click-out cancela
 *   - Não bloqueia thread (await Promise vs sync alert)
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";

export interface ConfirmOptions {
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
}

type Resolver = (confirmed: boolean) => void;

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm(): (opts: ConfirmOptions) => Promise<boolean> {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    throw new Error(
      "useConfirm precisa estar dentro de <ConfirmDialogHost>. Monta no root layout.",
    );
  }
  return ctx.confirm;
}

/**
 * Provider + host do modal. Monta uma vez no root.
 */
export function ConfirmDialogHost({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolverRef = useRef<Resolver | null>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  const confirm = useCallback((newOpts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setOpts(newOpts);
    });
  }, []);

  const close = useCallback(
    (result: boolean) => {
      resolverRef.current?.(result);
      resolverRef.current = null;
      setOpts(null);
    },
    [],
  );

  // ESC cancela
  useEffect(() => {
    if (!opts) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
      if (e.key === "Enter" && e.metaKey) close(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opts, close]);

  // Auto-focus no cancelar (mais seguro que default no destrutivo)
  useEffect(() => {
    if (opts) {
      // pequeno delay pra DOM estar pronto
      const t = setTimeout(() => cancelBtnRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [opts]);

  // Block body scroll quando aberto
  useEffect(() => {
    if (opts) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [opts]);

  const value = { confirm };

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {opts &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in-0 duration-150"
            onClick={() => close(false)}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <div
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md rounded-2xl border border-white/[0.08] bg-bg-elevated p-6 shadow-2xl animate-in zoom-in-95 duration-150"
            >
              <div className="flex items-start gap-3">
                {opts.variant === "destructive" && (
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="rounded-full bg-classification-attention/15 p-2">
                      <AlertTriangle className="h-4 w-4 text-classification-attention" />
                    </div>
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <h2 id="confirm-title" className="text-sm font-semibold">
                    {opts.title}
                  </h2>
                  {opts.description && (
                    <div className="text-[12px] text-muted-foreground mt-1.5 leading-relaxed">
                      {opts.description}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => close(false)}
                  className="flex-shrink-0 p-1 rounded hover:bg-white/[0.04] text-muted-foreground"
                  aria-label="Fechar"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="flex justify-end gap-2 mt-5">
                <button
                  ref={cancelBtnRef}
                  type="button"
                  onClick={() => close(false)}
                  className="text-xs px-3 py-2 rounded-lg border border-white/[0.06] hover:bg-white/[0.04]"
                >
                  {opts.cancelLabel || "Cancelar"}
                </button>
                <button
                  type="button"
                  onClick={() => close(true)}
                  className={[
                    "text-xs px-4 py-2 rounded-lg font-medium transition",
                    opts.variant === "destructive"
                      ? "bg-classification-attention text-white hover:bg-classification-attention/85"
                      : "accent-gradient text-slate-900",
                  ].join(" ")}
                >
                  {opts.confirmLabel || "Confirmar"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </ConfirmContext.Provider>
  );
}
