"use client";

import {
  AlertCircle,
  BadgeCheck,
  Beaker,
  BellRing,
  Brain,
  Calendar,
  Cloud,
  CreditCard,
  Database,
  FileCheck,
  Globe2,
  HeartPulse,
  Hospital,
  Landmark,
  Layers,
  Mail,
  Mic,
  Network,
  Phone,
  Pill,
  Radio,
  Shield,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Stethoscope,
  Users,
  Video,
  Watch,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// Slide T1 — "Não começamos ontem"
// ═══════════════════════════════════════════════════════════════════

export function SlideT1() {
  const milestones = [
    {
      label: "Commit 0",
      status: "done",
      items: ["Multi-tenant", "Multi-locale", "LOINC-aligned"],
    },
    {
      label: "Hoje",
      status: "done",
      items: ["331 testes verdes", "15 migrations", "7 ADRs publicados"],
      highlight: true,
    },
    {
      label: "6 meses",
      status: "pending",
      items: ["FHIR $everything", "SOC 2 audit", "ISO 13485"],
    },
    {
      label: "18 meses",
      status: "pending",
      items: ["HIPAA + GDPR", "LatAm 3 países", "US compliance"],
    },
  ];

  return (
    <SlideFrame eyebrow="Fundação" ariaLabel="Slide 1: infraestrutura pronta pra escala regulatória">
      <div className="max-w-6xl w-full space-y-14">
        <div className="text-center space-y-4">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            Infraestrutura pronta para{" "}
            <span className="accent-gradient-text">escala regulatória</span>{" "}
            desde o dia 1.
          </h2>
          <p className="text-lg text-muted-foreground max-w-3xl mx-auto">
            Cada linha revisada. Cada decisão documentada. Cada mudança rastreável.
          </p>
        </div>

        {/* Timeline */}
        <div className="relative">
          {/* linha base */}
          <div
            aria-hidden
            className="absolute left-0 right-0 top-[34px] h-px bg-gradient-to-r from-accent-cyan via-accent-teal to-transparent"
          />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
            {milestones.map((m) => (
              <div key={m.label} className="relative">
                <div
                  className={`mx-auto w-4 h-4 rounded-full flex items-center justify-center ${
                    m.status === "done"
                      ? "bg-accent-cyan glow-cyan"
                      : "bg-white/10 border-2 border-white/20"
                  }`}
                  aria-hidden
                >
                  {m.highlight && (
                    <span className="absolute -inset-2 rounded-full accent-gradient opacity-30 blur-md animate-pulse" />
                  )}
                </div>
                <div
                  className={`mt-5 text-center text-[10px] uppercase tracking-[0.18em] font-bold ${
                    m.highlight ? "text-accent-cyan" : "text-muted-foreground"
                  }`}
                >
                  {m.label}
                </div>
                <ul className="mt-3 space-y-1 text-sm text-center">
                  {m.items.map((it) => (
                    <li
                      key={it}
                      className={m.status === "done" ? "text-foreground/90" : "text-muted-foreground"}
                    >
                      {it}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* 3 KPIs */}
        <div className="grid grid-cols-3 gap-5 max-w-4xl mx-auto">
          <BigNumber value="331" label="testes verdes" icon={<BadgeCheck />} />
          <BigNumber value="15" label="migrations versionadas" icon={<Database />} />
          <BigNumber value="7" label="ADRs arquiteturais" icon={<FileCheck />} />
        </div>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T2 — Compliance grid
// ═══════════════════════════════════════════════════════════════════

export function SlideT2() {
  return (
    <SlideFrame eyebrow="Compliance" ariaLabel="Slide 2: compliance como base">
      <div className="max-w-6xl w-full space-y-10">
        <div className="text-center space-y-3">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            Compliance como{" "}
            <span className="accent-gradient-text">base</span>, não adendo.
          </h2>
          <p className="text-lg text-muted-foreground">
            4 marcos regulatórios brasileiros embutidos na arquitetura.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <ComplianceCard
            icon={<Shield className="h-6 w-6" />}
            law="LGPD"
            fullName="Lei 13.709/2018"
            accent="cyan"
            points={[
              "Criptografia fim-a-fim",
              "Consent versionado + timestamp imutável",
              "Audit chain hash-linked",
              "DPO nomeado · ANPD-ready",
            ]}
          />
          <ComplianceCard
            icon={<Stethoscope className="h-6 w-6" />}
            law="CFM 2.314/2022"
            fullName="Telemedicina + IA em saúde"
            accent="teal"
            points={[
              "IA nunca diagnostica",
              "IA nunca prescreve",
              "Constituição Sofia no system prompt",
              "Médicos com CRM ativo",
            ]}
          />
          <ComplianceCard
            icon={<HeartPulse className="h-6 w-6" />}
            law="Estatuto do Idoso"
            fullName="Lei 10.741/2003"
            accent="attention"
            points={[
              "Detector de elder abuse",
              "Escala Disque 100 em <60s",
              "Autonomia do idoso preservada",
              "Payer ≠ beneficiary",
            ]}
          />
          <ComplianceCard
            icon={<ShoppingBag className="h-6 w-6" />}
            law="CDC"
            fullName="Lei 8.078/1990"
            accent="routine"
            points={[
              "7 dias de arrependimento",
              "Zero fidelidade",
              "Cancelamento livre a qualquer momento",
              "Preço transparente",
            ]}
          />
        </div>

        <div className="flex items-center justify-center gap-3">
          <span className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan text-sm font-semibold">
            <BadgeCheck className="h-4 w-4" />
            ANVISA RDC 657/2022 — Classe B (SaMD)
          </span>
        </div>

        <p className="text-center text-muted-foreground text-lg italic">
          "Quando a norma muda, mudamos 1 configuração. Não refatoramos sistema."
        </p>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T3 — FHIR
// ═══════════════════════════════════════════════════════════════════

export function SlideT3() {
  const mappings = [
    ["aia_health_patients", "Patient"],
    ["aia_health_caregivers", "Practitioner"],
    ["aia_health_vital_signs", "Observation (LOINC)"],
    ["aia_health_reports", "Observation + Communication"],
    ["aia_health_care_events", "Encounter (virtual)"],
    ["aia_health_medication_*", "Medication* (RxNorm)"],
    ["aia_health_teleconsulta", "Encounter + DocumentRef"],
  ];

  return (
    <SlideFrame eyebrow="Interoperabilidade" ariaLabel="Slide 3: FHIR HL7">
      <div className="max-w-6xl w-full space-y-10">
        <div className="text-center space-y-3">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            FHIR HL7 é nosso{" "}
            <span className="accent-gradient-text">padrão interno</span>, não adaptador.
          </h2>
          <p className="text-lg text-muted-foreground">
            Pronto pra conversar com qualquer sistema clínico do mundo.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] items-center gap-5">
          {/* Esquerda — nosso schema */}
          <div className="glass-card rounded-2xl p-5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-semibold mb-3">
              Schema ConnectaIACare
            </div>
            <ul className="space-y-1.5 font-mono text-sm">
              {mappings.map(([from]) => (
                <li key={from} className="text-accent-cyan">
                  {from}
                </li>
              ))}
            </ul>
          </div>

          {/* Seta */}
          <div className="hidden lg:block">
            <div className="relative w-24 h-16 flex items-center justify-center">
              <div className="absolute inset-x-0 top-1/2 h-0.5 accent-gradient -translate-y-1/2" />
              <div className="absolute right-0 top-1/2 w-0 h-0 border-l-[10px] border-l-accent-teal border-y-[6px] border-y-transparent -translate-y-1/2" />
            </div>
          </div>

          {/* Direita — FHIR */}
          <div className="glass-card rounded-2xl p-5 accent-gradient-border">
            <div className="text-[10px] uppercase tracking-[0.18em] text-accent-teal font-semibold mb-3">
              FHIR R4
            </div>
            <ul className="space-y-1.5 font-mono text-sm">
              {mappings.map(([, to]) => (
                <li key={to} className="text-foreground">
                  {to}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <SealBadge
            icon={<FileCheck className="h-4 w-4" />}
            title="Exportador FHIR $everything"
            subtitle="Q3/2026"
          />
          <SealBadge
            icon={<Layers className="h-4 w-4" />}
            title="Terminologias"
            subtitle="LOINC · CID-10 · SNOMED · RxNorm"
          />
          <SealBadge
            icon={<Hospital className="h-4 w-4" />}
            title="TASY · Philips · Unimed"
            subtitle="Bridge pronta"
          />
        </div>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T4 — Mapa readiness
// ═══════════════════════════════════════════════════════════════════

export function SlideT4() {
  const countries = [
    { flag: "🇧🇷", name: "Brasil", pct: 100, law: "LGPD · CFM · ANVISA", status: "production" },
    { flag: "🇦🇷", name: "Argentina", pct: 95, law: "Lei 25.326 + GDPR-adequated", status: "ready" },
    { flag: "🇲🇽", name: "México", pct: 90, law: "LFPDPPP ≈ LGPD", status: "ready" },
    { flag: "🇨🇴", name: "Colômbia", pct: 90, law: "Lei 1581", status: "ready" },
    { flag: "🇨🇱", name: "Chile", pct: 85, law: "Lei 19.628", status: "ready" },
    { flag: "🇵🇹", name: "Portugal · UE", pct: 75, law: "GDPR 90% overlap LGPD", status: "preparing" },
    { flag: "🇺🇸", name: "EUA", pct: 60, law: "HIPAA estrutural (falta SOC 2)", status: "preparing" },
  ];

  return (
    <SlideFrame eyebrow="Expansão" ariaLabel="Slide 4: readiness por país">
      <div className="max-w-6xl w-full space-y-10">
        <div className="text-center space-y-3">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            Uma plataforma,{" "}
            <span className="accent-gradient-text">múltiplas jurisdições</span>.
          </h2>
          <p className="text-lg text-muted-foreground">
            LatAm, Europa e EUA sem refatoração.
          </p>
        </div>

        <div className="space-y-2">
          {countries.map((c) => (
            <div
              key={c.name}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-4 p-3 rounded-xl solid-card"
            >
              <div className="text-4xl">{c.flag}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-3">
                  <span className="text-lg font-bold">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.law}</span>
                </div>
                <div className="mt-1.5 h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      c.status === "production"
                        ? "bg-classification-routine glow-teal"
                        : c.status === "ready"
                          ? "accent-gradient"
                          : "bg-classification-attention"
                    }`}
                    style={{ width: `${c.pct}%` }}
                  />
                </div>
              </div>
              <div
                className={`text-xl font-bold tabular ${
                  c.status === "production"
                    ? "text-classification-routine"
                    : c.status === "ready"
                      ? "text-accent-cyan"
                      : "text-classification-attention"
                }`}
              >
                {c.pct}%
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <FeatureChip icon={<Globe2 className="h-3.5 w-3.5" />} label="Multi-tenant" hint="ADR-010" />
          <FeatureChip icon={<Mic className="h-3.5 w-3.5" />} label="Multi-locale" hint="BCP-47 · ICU" />
          <FeatureChip icon={<CreditCard className="h-3.5 w-3.5" />} label="Multi-moeda" hint="ISO 4217" />
          <FeatureChip icon={<Cloud className="h-3.5 w-3.5" />} label="Data residency" hint="BR · EU · US" />
        </div>

        <p className="text-center text-xl font-bold accent-gradient-text">
          8-12 semanas pra lançar em novo país. Sem refatoração.
        </p>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T5 — LLM Router
// ═══════════════════════════════════════════════════════════════════

export function SlideT5() {
  const providers = [
    { name: "Claude Sonnet 4", tasks: "SOAP · Rx Valid.", color: "cyan" },
    { name: "GPT-5.4", tasks: "Weekly · Intent", color: "teal" },
    { name: "Gemini 2.5", tasks: "Visão · Embedding", color: "purple" },
    { name: "DeepSeek", tasks: "Fallback · On-prem", color: "attention" },
  ];

  return (
    <SlideFrame eyebrow="Vendor-agnostic" ariaLabel="Slide 5: LLM router">
      <div className="max-w-6xl w-full space-y-10">
        <div className="text-center space-y-3">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            Nunca reféns de{" "}
            <span className="accent-gradient-text">fornecedor de IA</span>.
          </h2>
          <p className="text-lg text-muted-foreground">
            Router por tarefa + fallback cascade + config-as-data.
          </p>
        </div>

        {/* Router visual */}
        <div className="glass-card rounded-2xl p-8 relative">
          {/* Router central */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-3 px-6 py-4 rounded-xl accent-gradient text-slate-900 font-bold shadow-[0_0_40px_rgba(49,225,255,0.3)]">
              <Brain className="h-6 w-6" strokeWidth={2.5} />
              <span className="text-lg">LLM Router · por tarefa</span>
            </div>
          </div>

          {/* Linhas decorativas */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {providers.map((p) => (
              <div key={p.name} className="text-center">
                <div className="relative mb-3">
                  <div
                    aria-hidden
                    className="absolute left-1/2 top-0 w-px h-8 -translate-y-8 bg-gradient-to-b from-accent-cyan/40 to-transparent"
                  />
                </div>
                <div className="solid-card rounded-xl p-4 h-full">
                  <div className="font-bold text-sm mb-1">{p.name}</div>
                  <div className="text-[11px] text-muted-foreground">{p.tasks}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Fallback cascade */}
          <div className="mt-6 flex items-center justify-center gap-2 text-sm">
            <span className="text-muted-foreground">Se 1 cai:</span>
            <ArrowRight />
            <span className="text-accent-cyan font-semibold">próximo entra</span>
            <ArrowRight />
            <span className="text-classification-routine font-semibold">usuário nem percebe</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-5xl mx-auto">
          <BenefitCard
            title="Custo otimizado"
            desc="Tarefa simples usa modelo barato, crítica usa top."
          />
          <BenefitCard
            title="Fallback cascade"
            desc="1 provedor cai, outro entra, zero downtime."
          />
          <BenefitCard
            title="Migração em 1 config"
            desc="Troca YAML, restart container, zero code change."
          />
        </div>

        <div className="text-center">
          <div className="inline-flex items-baseline gap-3 px-6 py-3 rounded-xl glass-card">
            <span className="text-3xl font-bold tabular text-accent-cyan">$15–53</span>
            <span className="text-sm text-muted-foreground">custo real LLM/mês</span>
            <span className="text-muted-foreground/40 mx-2">vs</span>
            <span className="text-lg text-muted-foreground/70 line-through tabular">$300–500</span>
            <span className="text-sm text-muted-foreground">só Claude</span>
          </div>
        </div>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T6 — Hub
// ═══════════════════════════════════════════════════════════════════

export function SlideT6() {
  return (
    <SlideFrame eyebrow="Integrações" ariaLabel="Slide 6: hub de integrações">
      <div className="max-w-6xl w-full space-y-10">
        <div className="text-center space-y-3">
          <h2 className="text-5xl lg:text-6xl font-bold leading-tight">
            Ecossistema{" "}
            <span className="accent-gradient-text">aberto</span>.
          </h2>
          <p className="text-lg text-muted-foreground">
            Já conversamos com tudo que importa.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <IntegrationCluster
            title="Aferição"
            icon={<Watch className="h-5 w-5" />}
            items={[
              { icon: <Mic className="h-3 w-3" />, label: "Deepgram STT pt-BR" },
              { icon: <Radio className="h-3 w-3" />, label: "ElevenLabs TTS" },
              { icon: <Users className="h-3 w-3" />, label: "Resemblyzer (biometria voz)" },
              { icon: <Watch className="h-3 w-3" />, label: "Apple Health · Android Health" },
              { icon: <BellRing className="h-3 w-3" />, label: "Tecnosenior IoT (SOS)" },
              { icon: <Hospital className="h-3 w-3" />, label: "MedMonitor (clínico)" },
            ]}
          />
          <IntegrationCluster
            title="Canais"
            icon={<Phone className="h-5 w-5" />}
            items={[
              { icon: <Phone className="h-3 w-3" />, label: "WhatsApp (Evolution)" },
              { icon: <Radio className="h-3 w-3" />, label: "Alexa Skills · Q4" },
              { icon: <Phone className="h-3 w-3" />, label: "Voice Native · Q4" },
              { icon: <Globe2 className="h-3 w-3" />, label: "Web (Next.js 14)" },
            ]}
          />
          <IntegrationCluster
            title="Institucional"
            icon={<Landmark className="h-5 w-5" />}
            items={[
              { icon: <AlertCircle className="h-3 w-3" />, label: "CVV 188" },
              { icon: <Phone className="h-3 w-3" />, label: "Disque 100" },
              { icon: <BellRing className="h-3 w-3" />, label: "SAMU 192" },
              { icon: <ShieldCheck className="h-3 w-3" />, label: "CFM · ANPD · ANVISA" },
            ]}
          />
          <IntegrationCluster
            title="Complementares"
            icon={<Network className="h-5 w-5" />}
            items={[
              { icon: <CreditCard className="h-3 w-3" />, label: "Asaas + Mercado Pago (PSP)" },
              { icon: <Video className="h-3 w-3" />, label: "LiveKit WebRTC" },
              { icon: <Mail className="h-3 w-3" />, label: "Google Workspace" },
              { icon: <Brain className="h-3 w-3" />, label: "Anthropic · OpenAI · Google" },
            ]}
          />
        </div>

        <div className="flex items-center justify-center">
          <span className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan text-sm font-semibold">
            <Hospital className="h-4 w-4" />
            FHIR HL7 bridge · operadoras · ILPIs · hospitais · SUS Q2/2027
          </span>
        </div>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Slide T7 — Transição pra demo
// ═══════════════════════════════════════════════════════════════════

export function SlideT7() {
  return (
    <SlideFrame eyebrow="Por que isso importa" ariaLabel="Slide 7: gancho pra demo">
      <div className="max-w-5xl w-full space-y-14 text-center">
        <h2 className="text-4xl lg:text-5xl font-bold leading-tight">
          Não é sobre IA.
          <br />
          <span className="accent-gradient-text">
            É sobre cuidado com infraestrutura séria
          </span>
          <br />
          o suficiente pra sustentar{" "}
          <span className="text-accent-cyan">10 milhões</span> de idosos.
        </h2>

        <div className="space-y-4">
          <div className="flex items-center justify-center gap-6 flex-wrap">
            <div className="text-center">
              <div className="text-sm uppercase tracking-wider text-muted-foreground font-semibold">
                2025
              </div>
              <div className="text-6xl font-bold tabular text-foreground/80">31M</div>
              <div className="text-xs text-muted-foreground">idosos no Brasil</div>
            </div>
            <div className="text-5xl text-accent-cyan/40">→</div>
            <div className="text-center">
              <div className="text-sm uppercase tracking-wider text-accent-cyan font-semibold">
                2040
              </div>
              <div className="text-7xl font-bold tabular accent-gradient-text">57M</div>
              <div className="text-xs text-muted-foreground">projeção IBGE</div>
            </div>
          </div>

          <p className="text-xl font-bold text-foreground/90">
            O mercado vai dobrar. A tecnologia tem que estar pronta antes.
          </p>
        </div>

        <p className="text-lg text-muted-foreground italic pt-6">
          Agora deixa eu te mostrar isso funcionando.
        </p>
      </div>
    </SlideFrame>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Utility components
// ═══════════════════════════════════════════════════════════════════

function SlideFrame({
  eyebrow,
  children,
  ariaLabel,
}: {
  eyebrow: string;
  children: React.ReactNode;
  ariaLabel?: string;
}) {
  return (
    <section
      className="min-h-[calc(100vh-120px)] flex items-center justify-center py-12 px-4 animate-fade-up"
      aria-label={ariaLabel}
    >
      <div className="relative w-full flex flex-col items-center">
        <div className="absolute top-0 left-0 text-[10px] uppercase tracking-[0.18em] text-accent-cyan/70 font-bold">
          {eyebrow}
        </div>
        {children}
      </div>
    </section>
  );
}

function BigNumber({
  value,
  label,
  icon,
}: {
  value: string;
  label: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="glass-card rounded-2xl p-6 text-center">
      {icon && (
        <div className="w-10 h-10 rounded-xl mx-auto mb-3 accent-gradient flex items-center justify-center text-slate-900">
          {icon}
        </div>
      )}
      <div className="text-5xl font-bold tabular accent-gradient-text leading-none">
        {value}
      </div>
      <div className="text-sm text-muted-foreground mt-2 uppercase tracking-wider">
        {label}
      </div>
    </div>
  );
}

function ComplianceCard({
  icon,
  law,
  fullName,
  accent,
  points,
}: {
  icon: React.ReactNode;
  law: string;
  fullName: string;
  accent: "cyan" | "teal" | "routine" | "attention";
  points: string[];
}) {
  const accentMap: Record<string, { border: string; icon: string; text: string }> = {
    cyan: {
      border: "border-accent-cyan/35",
      icon: "text-accent-cyan bg-accent-cyan/10",
      text: "text-accent-cyan",
    },
    teal: {
      border: "border-accent-teal/35",
      icon: "text-accent-teal bg-accent-teal/10",
      text: "text-accent-teal",
    },
    routine: {
      border: "border-classification-routine/35",
      icon: "text-classification-routine bg-classification-routine/10",
      text: "text-classification-routine",
    },
    attention: {
      border: "border-classification-attention/35",
      icon: "text-classification-attention bg-classification-attention/10",
      text: "text-classification-attention",
    },
  };
  const a = accentMap[accent];

  return (
    <div className={`glass-card rounded-2xl p-5 border ${a.border}`}>
      <div className="flex items-center gap-3 mb-4">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${a.icon}`}>
          {icon}
        </div>
        <div>
          <div className={`text-xl font-bold ${a.text}`}>{law}</div>
          <div className="text-xs text-muted-foreground">{fullName}</div>
        </div>
      </div>
      <ul className="space-y-1.5">
        {points.map((p) => (
          <li key={p} className="flex items-start gap-2 text-sm text-foreground/85">
            <span className={`mt-1 w-1 h-1 rounded-full flex-shrink-0 ${a.text.replace("text-", "bg-")}`} />
            <span>{p}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SealBadge({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="solid-card rounded-xl p-3 flex items-center gap-3">
      <div className="w-8 h-8 rounded-md bg-accent-cyan/10 text-accent-cyan flex items-center justify-center">
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold truncate">{title}</div>
        <div className="text-[11px] text-muted-foreground truncate">{subtitle}</div>
      </div>
    </div>
  );
}

function FeatureChip({
  icon,
  label,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  hint: string;
}) {
  return (
    <div className="solid-card rounded-xl p-3 text-center">
      <div className="w-7 h-7 rounded-md mx-auto mb-2 bg-accent-cyan/10 text-accent-cyan flex items-center justify-center">
        {icon}
      </div>
      <div className="text-sm font-semibold">{label}</div>
      <div className="text-[10px] text-muted-foreground mt-0.5 uppercase tracking-wider">
        {hint}
      </div>
    </div>
  );
}

function BenefitCard({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="solid-card rounded-xl p-4 text-center">
      <div className="text-base font-bold accent-gradient-text mb-1">{title}</div>
      <div className="text-sm text-muted-foreground">{desc}</div>
    </div>
  );
}

function IntegrationCluster({
  title,
  icon,
  items,
}: {
  title: string;
  icon: React.ReactNode;
  items: Array<{ icon: React.ReactNode; label: string }>;
}) {
  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-md accent-gradient text-slate-900 flex items-center justify-center">
          {icon}
        </div>
        <h3 className="text-sm font-bold uppercase tracking-wider">{title}</h3>
      </div>
      <ul className="space-y-1.5">
        {items.map((it) => (
          <li key={it.label} className="flex items-center gap-2 text-xs text-foreground/85">
            <span className="text-muted-foreground">{it.icon}</span>
            <span>{it.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ArrowRight() {
  return (
    <svg
      className="inline-block w-5 h-5 text-muted-foreground"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}
