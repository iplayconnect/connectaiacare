"use client";

import { useEffect, useState } from "react";
import {
  Clock,
  Filter,
  Phone,
  Plus,
  Search,
  Stethoscope,
  UserCog,
  UserRound,
  Users,
  X,
} from "lucide-react";

import { CaregiverForm } from "@/components/equipe/caregiver-form";
import {
  type Caregiver,
  type CaregiverRole,
  deactivateCaregiver,
  listCaregivers,
} from "@/hooks/use-caregivers";

// ═══════════════════════════════════════════════════════════════
// /equipe — gestão de equipe clínica (médicos + cuidadores + técnicos)
// ═══════════════════════════════════════════════════════════════

const ROLE_LABELS: Record<CaregiverRole, string> = {
  cuidador: "Cuidador",
  enfermagem: "Enfermagem",
  tecnico: "Técnico",
  coordenador: "Coordenador",
  medico: "Médico",
};

const ROLE_COLORS: Record<CaregiverRole, { bg: string; text: string; border: string }> = {
  medico: {
    bg: "bg-accent-cyan/10",
    text: "text-accent-cyan",
    border: "border-accent-cyan/30",
  },
  enfermagem: {
    bg: "bg-accent-teal/10",
    text: "text-accent-teal",
    border: "border-accent-teal/30",
  },
  coordenador: {
    bg: "bg-classification-attention/10",
    text: "text-classification-attention",
    border: "border-classification-attention/30",
  },
  cuidador: {
    bg: "bg-classification-routine/10",
    text: "text-classification-routine",
    border: "border-classification-routine/30",
  },
  tecnico: {
    bg: "bg-purple-400/10",
    text: "text-purple-300",
    border: "border-purple-400/30",
  },
};

const ROLE_ICONS: Record<CaregiverRole, typeof UserRound> = {
  medico: Stethoscope,
  enfermagem: UserRound,
  coordenador: UserCog,
  cuidador: UserRound,
  tecnico: UserCog,
};

