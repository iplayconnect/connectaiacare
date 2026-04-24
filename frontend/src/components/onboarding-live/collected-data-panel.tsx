"use client";

import {
  Building2,
  Check,
  ClipboardList,
  CreditCard,
  HeartPulse,
  IdCard,
  Phone,
  Pill,
  Shield,
  User,
  UserRound,
  Users,
} from "lucide-react";

export interface CollectedData {
  role?: "self" | "family" | "caregiver";
  payer_name?: string;
  payer_cpf_last4?: string;
  beneficiary_name?: string;
  beneficiary_age?: number;
  conditions_raw?: string;
  medications_raw?: string;
  emergency_contacts_count?: number;
  address_cep?: string;
  plan_sku?: "essencial" | "familia" | "premium" | "premium_device";
  payment_method?: "credit_card" | "pix";
  consent_signed?: boolean;
}

interface Props {
  data: CollectedData;
  plan_price?: number;
}

/**
 * Painel "dados coletados" — cards que aparecem à medida que Sofia avança.
 * Cada card tem ícone + label + valor + ✓ verde quando preenchido.
 */
export function CollectedDataPanel({ data, plan_price }: Props) {
  return (
    <section className="glass-card rounded-2xl p-5">
      <header className="mb-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-semibold">
          Dados capturados
        </div>
        <h3 className="text-sm font-semibold mt-0.5">Coleta em tempo real</h3>
      </header>

      <div className="grid grid-cols-1 gap-2">
        <DataRow
          icon={<UserRound className="h-3.5 w-3.5" />}
          label="Papel"
          value={roleLabel(data.role)}
          filled={!!data.role}
        />
        <DataRow
          icon={<User className="h-3.5 w-3.5" />}
          label="Pagador"
          value={data.payer_name}
          filled={!!data.payer_name}
        />
        <DataRow
          icon={<IdCard className="h-3.5 w-3.5" />}
          label="CPF"
          value={data.payer_cpf_last4 ? `*******${data.payer_cpf_last4}` : undefined}
          valueFontMono
          filled={!!data.payer_cpf_last4}
          secure
        />
        <DataRow
          icon={<HeartPulse className="h-3.5 w-3.5" />}
          label="Beneficiário"
          value={
            data.beneficiary_name
              ? `${data.beneficiary_name}${data.beneficiary_age ? `, ${data.beneficiary_age} anos` : ""}`
              : undefined
          }
          filled={!!data.beneficiary_name}
        />
        <DataRow
          icon={<ClipboardList className="h-3.5 w-3.5" />}
          label="Condições"
          value={truncate(data.conditions_raw, 40)}
          filled={!!data.conditions_raw}
        />
        <DataRow
          icon={<Pill className="h-3.5 w-3.5" />}
          label="Medicações"
          value={truncate(data.medications_raw, 40)}
          filled={!!data.medications_raw}
        />
        <DataRow
          icon={<Users className="h-3.5 w-3.5" />}
          label="Contatos emergência"
          value={
            data.emergency_contacts_count
              ? `${data.emergency_contacts_count} contato${data.emergency_contacts_count > 1 ? "s" : ""}`
              : undefined
          }
          filled={!!data.emergency_contacts_count}
        />
        <DataRow
          icon={<Building2 className="h-3.5 w-3.5" />}
          label="Endereço"
          value={data.address_cep ? `CEP ${data.address_cep}` : undefined}
          valueFontMono
          filled={!!data.address_cep}
        />
      </div>

      {/* Divisor entre dados e compromisso comercial */}
      <div className="gradient-divider my-4" />

      <div className="grid grid-cols-1 gap-2">
        <DataRow
          icon={<ClipboardList className="h-3.5 w-3.5" />}
          label="Plano"
          value={
            data.plan_sku
              ? `${planLabel(data.plan_sku)}${plan_price ? ` · R$ ${(plan_price / 100).toFixed(2).replace(".", ",")}` : ""}`
              : undefined
          }
          filled={!!data.plan_sku}
          highlight
        />
        <DataRow
          icon={<CreditCard className="h-3.5 w-3.5" />}
          label="Pagamento"
          value={paymentLabel(data.payment_method)}
          filled={!!data.payment_method}
          highlight
        />
        <DataRow
          icon={<Shield className="h-3.5 w-3.5" />}
          label="Consentimento LGPD"
          value={data.consent_signed ? "Aceito · hash SHA-256 armazenado" : undefined}
          filled={!!data.consent_signed}
          highlight
        />
      </div>
    </section>
  );
}

// ══════════════════════════════════════════════════════════════════
// Row
// ══════════════════════════════════════════════════════════════════

function DataRow({
  icon,
  label,
  value,
  filled,
  secure,
  valueFontMono,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value?: string;
  filled: boolean;
  secure?: boolean;
  valueFontMono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div
      className={`
        flex items-center gap-2.5 px-3 py-2 rounded-md border transition-all
        ${filled
          ? highlight
            ? "border-accent-cyan/30 bg-accent-cyan/5"
            : "border-classification-routine/20 bg-classification-routine/5"
          : "border-white/5 bg-white/[0.015]"
        }
      `}
      aria-label={`${label}${filled && value ? `: ${value}` : ": não preenchido"}`}
    >
      <div
        className={`flex-shrink-0 ${
          filled ? "text-classification-routine" : "text-muted-foreground/50"
        }`}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
          {label}
        </div>
        <div
          className={`text-sm leading-tight truncate ${
            valueFontMono ? "font-mono" : ""
          } ${filled ? "text-foreground" : "text-muted-foreground/40 italic"}`}
        >
          {value ?? "—"}
          {secure && filled && (
            <span className="ml-1.5 text-[9px] uppercase tracking-wider text-accent-cyan font-semibold">
              hash LGPD
            </span>
          )}
        </div>
      </div>
      <div className="flex-shrink-0">
        {filled ? (
          <Check
            className="h-4 w-4 text-classification-routine animate-fade-up"
            strokeWidth={3}
            aria-hidden
          />
        ) : (
          <div className="w-4 h-4 rounded-full border border-white/10" />
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════

function roleLabel(role?: CollectedData["role"]): string | undefined {
  if (!role) return undefined;
  return {
    self: "Própria pessoa",
    family: "Familiar",
    caregiver: "Cuidador profissional",
  }[role];
}

function planLabel(sku: NonNullable<CollectedData["plan_sku"]>): string {
  return {
    essencial: "Essencial",
    familia: "Família",
    premium: "Premium",
    premium_device: "Premium + Dispositivo",
  }[sku];
}

function paymentLabel(m?: CollectedData["payment_method"]): string | undefined {
  if (!m) return undefined;
  return m === "credit_card" ? "Cartão (trial 7 dias)" : "PIX imediato";
}

function truncate(s?: string, n: number = 40): string | undefined {
  if (!s) return undefined;
  return s.length > n ? s.slice(0, n) + "…" : s;
}
