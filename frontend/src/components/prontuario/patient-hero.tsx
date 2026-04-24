import { AlertCircle, HeartPulse, MapPin, Users } from "lucide-react";

import {
  type Condition,
  type Patient,
  patientAge,
  type ResponsibleFamily,
} from "../../../../exploracoes/mocks/patients";

interface Props {
  patient: Patient;
  acgScore?: { value: number; label: string };
}

/**
 * Hero do Prontuário 360° — cartão principal com identidade do paciente.
 *
 * Mostra:
 *   - Avatar + nome + idade + unidade
 *   - Comorbidades com badge de controle (verde/âmbar/vermelho)
 *   - Alergias em destaque vermelho
 *   - Score ACG (Adjusted Clinical Groups) com cor por faixa
 *   - Cuidador primário + plano ativo
 *
 * Não depende de hooks — recebe tudo via props.
 */
export function PatientHero({ patient, acgScore }: Props) {
  const age = patientAge(patient);
  const primaryResp = patient.responsible.find((r) => r.is_primary);

  return (
    <section
      className="glass-card rounded-2xl p-6 lg:p-8 relative overflow-hidden"
      aria-label={`Identificação do paciente ${patient.full_name}`}
    >
      {/* Gradient glow decorativo */}
      <div
        aria-hidden
        className="absolute -top-32 -right-20 w-96 h-96 rounded-full opacity-20 blur-3xl"
        style={{
          background:
            "radial-gradient(circle, rgba(49,225,255,0.35) 0%, rgba(20,184,166,0.15) 50%, transparent 80%)",
        }}
      />

      <div className="relative flex flex-col lg:flex-row gap-6 lg:gap-8">
        {/* Avatar + identidade */}
        <div className="flex items-center gap-5 lg:gap-6 lg:min-w-[360px]">
          <AvatarBlock patient={patient} />
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl lg:text-3xl font-bold leading-tight">
              {patient.full_name}
            </h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm text-muted-foreground">
              {patient.nickname && (
                <span className="text-foreground/80">"{patient.nickname}"</span>
              )}
              <span className="tabular font-semibold text-foreground">
                {age} anos
              </span>
              <span className="capitalize">
                {patient.gender === "F" ? "Feminino" : patient.gender === "M" ? "Masculino" : "—"}
              </span>
            </div>

            {patient.care_unit && (
              <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                <MapPin className="h-3 w-3" aria-hidden />
                <span>{patient.care_unit}</span>
                {patient.room_number && (
                  <span className="text-foreground/70">· Quarto {patient.room_number}</span>
                )}
              </div>
            )}

            {patient.care_level && (
              <div className="mt-3 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] uppercase tracking-wider font-semibold border border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan">
                {patient.care_level === "autonomo"
                  ? "Autônomo"
                  : patient.care_level === "semi_dependente"
                    ? "Semi-dependente"
                    : "Dependente"}
              </div>
            )}
          </div>
        </div>

        {/* Divisor */}
        <div className="hidden lg:block w-px bg-gradient-to-b from-transparent via-white/10 to-transparent" />

        {/* Condições + alergias + ACG + cuidador */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-5">
          <ConditionsBlock conditions={patient.conditions} />
          <AllergiesBlock allergies={patient.allergies} />
          {acgScore && <ACGBlock score={acgScore} />}
          {primaryResp && <CaregiverBlock caregiver={primaryResp} />}
        </div>
      </div>
    </section>
  );
}

// ══════════════════════════════════════════════════════════════════
// Blocos internos
// ══════════════════════════════════════════════════════════════════

function AvatarBlock({ patient }: { patient: Patient }) {
  const initials = patient.full_name
    .split(" ")
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  return (
    <div className="relative flex-shrink-0">
      <div className="absolute -inset-1 accent-gradient rounded-full opacity-40 blur-md" />
      <div className="relative w-20 h-20 lg:w-24 lg:h-24 rounded-full overflow-hidden border-2 border-white/10 bg-secondary">
        {patient.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={patient.photo_url}
            alt={`Foto de ${patient.full_name}`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xl font-bold text-foreground/70">
            {initials}
          </div>
        )}
      </div>
      <div
        className="absolute bottom-0 right-0 w-4 h-4 rounded-full bg-classification-routine border-2 border-background"
        title="Estado estável"
        aria-label="Estado atual: estável"
      />
    </div>
  );
}

function ConditionsBlock({ conditions }: { conditions: Condition[] }) {
  if (!conditions.length) {
    return (
      <div>
        <Label icon={<HeartPulse className="h-3.5 w-3.5" />}>Condições clínicas</Label>
        <p className="text-sm text-muted-foreground mt-1.5">Nenhuma condição registrada.</p>
      </div>
    );
  }

  return (
    <div>
      <Label icon={<HeartPulse className="h-3.5 w-3.5" />}>Condições clínicas</Label>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {conditions.map((c) => (
          <ConditionBadge key={c.name} condition={c} />
        ))}
      </div>
    </div>
  );
}

function ConditionBadge({ condition }: { condition: Condition }) {
  // Cor por status de controle
  const controlStyles = condition.controlled === false
    ? "border-classification-attention/40 bg-classification-attention/10 text-classification-attention"
    : condition.severity === "severe"
      ? "border-classification-urgent/40 bg-classification-urgent/10 text-classification-urgent"
      : "border-classification-routine/30 bg-classification-routine/8 text-classification-routine";

  return (
    <div
      className={`inline-flex flex-col items-start px-2.5 py-1 rounded-md border text-xs ${controlStyles}`}
      aria-label={`${condition.name}, ${condition.controlled === false ? "descontrolada" : "controlada"}`}
    >
      <span className="font-semibold">{condition.name}</span>
      <span className="text-[10px] opacity-80 uppercase tracking-wider">
        {condition.cid10 && <span className="font-mono">{condition.cid10}</span>}
        {condition.cid10 && condition.since && " · "}
        {condition.since && `Desde ${new Date(condition.since).getFullYear()}`}
      </span>
    </div>
  );
}

function AllergiesBlock({ allergies }: { allergies: Patient["allergies"] }) {
  if (!allergies.length) return null;

  return (
    <div>
      <Label icon={<AlertCircle className="h-3.5 w-3.5 text-classification-critical" />}>
        <span className="text-classification-critical">Alergias</span>
      </Label>
      <div className="flex flex-wrap gap-1.5 mt-2">
        {allergies.map((a) => (
          <div
            key={a.substance}
            className="inline-flex flex-col items-start px-2.5 py-1 rounded-md border text-xs border-classification-critical/45 bg-classification-critical/10 text-classification-critical"
            aria-label={`Alergia: ${a.substance}, reação ${a.reaction}`}
          >
            <span className="font-semibold">{a.substance}</span>
            {a.reaction && (
              <span className="text-[10px] opacity-80">{a.reaction}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ACGBlock({ score }: { score: { value: number; label: string } }) {
  const bandColor =
    score.value >= 75
      ? "classification-critical"
      : score.value >= 50
        ? "classification-attention"
        : "classification-routine";

  return (
    <div>
      <Label>Score ACG</Label>
      <div className="flex items-baseline gap-2 mt-2">
        <span className={`text-3xl font-bold tabular text-${bandColor}`}>
          {score.value}
        </span>
        <span className={`text-xs uppercase font-semibold tracking-wider text-${bandColor}`}>
          {score.label}
        </span>
      </div>
      <p className="text-[10px] text-muted-foreground mt-1">
        Adjusted Clinical Groups
      </p>
    </div>
  );
}

function CaregiverBlock({ caregiver }: { caregiver: ResponsibleFamily }) {
  return (
    <div>
      <Label icon={<Users className="h-3.5 w-3.5" />}>Cuidador primário</Label>
      <div className="mt-1.5">
        <div className="text-sm font-semibold">{caregiver.name}</div>
        <div className="text-xs text-muted-foreground capitalize">
          {caregiver.relationship} · {formatPhone(caregiver.phone)}
        </div>
      </div>
    </div>
  );
}

function Label({
  icon,
  children,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-semibold">
      {icon}
      <span>{children}</span>
    </div>
  );
}

function formatPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 13) {
    // 5511987654321 → +55 (11) 98765-4321
    return `+${digits.slice(0, 2)} (${digits.slice(2, 4)}) ${digits.slice(4, 9)}-${digits.slice(9)}`;
  }
  return raw;
}
