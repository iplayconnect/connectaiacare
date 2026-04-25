"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  HeartPulse,
  KeyRound,
  Loader2,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// /reset-password?token=... — define nova senha via token de reset
// ═══════════════════════════════════════════════════════════════

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      <div
        aria-hidden
        className="fixed inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(800px circle at 20% 10%, hsla(187,100%,40%,0.12), transparent 50%), radial-gradient(900px circle at 85% 90%, hsla(160,84%,39%,0.08), transparent 60%)",
        }}
      />
      <Suspense fallback={<div className="text-muted-foreground text-xs">Carregando...</div>}>
        <ResetForm />
      </Suspense>
    </div>
  );
}

function ResetForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = (searchParams.get("token") || "").trim();

  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Link inválido — token ausente.");
      return;
    }
    if (next.length < 8) {
      setError("A nova senha deve ter ao menos 8 caracteres.");
      return;
    }
    if (next !== confirm) {
      setError("Confirmação não bate com a nova senha.");
      return;
    }
    setLoading(true);
    try {
      await api.resetPassword(token, next);
      setDone(true);
      setTimeout(() => router.replace("/login?reason=password_reset_ok"), 2000);
    } catch (err) {
      const reason = err instanceof ApiError ? err.reason : undefined;
      if (reason === "invalid_or_expired_token") {
        setError("Link inválido ou expirado. Solicite um novo em 'Esqueci a senha'.");
      } else if (reason === "password_too_short") {
        setError("Senha muito curta (mín 8).");
      } else {
        setError("Não foi possível trocar a senha. Tente novamente.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md px-4 z-10">
      <div className="flex flex-col items-center mb-8">
        <div className="accent-gradient p-3 rounded-xl shadow-glow-cyan mb-4">
          <HeartPulse className="h-7 w-7 text-slate-900" strokeWidth={2.5} />
        </div>
        <div className="text-2xl font-bold tracking-tight">
          <span className="accent-gradient-text">ConnectaIA</span>
          <span className="text-foreground">Care</span>
        </div>
        <div className="text-[11px] text-muted-foreground uppercase tracking-[0.18em] mt-1.5">
          Definir nova senha
        </div>
      </div>

      {done ? (
        <div className="rounded-2xl border border-classification-routine/30 bg-classification-routine/[0.06] p-6 space-y-3 text-center">
          <CheckCircle2 className="h-8 w-8 text-classification-routine mx-auto" />
          <h1 className="text-base font-semibold">Senha redefinida</h1>
          <p className="text-xs text-muted-foreground">
            Redirecionando pro login com sua nova senha...
          </p>
        </div>
      ) : !token ? (
        <div className="rounded-2xl border border-classification-attention/30 bg-classification-attention/[0.06] p-6 space-y-3 text-center">
          <AlertCircle className="h-8 w-8 text-classification-attention mx-auto" />
          <h1 className="text-base font-semibold">Link inválido</h1>
          <p className="text-xs text-muted-foreground">
            Este link de redefinição é inválido ou está incompleto. Solicite um novo.
          </p>
          <Link
            href="/forgot-password"
            className="inline-block px-4 py-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-xs border border-white/[0.08]"
          >
            Esqueci a senha
          </Link>
        </div>
      ) : (
        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6 sm:p-7 space-y-5 shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
        >
          <div>
            <h1 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Nova senha
            </h1>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              Escolha uma senha forte (mínimo 8 caracteres). Após a troca, todas
              as sessões anteriores serão encerradas por segurança.
            </p>
          </div>

          {error && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-classification-attention/10 border border-classification-attention/20 text-xs text-classification-attention">
              <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span className="leading-relaxed">{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground" htmlFor="newp">
              Nova senha
            </label>
            <input
              id="newp"
              type="password"
              autoComplete="new-password"
              autoFocus
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="input"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground" htmlFor="confirm">
              Repetir nova senha
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg accent-gradient text-slate-900 font-medium text-sm shadow-glow-cyan hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Trocando...
              </>
            ) : (
              "Definir nova senha"
            )}
          </button>
        </form>
      )}
    </div>
  );
}
