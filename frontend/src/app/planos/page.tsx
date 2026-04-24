import Link from "next/link";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  HeartPulse,
  ShieldCheck,
  Sparkles,
  Users,
  Watch,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// Página pública /planos — landing comparativa
// Destino principal de tráfego pago (Google Ads / Meta Ads)
// CTA → /cadastro?plan=X → handshake /api/onboarding/start-from-web
// ═══════════════════════════════════════════════════════════════════

const PLANS = [
  {
    sku: "essencial",
    name: "Essencial",
    price_cents: 4990,
    tagline: "Para começar o cuidado sem grande investimento",
    target: "Idoso autônomo + 1 cuidador",
    icon: HeartPulse,
    features: [
      "Check-in diário proativo da Sofia",
      "Até 3 contatos de emergência",
      "Lembretes ilimitados de medicação",
      "Detecção básica de anormalidades",
      "30 msgs/dia com Sofia",
    ],
  },
  {
    sku: "familia",
    name: "Família",
    price_cents: 8990,
    tagline: "Quando a família cuida em conjunto",
    target: "2+ cuidadores em revezamento",
    icon: Users,
    features: [
      "Tudo do Essencial +",
      "Grupo familiar ilimitado",
      "Rede comunitária de cuidado",
      "Relatório semanal no grupo",
      "Histórico exportável em PDF",
      "60 msgs/dia com Sofia",
    ],
  },
  {
    sku: "premium",
    name: "Premium",
    price_cents: 14990,
    tagline: "Cuidado clínico ativo com central 24h",
    target: "Idoso com condições crônicas",
    icon: ShieldCheck,
    featured: true,
    features: [
      "Tudo do Família +",
      "Teleconsulta inclusa (até 2/mês)",
      "Central Atente 24h humana",
      "Monitoramento clínico proativo",
      "Validação de medicação (Beers)",
      "100 msgs/dia com Sofia",
    ],
  },
  {
    sku: "premium_device",
    name: "Premium + Dispositivo",
    price_cents: 19990,
    tagline: "Proteção máxima com IoT Tecnosenior",
    target: "Risco de queda ou desmaio",
    icon: Watch,
    features: [
      "Tudo do Premium +",
      "Pulseira SOS Tecnosenior",
      "Detecção automática de queda",
      "Sinais vitais 24h (BPM, HRV)",
      "Assistência domiciliar",
      "150 msgs/dia com Sofia",
    ],
  },
];

export default function PlanosPage() {
  return (
    <div className="max-w-7xl mx-auto space-y-16 py-8">
      {/* Hero */}
      <header className="text-center space-y-5 max-w-3xl mx-auto animate-fade-up">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan text-xs font-semibold uppercase tracking-wider">
          <Sparkles className="h-3 w-3" />
          Sofia Cuida · ConnectaIACare
        </div>
        <h1 className="text-5xl lg:text-6xl font-bold leading-tight">
          Cuidado com seu{" "}
          <span className="accent-gradient-text">ente querido</span>,
          <br />
          24 horas por dia.
        </h1>
        <p className="text-lg text-muted-foreground">
          Uma Sofia de plantão no WhatsApp + central humana + médicos certificados.
          <br />
          Escolha o plano que encaixa no seu momento.
        </p>
        <div className="flex items-center justify-center gap-6 text-sm text-muted-foreground pt-2">
          <span className="flex items-center gap-1.5">
            <Check className="h-4 w-4 text-classification-routine" />
            7 dias grátis no cartão
          </span>
          <span className="flex items-center gap-1.5">
            <Check className="h-4 w-4 text-classification-routine" />
            Zero fidelidade
          </span>
          <span className="flex items-center gap-1.5">
            <Check className="h-4 w-4 text-classification-routine" />
            Cancelamento livre
          </span>
        </div>
      </header>

      {/* Grid de planos */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {PLANS.map((plan) => (
          <PlanCard key={plan.sku} plan={plan} />
        ))}
      </div>

      {/* Footer compliance */}
      <footer className="text-center text-xs text-muted-foreground space-y-1 pt-8">
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <span>🛡️ LGPD · Lei 13.709/2018</span>
          <span>⚕️ CFM 2.314/2022</span>
          <span>👴 Estatuto do Idoso</span>
          <span>🛒 CDC Art. 49</span>
        </div>
        <p className="pt-2">
          Dados protegidos · médicos com CRM ativo · direito ao cancelamento preservado
        </p>
      </footer>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// PlanCard
// ══════════════════════════════════════════════════════════════════

function PlanCard({ plan }: { plan: (typeof PLANS)[0] }) {
  const Icon = plan.icon;
  const price = (plan.price_cents / 100).toFixed(2).replace(".", ",");

  return (
    <article
      className={`
        rounded-2xl p-6 flex flex-col relative
        ${plan.featured
          ? "glass-card accent-gradient-border scale-[1.03] shadow-[0_0_40px_rgba(49,225,255,0.15)] lg:-translate-y-2"
          : "solid-card"
        }
      `}
    >
      {plan.featured && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full accent-gradient text-slate-900 text-[11px] font-bold uppercase tracking-wider shadow-glow-cyan">
            Mais escolhido
          </span>
        </div>
      )}

      <div className="flex items-center gap-2.5 mb-4">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center ${
            plan.featured
              ? "accent-gradient text-slate-900"
              : "bg-accent-cyan/10 text-accent-cyan"
          }`}
        >
          <Icon className="h-5 w-5" strokeWidth={2.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xl font-bold truncate">{plan.name}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {plan.target}
          </div>
        </div>
      </div>

      <div className="mb-5">
        <div className="flex items-baseline gap-1">
          <span className="text-sm text-muted-foreground">R$</span>
          <span className="text-4xl font-bold tabular">{price}</span>
          <span className="text-sm text-muted-foreground">/mês</span>
        </div>
        <p className="text-sm text-muted-foreground mt-1">{plan.tagline}</p>
      </div>

      <ul className="space-y-2 flex-1 mb-6">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm">
            <CheckCircle2
              className={`h-4 w-4 flex-shrink-0 mt-0.5 ${
                plan.featured ? "text-accent-cyan" : "text-classification-routine"
              }`}
              aria-hidden
            />
            <span className="text-foreground/85">{f}</span>
          </li>
        ))}
      </ul>

      <Link
        href={`/cadastro?plan=${plan.sku}`}
        className={`
          w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold transition-all
          ${plan.featured
            ? "accent-gradient text-slate-900 hover:shadow-[0_0_24px_rgba(49,225,255,0.4)]"
            : "border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan hover:bg-accent-cyan/10"
          }
        `}
      >
        Assinar {plan.name}
        <ArrowRight className="h-4 w-4" />
      </Link>
    </article>
  );
}