export default function EquipePage() {
  const [activeTab, setActiveTab] = useState<CaregiverRole | "todos">("todos");
  const [caregivers, setCaregivers] = useState<Caregiver[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [showForm, setShowForm] = useState(false);

  const refresh = async () => {
    setLoading(true);
    const r = await listCaregivers({ active: true });
    setCaregivers(r.caregivers);
    setLoading(false);
  };

  useEffect(() => {
    refresh();
  }, []);

  const filtered = caregivers.filter((c) => {
    if (activeTab !== "todos" && c.role !== activeTab) return false;
    if (query.trim()) {
      const q = query.toLowerCase();
      if (
        !c.full_name.toLowerCase().includes(q) &&
        !(c.phone || "").includes(q)
      )
        return false;
    }
    return true;
  });

  // Contagens por role
  const counts = caregivers.reduce(
    (acc, c) => {
      acc[c.role] = (acc[c.role] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  const handleDeactivate = async (id: string, name: string) => {
    if (!confirm(`Desativar ${name}? Ele não aparecerá mais na lista ativa.`))
      return;
    const ok = await deactivateCaregiver(id);
    if (ok) refresh();
  };

  return (
    <div className="space-y-6 max-w-[1400px] animate-fade-up">
      {/* Header */}
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <UserCog className="h-4 w-4 text-accent-teal" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Gestão clínica
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="accent-gradient-text">Equipe</span>
          </h1>
          <p className="text-muted-foreground mt-1">
            <span className="tabular font-medium text-foreground">
              {caregivers.length}
            </span>{" "}
            {caregivers.length === 1 ? "profissional ativo" : "profissionais ativos"}
          </p>
        </div>

        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl accent-gradient text-slate-900 font-semibold text-sm hover:shadow-[0_0_24px_rgba(49,225,255,0.35)] transition-all"
        >
          <Plus className="h-4 w-4" strokeWidth={2.5} />
          Novo cuidador
        </button>
      </header>

      {/* Tabs */}
      <section className="glass-card rounded-2xl p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          <TabButton
            label="Todos"
            count={caregivers.length}
            active={activeTab === "todos"}
            onClick={() => setActiveTab("todos")}
          />
          {(["medico", "enfermagem", "cuidador", "tecnico", "coordenador"] as const).map(
            (role) => (
              <TabButton
                key={role}
                label={ROLE_LABELS[role]}
                count={counts[role] || 0}
                active={activeTab === role}
                onClick={() => setActiveTab(role)}
                color={ROLE_COLORS[role].text}
              />
            ),
          )}
        </div>

        {/* Busca */}
        <div className="relative">
          <Search
            className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70"
            aria-hidden
          />
          <input
            type="search"
            placeholder="Buscar por nome ou telefone…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-xl pl-10 pr-10 py-2.5 text-sm focus:border-accent-cyan/50 focus:outline-none transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              aria-label="Limpar busca"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </section>

      {/* Lista */}
      {loading ? (
        <div className="glass-card rounded-2xl p-10 text-center text-muted-foreground">
          Carregando equipe…
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState hasFilter={!!query || activeTab !== "todos"} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((c) => (
            <CaregiverCard
              key={c.id}
              caregiver={c}
              onDeactivate={() => handleDeactivate(c.id, c.full_name)}
            />
          ))}
        </div>
      )}

      {/* Form modal */}
      {showForm && (
        <CaregiverForm
          onSuccess={() => {
            setShowForm(false);
            refresh();
          }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Sub-components
// ══════════════════════════════════════════════════════════════════

function TabButton({
  label,
  count,
  active,
  onClick,
  color,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all border ${
        active
          ? "border-accent-cyan/35 bg-accent-cyan/5 text-accent-cyan"
          : "border-white/10 bg-white/[0.02] text-muted-foreground hover:text-foreground"
      }`}
    >
      <span>{label}</span>
      <span
        className={`font-mono tabular ${
          active ? "text-accent-cyan" : color ?? "text-muted-foreground/60"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function CaregiverCard({
  caregiver,
  onDeactivate,
}: {
  caregiver: Caregiver;
  onDeactivate: () => void;
}) {
  const color = ROLE_COLORS[caregiver.role];
  const Icon = ROLE_ICONS[caregiver.role];
  const initials = caregiver.full_name
    .split(" ")
    .filter((w) => w.length > 1)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  return (
    <article className="solid-card rounded-xl p-4 flex gap-3 group hover:border-accent-cyan/30 transition-colors">
      <div
        className={`w-12 h-12 rounded-full flex items-center justify-center font-bold flex-shrink-0 border ${color.bg} ${color.text} ${color.border}`}
      >
        {initials}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold truncate">{caregiver.full_name}</h3>
            <div className={`flex items-center gap-1 mt-0.5 text-[10px] uppercase tracking-wider font-semibold ${color.text}`}>
              <Icon className="h-3 w-3" />
              {ROLE_LABELS[caregiver.role]}
              {caregiver.shift && (
                <span className="text-muted-foreground/70 ml-1 normal-case tracking-normal font-normal flex items-center gap-0.5">
                  <Clock className="h-2.5 w-2.5" />
                  {formatShift(caregiver.shift)}
                </span>
              )}
            </div>
          </div>

          <button
            onClick={onDeactivate}
            aria-label={`Desativar ${caregiver.full_name}`}
            className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-classification-critical transition-all"
            title="Desativar"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {caregiver.phone && (
          <div className="flex items-center gap-1 mt-2 text-[11px] text-muted-foreground font-mono tabular">
            <Phone className="h-3 w-3" />
            {formatPhone(caregiver.phone)}
          </div>
        )}

        {caregiver.metadata &&
          typeof caregiver.metadata === "object" &&
          "crm" in caregiver.metadata && (
            <div className="mt-1 text-[10px] text-muted-foreground uppercase tracking-wider">
              {String(caregiver.metadata.crm)}
            </div>
          )}
      </div>
    </article>
  );
}

function EmptyState({ hasFilter }: { hasFilter: boolean }) {
  return (
    <div className="glass-card rounded-2xl p-10 text-center">
      <Users className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
      <div className="text-base font-semibold">
        {hasFilter ? "Nenhum profissional encontrado" : "Equipe vazia"}
      </div>
      <div className="text-sm text-muted-foreground mt-1">
        {hasFilter
          ? "Ajuste os filtros ou cadastre um novo profissional."
          : "Cadastre o primeiro profissional da sua equipe."}
      </div>
    </div>
  );
}

function formatPhone(phone: string): string {
  const d = phone.replace(/\D/g, "");
  if (d.length === 13 && d.startsWith("55")) {
    return `+${d.slice(0, 2)} (${d.slice(2, 4)}) ${d.slice(4, 9)}-${d.slice(9)}`;
  }
  if (d.length === 11) {
    return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  }
  return phone;
}

function formatShift(shift: string): string {
  return {
    manha: "Manhã",
    tarde: "Tarde",
    noite: "Noite",
    "12x36": "12×36",
    "24h": "24h",
    plantao: "Plantão",
    flexivel: "Flexível",
  }[shift] ?? shift;
}
