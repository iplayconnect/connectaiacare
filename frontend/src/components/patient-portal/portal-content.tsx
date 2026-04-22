"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Check,
  ExternalLink,
  Heart,
  Info,
  Pill,
  RefreshCw,
  Stethoscope,
  Store,
} from "lucide-react";

type PriceOffer = {
  name: string;
  price_brl: number | null;
  pharmacy: string;
  url: string | null;
  notes: string;
};

type PriceResult = {
  medication: string;
  offers: PriceOffer[];
  confidence: string;
  notes_for_patient?: string;
  source?: string;
  source_url?: string;
};

type PortalData = {
  teleconsulta: {
    id: string;
    patient_full_name: string;
    patient_nickname: string | null;
    doctor_name: string | null;
    doctor_crm: string | null;
    signed_at: string | null;
    prescription: Array<{
      id: string;
      medication: string;
      dose?: string;
      schedule?: string;
      duration?: string;
      indication?: string;
    }>;
  };
  summary: {
    greeting?: string;
    what_happened?: string;
    main_findings?: string[];
    what_to_do_now?: Array<{ action: string; detail: string }>;
    medications_explained?: Array<{
      name: string;
      why: string;
      how_to_take: string;
      important?: string;
    }>;
    warning_signs?: string[];
    next_appointment?: string;
    supportive_message?: string;
  };
  prices: {
    results?: PriceResult[];
    error?: string;
  };
};

const apiBase = process.env.NEXT_PUBLIC_API_URL || "";

