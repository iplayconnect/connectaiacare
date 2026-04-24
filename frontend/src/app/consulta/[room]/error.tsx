"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertOctagon, RefreshCw, Video } from "lucide-react";

export default function ConsultaError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[ConsultaError]", error);
  }, [error]);

  return (
    <div className="min-h-[calc(100vh-80px)] flex items-center justify-center p-6">
      <div className="max-w-lg w-full glass-card rounded-2xl p-8 text-center space-y-5">
        <div className="w-14 h-14 rounded-full bg-classification-critical/15 border border-classification-critical/40 flex items-center justify-center mx-auto">
          <AlertOctagon className="h-7 w-7 text-classification-critical" strokeWidth={2.5} />
        </div>

        <div>
          <h2 className="text-xl font-bold">Não foi possível abrir a sala</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Algo deu errado ao preparar a teleconsulta.
          </p>
        </div>

        <div className="text-left bg-[hsl(222,30%,10%)] border border-classification-critical/30 rounded-xl p-3">
          <div className="text-[10px] uppercase tracking-wider text-classification-critical font-bold mb-1">
            Erro
          </div>
          <div className="text-sm font-mono text-classification-critical break-all">
            {error.message || error.name}
          </div>
          {error.digest && (
            <div className="text-[10px] text-muted-foreground mt-1 font-mono">
              ref: {error.digest}
            </div>
          )}
        </div>

        <div className="flex items-center justify-center gap-2">
          <button
            onClick={reset}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold accent-gradient text-slate-900"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Tentar abrir de novo
          </button>
          <Link
            href="/teleconsulta"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold border border-white/10 bg-white/5 hover:bg-white/10"
          >
            <Video className="h-3.5 w-3.5" />
            Lista de consultas
          </Link>
        </div>
      </div>
    </div>
  );
}
