"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { HeartPulse, ShieldCheck, AlertCircle, Loader2 } from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { getStoredUser } from "@/lib/auth";

const REASON_MESSAGES: Record<string, string> = {
  invalid_credentials: "Email ou senha incorretos.",
  missing_credentials: "Preencha email e senha.",
  network_error: "Falha de conexão. Tente novamente em alguns segundos.",
  jwt_secret_not_configured:
    "Servidor sem JWT_SECRET configurado. Avise o administrador.",
  unauthorized: "Sessão expirada. Faça login novamente.",
};

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      {/* Ambient gradient (mesmo do RootLayout) */}
      <div
        aria-hidden
        className="fixed inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(800px circle at 20% 10%, hsla(187,100%,40%,0.12), transparent 50%), radial-gradient(900px circle at 85% 90%, hsla(160,84%,39%,0.08), transparent 60%)",
        }}
      />
      <Suspense fallback={<LoginSkeleton />}>
        <LoginForm />
      </Suspense>
    </div>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, loading, user, hydrated } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Se já está autenticado, redireciona pra destino (next param) ou home
  useEffect(() => {
    if (hydrated && user) {
      const next = searchParams.get("next") || "/";
      router.replace(next);
    }
  }, [hydrated, user, router, searchParams]);

  // Pré-validação: se já há sessão (mas AuthContext ainda não hidratou), evita flash
  useEffect(() => {
    if (!hydrated) {
      const stored = getStoredUser();
      if (stored) {
        const next = searchParams.get("next") || "/";
        router.replace(next);
      }
    }
  }, [hydrated, router, searchParams]);

  // Detecta razão pré-existente (ex: redirect de api 401)
  useEffect(() => {
    const reason = searchParams.get("reason");
    if (reason && REASON_MESSAGES[reason]) {
      setError(REASON_MESSAGES[reason]);
    }
  }, [searchParams]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email || !password) {
      setError(REASON_MESSAGES.missing_credentials);
      return;
    }
    const result = await login(email.trim(), password);
    if (!result.ok) {
      setError(REASON_MESSAGES[result.reason] || "Não foi possível entrar.");
      return;
    }
    const next = searchParams.get("next") || "/";
    router.replace(next);
  }

  return (
    <div className="w-full max-w-md px-4 z-10">
      {/* Logo */}
      <div className="flex flex-col items-center mb-8">
        <div className="accent-gradient p-3 rounded-xl shadow-glow-cyan mb-4">
          <HeartPulse
            className="h-7 w-7 text-slate-900"
            strokeWidth={2.5}
          />
        </div>
        <div className="text-2xl font-bold tracking-tight">
          <span className="accent-gradient-text">ConnectaIA</span>
          <span className="text-foreground">Care</span>
        </div>
        <div className="text-[11px] text-muted-foreground uppercase tracking-[0.18em] mt-1.5">
          Cuidado integrado · Plataforma clínica
        </div>
      </div>

      {/* Card */}
      <form
        onSubmit={onSubmit}
        className="rounded-2xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-xl p-6 sm:p-7 space-y-5 shadow-[0_8px_32px_rgba(0,0,0,0.45)]"
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">
            Entrar
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Acesse com o email cadastrado pela sua clínica ou parceiro.
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
            className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:border-accent-cyan/40 focus:bg-white/[0.06] transition-all"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="password">
            Senha
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full px-3 py-2.5 rounded-lg bg-white/[0.04] border border-white/[0.08] text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:border-accent-cyan/40 focus:bg-white/[0.06] transition-all"
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
              Entrando...
            </>
          ) : (
            "Entrar"
          )}
        </button>

        <div className="pt-2 border-t border-white/[0.04] flex items-center gap-2 text-[11px] text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5 text-classification-routine" />
          <span>
            Acesso autorizado · LGPD Art. 11 · CFM 2.314/2022
          </span>
        </div>
      </form>

      <div className="text-center mt-6 text-[11px] text-muted-foreground">
        Não tem conta?{" "}
        <Link
          href="/cadastro"
          className="text-accent-cyan hover:underline"
        >
          Conheça os planos
        </Link>
      </div>
    </div>
  );
}

function LoginSkeleton() {
  return (
    <div className="w-full max-w-md px-4 z-10 animate-pulse">
      <div className="h-32 rounded-2xl bg-white/[0.04]" />
    </div>
  );
}
