"use client";

/**
 * Toast — substitui window.alert() com notificação não-bloqueante.
 *
 * Uso via hook:
 *   const toast = useToast();
 *   toast.success("Contato cadastrado");
 *   toast.error("Falhou: phone duplicado");
 *   toast.info("Recalculando scores…");
 *
 * Auto-dismiss em 4s (configurável). Múltiplos toasts empilham
 * no canto inferior-direito da tela.
 *
 * Mount: <ToastHost /> precisa estar 1× no root layout.
 */

import { createContext, useCallback, useContext, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  variant: ToastVariant;
  message: string;
  durationMs: number;
}

interface ToastApi {
  show: (variant: ToastVariant, message: string, durationMs?: number) => void;
  success: (message: string, durationMs?: number) => void;
  error: (message: string, durationMs?: number) => void;
  info: (message: string, durationMs?: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast precisa estar dentro de <ToastHost>.");
  }
  return ctx;
}

const VARIANT_STYLES: Record<ToastVariant, { icon: typeof CheckCircle2; color: string }> = {
  success: {
    icon: CheckCircle2,
    color: "border-classification-routine/40 bg-classification-routine/10 text-classification-routine",
  },
  error: {
    icon: AlertCircle,
    color: "border-classification-attention/40 bg-classification-attention/10 text-classification-attention",
  },
  info: {
    icon: Info,
    color: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  },
};

let nextId = 1;

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (variant: ToastVariant, message: string, durationMs = 4000) => {
      const id = nextId++;
      setToasts((prev) => [...prev, { id, variant, message, durationMs }]);
      if (durationMs > 0) {
        setTimeout(() => dismiss(id), durationMs);
      }
    },
    [dismiss],
  );

  const api: ToastApi = {
    show,
    success: (m, d) => show("success", m, d),
    error: (m, d) => show("error", m, d ?? 6000), // erros ficam um pouco mais
    info: (m, d) => show("info", m, d),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      {typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed bottom-4 right-4 z-[80] flex flex-col gap-2 max-w-sm pointer-events-none"
            aria-live="polite"
            aria-atomic="true"
          >
            {toasts.map((t) => {
              const Icon = VARIANT_STYLES[t.variant].icon;
              return (
                <div
                  key={t.id}
                  className={[
                    "pointer-events-auto rounded-lg border backdrop-blur-xl px-3 py-2.5 shadow-2xl",
                    "flex items-start gap-2",
                    "animate-in slide-in-from-right-4 fade-in-0 duration-200",
                    VARIANT_STYLES[t.variant].color,
                  ].join(" ")}
                  role="status"
                >
                  <Icon className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 text-xs leading-relaxed text-foreground/95">
                    {t.message}
                  </div>
                  <button
                    type="button"
                    onClick={() => dismiss(t.id)}
                    className="flex-shrink-0 p-0.5 rounded hover:bg-white/[0.04] text-muted-foreground"
                    aria-label="Fechar"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              );
            })}
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  );
}