export function PortalContent({
  data,
  teleconsultaId,
  pin,
}: {
  data: PortalData;
  teleconsultaId: string;
  pin: string;
}) {
  const { teleconsulta: tc, summary, prices } = data;
  const [refreshing, setRefreshing] = useState(false);
  const [priceResults, setPriceResults] = useState<PriceResult[]>(
    prices?.results || [],
  );

  async function refreshPrices() {
    if (!pin) return;
    setRefreshing(true);
    try {
      const res = await fetch(
        `${apiBase}/api/patient-portal/${teleconsultaId}/refresh-prices`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pin }),
        },
      );
      const payload = await res.json();
      if (payload.status === "ok" && payload.prices?.results) {
        setPriceResults(payload.prices.results);
      }
    } finally {
      setRefreshing(false);
    }
  }

  const firstName =
    tc.patient_nickname ||
    (tc.patient_full_name || "").split(" ")[0] ||
    "paciente";

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#050b1f] via-[#0a1028] to-[#0d1f2b] pb-20">
      {/* Hero Header */}
      <header className="px-5 pt-8 pb-6 border-b border-white/[0.05] bg-black/10 backdrop-blur-sm">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-accent-cyan/15 border border-accent-cyan/30 flex items-center justify-center">
              <Heart className="h-4 w-4 text-accent-cyan" strokeWidth={2.5} />
            </div>
            <span className="text-[11px] uppercase tracking-[0.15em] font-semibold text-foreground/70">
              ConnectaIACare · Portal do paciente
            </span>
          </div>
          <h1 className="text-xl md:text-2xl font-semibold leading-tight">
            {summary.greeting || `Olá, ${firstName}!`}
          </h1>
          {tc.doctor_name && (
            <p className="text-[13px] text-foreground/75 mt-2">
              Teleconsulta com{" "}
              <span className="text-foreground font-medium">
                {tc.doctor_name}
              </span>
              {tc.signed_at && (
                <span className="text-foreground/60">
                  {" "}
                  · {formatDate(tc.signed_at)}
                </span>
              )}
            </p>
          )}
        </div>
      </header>

      <main className="px-5 py-6 max-w-2xl mx-auto space-y-5">
        {/* O que aconteceu */}
        <Section icon={<Stethoscope className="h-4 w-4" />} title="Como foi a consulta">
          <p className="text-[14px] text-foreground/85 leading-relaxed">
            {summary.what_happened || "A teleconsulta foi finalizada."}
          </p>

          {summary.main_findings && summary.main_findings.length > 0 && (
            <div className="mt-4 space-y-2">
              {summary.main_findings.map((finding, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2.5 text-[13px] text-foreground/80 leading-relaxed"
                >
                  <Check className="h-4 w-4 text-accent-cyan flex-shrink-0 mt-0.5" />
                  <span>{finding}</span>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* O que fazer agora */}
        {summary.what_to_do_now && summary.what_to_do_now.length > 0 && (
          <Section icon={<Check className="h-4 w-4" />} title="O que fazer agora" tone="teal">
            <ul className="space-y-3">
              {summary.what_to_do_now.map((item, i) => (
                <li
                  key={i}
                  className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3.5"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-accent-teal/20 border border-accent-teal/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <span className="text-[11px] font-bold text-accent-teal">
                        {i + 1}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[14px] font-semibold text-foreground">
                        {item.action}
                      </div>
                      <div className="text-[13px] text-foreground/75 mt-1 leading-relaxed">
                        {item.detail}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Medicamentos + preços */}
        {summary.medications_explained &&
          summary.medications_explained.length > 0 && (
            <Section
              icon={<Pill className="h-4 w-4" />}
              title="Seus medicamentos"
              tone="cyan"
              action={
                <button
                  onClick={refreshPrices}
                  disabled={refreshing}
                  className="text-[11px] text-foreground/70 hover:text-foreground inline-flex items-center gap-1 transition-colors"
                  title="Atualizar preços"
                >
                  <RefreshCw
                    className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`}
                  />
                  {refreshing ? "Atualizando…" : "Atualizar preços"}
                </button>
              }
            >
              <ul className="space-y-4">
                {summary.medications_explained.map((med, i) => {
                  // Tenta casar com a busca de preços pelo nome (loose match)
                  const prices = priceResults.find((p) =>
                    normalizeForMatch(p.medication).includes(
                      normalizeForMatch(med.name).split(" ")[0] || "",
                    ),
                  );
                  return (
                    <li
                      key={i}
                      className="rounded-xl bg-white/[0.025] border border-white/[0.06] p-4"
                    >
                      <div className="flex items-start gap-3">
                        <div className="w-10 h-10 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center flex-shrink-0">
                          <Pill className="h-5 w-5 text-accent-cyan" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-[15px] font-semibold">
                            {med.name}
                          </div>
                          <div className="text-[13px] text-foreground/75 mt-1 leading-relaxed">
                            <span className="text-accent-cyan/90 font-medium">
                              Pra que serve:{" "}
                            </span>
                            {med.why}
                          </div>
                          <div className="text-[13px] text-foreground/75 mt-1 leading-relaxed">
                            <span className="text-accent-cyan/90 font-medium">
                              Como tomar:{" "}
                            </span>
                            {med.how_to_take}
                          </div>
                          {med.important && (
                            <div className="mt-2 text-[13px] rounded-lg bg-classification-attention/10 border border-classification-attention/25 px-3 py-2 flex items-start gap-2">
                              <Info className="h-3.5 w-3.5 text-classification-attention flex-shrink-0 mt-0.5" />
                              <span className="text-classification-attention">
                                <span className="font-semibold">Atenção: </span>
                                {med.important}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Preços */}
                      {prices && prices.offers && prices.offers.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-white/[0.05]">
                          <div className="flex items-center justify-between mb-2">
                            <div className="text-[11px] uppercase tracking-[0.1em] font-semibold text-accent-cyan/80">
                              Onde encontrar com melhor preço
                            </div>
                            {prices.confidence && (
                              <ConfidenceTag level={prices.confidence} />
                            )}
                          </div>
                          <div className="space-y-1.5">
                            {prices.offers.slice(0, 4).map((offer, j) => (
                              <OfferRow key={j} offer={offer} />
                            ))}
                          </div>
                          {prices.notes_for_patient && (
                            <p className="text-[11px] text-foreground/55 italic mt-2 leading-relaxed">
                              {prices.notes_for_patient}
                            </p>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Section>
          )}

        {/* Sinais de alerta */}
        {summary.warning_signs && summary.warning_signs.length > 0 && (
          <Section
            icon={<AlertTriangle className="h-4 w-4" />}
            title="Quando voltar ao médico imediatamente"
            tone="critical"
          >
            <ul className="space-y-2">
              {summary.warning_signs.map((sign, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-[14px] text-foreground/90 leading-relaxed rounded-lg bg-classification-critical/[0.05] border border-classification-critical/20 px-3 py-2"
                >
                  <AlertTriangle className="h-4 w-4 text-classification-critical flex-shrink-0 mt-0.5" />
                  <span>{sign}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Retorno */}
        {summary.next_appointment && (
          <Section
            icon={<Stethoscope className="h-4 w-4" />}
            title="Próximo retorno"
            tone="teal"
          >
            <p className="text-[14px] text-foreground/85 leading-relaxed">
              {summary.next_appointment}
            </p>
          </Section>
        )}

        {/* Mensagem acolhedora final */}
        {summary.supportive_message && (
          <div className="mt-6 text-center">
            <p className="text-[13px] text-foreground/70 italic leading-relaxed max-w-md mx-auto">
              {summary.supportive_message}
            </p>
          </div>
        )}

        {/* Rodapé compliance */}
        <footer className="mt-10 pt-6 border-t border-white/[0.05] text-center">
          <p className="text-[11px] text-foreground/50 leading-relaxed">
            Este resumo é <span className="font-medium">pessoal e confidencial</span>.
            Gerado a partir do prontuário clínico oficial assinado por{" "}
            <span className="font-medium">{tc.doctor_name}</span>
            {tc.doctor_crm && (
              <span className="font-mono"> ({tc.doctor_crm})</span>
            )}
            .
            <br />
            LGPD · CFM 2.314/2022 · Acesso válido por 24 horas
          </p>
        </footer>
      </main>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Subcomponentes
// ═══════════════════════════════════════════════════════════════════

function Section({
  icon,
  title,
  children,
  tone = "cyan",
  action,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  tone?: "cyan" | "teal" | "critical";
  action?: React.ReactNode;
}) {
  const toneMap = {
    cyan: "bg-accent-cyan/10 border-accent-cyan/25 text-accent-cyan",
    teal: "bg-accent-teal/10 border-accent-teal/25 text-accent-teal",
    critical: "bg-classification-critical/10 border-classification-critical/25 text-classification-critical",
  };
  return (
    <section className="glass-card rounded-2xl p-5 border border-white/[0.06]">
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="flex items-center gap-2.5">
          <div
            className={`w-8 h-8 rounded-lg border flex items-center justify-center flex-shrink-0 ${toneMap[tone]}`}
          >
            {icon}
          </div>
          <h2 className="text-[16px] font-semibold">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function OfferRow({ offer }: { offer: PriceOffer }) {
  const priceStr =
    offer.price_brl != null
      ? offer.price_brl.toLocaleString("pt-BR", {
          style: "currency",
          currency: "BRL",
        })
      : null;

  return (
    <div className="flex items-center gap-3 rounded-lg bg-white/[0.02] border border-white/[0.04] px-3 py-2.5 hover:border-white/[0.1] transition-colors">
      <div className="w-8 h-8 rounded-lg bg-white/[0.04] flex items-center justify-center flex-shrink-0">
        <Store className="h-4 w-4 text-foreground/70" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-medium text-foreground truncate">
          {offer.pharmacy}
        </div>
        <div className="text-[11px] text-foreground/60 truncate">
          {offer.name}
          {offer.notes && <span className="text-foreground/50"> · {offer.notes}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {priceStr && (
          <div className="text-[14px] font-bold tabular text-accent-cyan whitespace-nowrap">
            {priceStr}
          </div>
        )}
        {offer.url && (
          <a
            href={offer.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground/60 hover:text-accent-cyan p-1"
            title="Ver oferta"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </div>
  );
}

function ConfidenceTag({ level }: { level: string }) {
  const cfg =
    level === "high"
      ? {
          label: "atualizado",
          cls: "bg-classification-routine/15 border-classification-routine/25 text-classification-routine",
        }
      : level === "low"
      ? {
          label: "estimativa",
          cls: "bg-classification-attention/15 border-classification-attention/30 text-classification-attention",
        }
      : {
          label: "consultado",
          cls: "bg-white/[0.04] border-white/[0.08] text-foreground/70",
        };
  return (
    <span
      className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded border font-semibold ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function normalizeForMatch(s: string): string {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ");
}
