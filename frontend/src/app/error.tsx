"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertOctagon, RefreshCw, Home, Bug } from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// Error boundary global
// Mostra erro real + stack trace em vez da mensagem opaca do Next.
// Facilita debug em produção com usuários reais reportando problemas.
// ═══════════════════════════════════════════════════════════════════

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log pro console + pode plugar Sentry futuro aqui
    // eslint-disable-next-line no-console
    console.error("[GlobalError]", error);
  }, [error]);

  const stackLines = (error.stack || "").split("\n").slice(0, 8);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-2xl w-full space-y-6">
        <div className="glass-card rounded-2xl p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-classification-critical/15 border border-classification-critical/40 flex items-center justify-center mx-auto mb-5">
            <AlertOctagon className="h-8 w-8 text-classification-critical" strokeWidth={2.5} />
          </div>

          <h1 className="text-2xl font-bold mb-2">Ops — algo quebrou</h1>
          <p className="text-sm text-muted-foreground mb-5">
            Um erro inesperado aconteceu. Pode tentar de novo ou voltar pra tela inicial.
          </p>

          {/* Erro real */}
          <div className="text-left bg-[hsl(222,30%,10%)] border border-classification-critical/30 rounded-xl p-4 mb-5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-classification-critical font-bold mb-2">
              <Bug className="h-3 w-3" />
              Detalhe técnico
            </div>
            <div className="text-sm font-mono text-classification-critical break-all">
              {error.name}: {error.message}
            </div>
            {error.digest && (
              <div className="text-[10px] text-muted-foreground mt-2 font-mono">
                digest: {error.digest}
              </div>
            )}
          </div>

          {stackLines.length > 1 && (
            <details className="text-left mb-5">
              <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                Stack trace ({stackLines.length} linhas)
              </summary>
              <pre className="mt-2 p-3 bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg text-[10px] font-mono text-muted-foreground overflow-x-auto">
                {stackLines.join("\n")}
              </pre>
            </details>
          )}

          <div className="flex items-center justify-center gap-2">
            <button
              onClick={reset}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold accent-gradient text-slate-900 hover:shadow-[0_0_20px_rgba(49,225,255,0.35)] transition-all"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Tentar de novo
            </button>
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold border border-white/10 bg-white/5 hover:bg-white/10 transition-colors"
            >
              <Home className="h-3.5 w-3.5" />
              Tela inicial
            </Link>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground text-center italic">
          Se o erro persistir, compartilhe a mensagem acima com o suporte técnico.
        </p>
      </div>
    </div>
  );
}
