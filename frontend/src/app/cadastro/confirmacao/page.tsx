"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Check, Sparkles } from "lucide-react";

import { getOnboardingSessionStatus } from "@/hooks/use-onboarding-web";

// ═══════════════════════════════════════════════════════════════════
// /cadastro/confirmacao — tela de handshake pro WhatsApp
//
// Aparece depois do POST /api/onboarding/start-from-web.
// Mostra:
//   - Confirmação visual do cadastro inicial
//   - CTA grande "Continuar no WhatsApp"
//   - Polling do estado da sessão (detecta quando user completa no WhatsApp)
//   - Se completar: parabéns + link pra portal
// ═══════════════════════════════════════════════════════════════════

export default function ConfirmacaoPage() {
  return (
    <div className="max-w-2xl mx-auto py-12 animate-fade-up">
      <Suspense fallback={<div className="text-center text-muted-foreground">Carregando…</div>}>
        <ConfirmacaoContent />
      </Suspense>
    </div>
  );
}

function ConfirmacaoContent() {
  const params = useSearchParams();
  const sessionId = params.get("session") || "";
  const waUrl = decodeURIComponent(params.get("wa") || "");

  const [sessionState, setSessionState] = useState<string | null>(null);
  const [isCompleted, setIsCompleted] = useState(false);

  // Polling da sessão a cada 5s
  useEffect(() => {
    if (!sessionId) return;

    const poll = async () => {
      const r = await getOnboardingSessionStatus(sessionId);
      if (r.status === "ok") {
        setSessionState(r.state ?? null);
        if (r.is_completed) {
          setIsCompleted(true);
        }
      }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [sessionId]);

  if (!sessionId || !waUrl) {
    return (
      <div className="glass-card rounded-2xl p-8 text-center">
        <p className="text-muted-foreground">
          Dados de sessão faltando.{" "}
          <Link href="/planos" className="accent-gradient-text underline">
            Voltar aos planos
          </Link>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="text-center space-y-3">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full accent-gradient mb-3">
          <Check className="h-8 w-8 text-slate-900" strokeWidth={3} />
        </div>
        <h1 className="text-3xl lg:text-4xl font-bold">
          Quase lá! <span className="accent-gradient-text">Último passo.</span>
        </h1>
        <p className="text-muted-foreground">
          Clica no botão abaixo pra Sofia te receber no WhatsApp.
        </p>
      </header>

      {/* CTA principal */}
      {!isCompleted ? (
        <div className="glass-card rounded-2xl p-8 text-center space-y-5">
          <div className="w-20 h-20 rounded-full accent-gradient mx-auto flex items-center justify-center shadow-[0_0_40px_rgba(49,225,255,0.3)]">
            <Sparkles className="h-10 w-10 text-slate-900" strokeWidth={2.5} />
          </div>

          <div>
            <div className="text-xl font-bold">Continuar no WhatsApp</div>
            <p className="text-sm text-muted-foreground mt-1">
              Sofia vai te pedir CPF, dados do seu ente querido e detalhes do plano.
              <br />
              Uns 3 minutos e tá pronto.
            </p>
          </div>

          <a
            href={waUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-8 py-4 rounded-xl accent-gradient text-slate-900 font-bold text-lg hover:shadow-[0_0_40px_rgba(49,225,255,0.5)] transition-all"
          >
            Abrir WhatsApp
            <ArrowRight className="h-5 w-5" />
          </a>

          <div className="text-[11px] text-muted-foreground">
            Não tem WhatsApp? Liga pra gente: <strong>(51) 4002-8922</strong>
          </div>
        </div>
      ) : (
        <div className="glass-card rounded-2xl p-8 text-center space-y-4 border-classification-routine/40">
          <div className="w-20 h-20 rounded-full bg-classification-routine/20 border-2 border-classification-routine/50 mx-auto flex items-center justify-center">
            <Check className="h-10 w-10 text-classification-routine" strokeWidth={3} />
          </div>
          <div>
            <div className="text-2xl font-bold text-classification-routine">
              Assinatura ativada! 🎉
            </div>
            <p className="text-muted-foreground mt-2">
              Tudo certo. A Sofia já está cuidando do seu ente querido.
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl accent-gradient text-slate-900 font-semibold"
          >
            Ir pro painel
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {/* Status silencioso */}
      {sessionState && !isCompleted && (
        <div className="text-center text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse" />
            aguardando você no WhatsApp · estado: <span className="font-mono">{sessionState}</span>
          </span>
        </div>
      )}

      {/* Footer */}
      <div className="text-center text-[11px] text-muted-foreground pt-4 space-y-1">
        <p>Sessão: <span className="font-mono">{sessionId.slice(0, 8)}…</span></p>
        <p>
          Dados protegidos pela LGPD ·{" "}
          <Link href="/planos" className="underline hover:text-foreground">
            Termos
          </Link>
        </p>
      </div>
    </div>
  );
}
