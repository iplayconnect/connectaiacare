"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  HeartPulse,
  Loader2,
  MessageCircle,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════
// /forgot-password — solicita link de redefinição via WhatsApp
// ═══════════════════════════════════════════════════════════════

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ channel?: string; hint?: string } | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.forgotPassword(email.trim().toLowerCase());
      setSuccess({ channel: res.channel, hint: res.hint });
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Não foi possível processar.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

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
            Redefinir senha
          </div>
        </div>

        {success ? (
          <SuccessCard email={email} channel={success.channel} hint={success.hint} />
        ) : (
          <form
            onSubmit={onSubmit}
            className="rounded-2xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6 sm:p-7 space-y-5 shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
          >
            <div>
              <h1 className="text-lg font-semibold text-foreground">
                Esqueceu a senha?
              </h1>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                Informe seu email cadastrado. Se o email existir, enviaremos um
                link de redefinição pelo WhatsApp registrado na sua conta. O
                link expira em 1 hora.
              </p>
            </div>

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-classification-attention/10 border border-classification-attention/20 text-xs text-classification-attention">
                <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span className="leading-relaxed">{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seuemail@clinica.com.br"
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
                  Enviando...
                </>
              ) : (
                "Enviar link de redefinição"
              )}
            </button>

            <Link
              href="/login"
              className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-3 w-3" />
              Voltar pro login
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}

function SuccessCard({
  email,
  channel,
  hint,
}: {
  email: string;
  channel?: string;
  hint?: string;
}) {
  const sentByWhatsapp = channel === "whatsapp";
  return (
    <div className="rounded-2xl border border-classification-routine/30 bg-classification-routine/[0.06] backdrop-blur-xl p-6 sm:p-7 space-y-4 shadow-[0_8px_32px_rgba(0,0,0,0.45)]">
      <div className="flex items-center gap-2 text-classification-routine">
        <CheckCircle2 className="h-5 w-5" />
        <h1 className="text-base font-semibold">Solicitação registrada</h1>
      </div>

      {sentByWhatsapp ? (
        <div className="space-y-3">
          <div className="flex items-start gap-2 text-xs text-foreground">
            <MessageCircle className="h-4 w-4 text-classification-routine flex-shrink-0 mt-0.5" />
            <span className="leading-relaxed">
              Se <strong>{email}</strong> existe na nossa base, enviamos um link
              de redefinição pro WhatsApp cadastrado na conta. O link expira em
              1 hora.
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            Não recebeu? Aguarde um minuto e tente novamente. Se o problema
            persistir, fale com o administrador da sua clínica.
          </p>
        </div>
      ) : (
        <div className="space-y-3 text-xs text-foreground leading-relaxed">
          <p>
            Se <strong>{email}</strong> existe na nossa base, processamos sua
            solicitação.
          </p>
          {hint && (
            <p className="text-classification-attention">{hint}</p>
          )}
          <p className="text-[11px] text-muted-foreground">
            Não foi possível enviar o link automaticamente — provavelmente
            falta WhatsApp cadastrado nessa conta. Procure o administrador da
            sua clínica para um reset manual.
          </p>
        </div>
      )}

      <Link
        href="/login"
        className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-xs border border-white/[0.08] transition-colors"
      >
        <ArrowLeft className="h-3 w-3" />
        Voltar pro login
      </Link>
    </div>
  );
}
