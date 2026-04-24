"use client";

import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Activity,
  Building2,
  Filter,
  Search,
  Users,
  X,
} from "lucide-react";

import { calcAge } from "@/lib/utils";
import type { Patient } from "@/lib/api";

interface Props {
  patients: Patient[];
}

type CareLevel = "autonomo" | "semi_dependente" | "dependente";

// ══════════════════════════════════════════════════════════════════
// Lista reativa de pacientes com busca + filtros
// ══════════════════════════════════════════════════════════════════

export function PatientsList({ patients }: Props) {
  const [query, setQuery] = useState("");
  const [careLevel, setCareLevel] = useState<CareLevel | null>(null);
  const [unit, setUnit] = useState<string | null>(null);
  const [conditionFilter, setConditionFilter] = useState<string | null>(null);

  // ─── Derivar listas únicas pra filtros ───────────────────────
  const units = useMemo(() => {
    const set = new Set<string>();
    patients.forEach((p) => p.care_unit && set.add(p.care_unit));
    return Array.from(set).sort();
  }, [patients]);

  const commonConditions = useMemo(() => {
    const counts: Record<string, number> = {};
    patients.forEach((p) => {
      (p.conditions || []).forEach((c) => {
        const name = c.description.toLowerCase();
        counts[name] = (counts[name] || 0) + 1;
      });
    });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([name]) => name);
  }, [patients]);

  // ─── Filtragem ──────────────────────────────────────────────
  const filtered = useMemo(() => {
    let list = patients;

    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (p) =>
          p.full_name.toLowerCase().includes(q) ||
          (p.nickname || "").toLowerCase().includes(q) ||
          (p.room_number || "").toLowerCase().includes(q) ||
          (p.care_unit || "").toLowerCase().includes(q),
      );
    }

    if (careLevel) {
      list = list.filter((p) => p.care_level === careLevel);
    }

    if (unit) {
      list = list.filter((p) => p.care_unit === unit);
    }

    if (conditionFilter) {
      list = list.filter((p) =>
        (p.conditions || []).some((c) =>
          c.description.toLowerCase().includes(conditionFilter),
        ),
      );
    }

    return list;
  }, [patients, query, careLevel, unit, conditionFilter]);

  const hasActiveFilters =
    !!query || !!careLevel || !!unit || !!conditionFilter;

  const clearAll = () => {
    setQuery("");
    setCareLevel(null);
    setUnit(null);
    setConditionFilter(null);
  };

  return (
    <div className="space-y-4">
      {/* Barra de busca + filtros */}
      <section className="glass-card rounded-2xl p-4 space-y-3">
        {/* Busca */}
        <div className="relative">
          <Search
            className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/70"
            aria-hidden
          />
          <input
            type="search"
            placeholder="Buscar por nome, apelido, quarto ou unidade…"
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

        {/* Filtros chips */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1">
            <Filter className="h-3 w-3" />
            Filtros:
          </span>

          {/* Care level */}
          <FilterChip
            label="Autônomo"
            active={careLevel === "autonomo"}
            onClick={() =>
              setCareLevel(careLevel === "autonomo" ? null : "autonomo")
            }
            icon={<Activity className="h-3 w-3" />}
            colorKey="routine"
          />
          <FilterChip
            label="Semi-dep."
            active={careLevel === "semi_dependente"}
            onClick={() =>
              setCareLevel(
                careLevel === "semi_dependente" ? null : "semi_dependente",
              )
            }
            icon={<Activity className="h-3 w-3" />}
            colorKey="attention"
          />
          <FilterChip
            label="Dependente"
            active={careLevel === "dependente"}
            onClick={() =>
              setCareLevel(careLevel === "dependente" ? null : "dependente")
            }
            icon={<Activity className="h-3 w-3" />}
            colorKey="urgent"
          />

          {/* Separador visual */}
          <span className="w-px h-5 bg-white/10 mx-1" aria-hidden />

          {/* Unidades (se houver >1) */}
          {units.length > 1 && (
            <select
              value={unit ?? ""}
              onChange={(e) => setUnit(e.target.value || null)}
              className="bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs focus:border-accent-cyan/50 focus:outline-none"
              aria-label="Filtrar por unidade"
            >
              <option value="">Todas as unidades</option>
              {units.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          )}

          {/* Condições mais comuns */}
          {commonConditions.length > 0 && (
            <>
              <span className="w-px h-5 bg-white/10 mx-1" aria-hidden />
              {commonConditions.slice(0, 4).map((c) => (
                <FilterChip
                  key={c}
                  label={capitalize(c)}
                  active={conditionFilter === c}
                  onClick={() => setConditionFilter(conditionFilter === c ? null : c)}
                />
              ))}
            </>
          )}

          {/* Limpar */}
          {hasActiveFilters && (
            <button
              onClick={clearAll}
              className="ml-auto text-[11px] text-muted-foreground hover:text-accent-cyan transition-colors underline-offset-2 hover:underline"
            >
              limpar filtros
            </button>
          )}
        </div>
      </section>

      {/* Contador de resultados */}
      {hasActiveFilters && (
        <div className="text-xs text-muted-foreground">
          Mostrando{" "}
          <span className="text-foreground font-semibold tabular">
            {filtered.length}
          </span>{" "}
          de{" "}
          <span className="text-foreground font-semibold tabular">
            {patients.length}
          </span>{" "}
          paciente{patients.length !== 1 ? "s" : ""}
        </div>
      )}

      {/* Grid de pacientes */}
      {filtered.length === 0 ? (
        <div className="glass-card rounded-2xl p-10 text-center">
          <Users className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
          <div className="text-base font-semibold">
            {patients.length === 0
              ? "Nenhum paciente cadastrado"
              : "Nenhum paciente corresponde aos filtros"}
          </div>
          {hasActiveFilters && (
            <button
              onClick={clearAll}
              className="mt-3 text-sm text-accent-cyan hover:underline"
            >
              Limpar filtros e ver todos
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((p) => (
            <PatientCard key={p.id} patient={p} />
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Filter chip
// ══════════════════════════════════════════════════════════════════

function FilterChip({
  label,
  active,
  onClick,
  icon,
  colorKey,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
  colorKey?: "routine" | "attention" | "urgent" | "critical";
}) {
  const colorClasses = colorKey
    ? {
        routine: active
          ? "border-classification-routine/40 bg-classification-routine/10 text-classification-routine"
          : "border-white/10 text-muted-foreground hover:border-classification-routine/30",
        attention: active
          ? "border-classification-attention/40 bg-classification-attention/10 text-classification-attention"
          : "border-white/10 text-muted-foreground hover:border-classification-attention/30",
        urgent: active
          ? "border-classification-urgent/40 bg-classification-urgent/10 text-classification-urgent"
          : "border-white/10 text-muted-foreground hover:border-classification-urgent/30",
        critical: active
          ? "border-classification-critical/40 bg-classification-critical/10 text-classification-critical"
          : "border-white/10 text-muted-foreground hover:border-classification-critical/30",
      }[colorKey]
    : active
      ? "border-accent-cyan/35 bg-accent-cyan/10 text-accent-cyan"
      : "border-white/10 text-muted-foreground hover:border-accent-cyan/30 hover:text-foreground";

  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border transition-all ${colorClasses}`}
    >
      {icon}
      {label}
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════
// Patient card
// ══════════════════════════════════════════════════════════════════

function PatientCard({ patient }: { patient: Patient }) {
  const age = calcAge(patient.birth_date);
  const conditions = (patient.conditions || []).slice(0, 2);

  return (
    <Link
      href={`/patients/${patient.id}`}
      className="glass-card rounded-2xl p-5 flex items-start gap-4 group hover:border-accent-cyan/30 transition-all"
    >
      {patient.photo_url ? (
        <Image
          src={patient.photo_url}
          alt={patient.full_name}
          width={64}
          height={64}
          className="rounded-full object-cover w-16 h-16 ring-1 ring-white/10 flex-shrink-0"
        />
      ) : (
        <div className="w-16 h-16 rounded-full bg-white/[0.05] border border-white/[0.06] flex items-center justify-center flex-shrink-0">
          <Users className="h-7 w-7 text-muted-foreground" />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <h3 className="font-semibold truncate group-hover:text-accent-cyan transition-colors">
          {patient.full_name}
        </h3>
        {patient.nickname && patient.nickname !== patient.full_name && (
          <p className="text-[11px] text-muted-foreground truncate">
            "{patient.nickname}"
          </p>
        )}

        <div className="flex items-center gap-2 mt-1.5 text-[11px] text-muted-foreground">
          {age && <span className="font-medium tabular">{age} anos</span>}
          {patient.room_number && (
            <>
              <span className="opacity-40">·</span>
              <span>Qto {patient.room_number}</span>
            </>
          )}
          {patient.care_level && (
            <>
              <span className="opacity-40">·</span>
              <span className="capitalize">
                {patient.care_level.replace("_", "-")}
              </span>
            </>
          )}
        </div>

        {patient.care_unit && (
          <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground/80">
            <Building2 className="h-2.5 w-2.5" />
            <span className="truncate">{patient.care_unit}</span>
          </div>
        )}

        {conditions.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {conditions.map((c, i) => (
              <span
                key={i}
                className="text-[10px] px-1.5 py-0.5 rounded-md bg-accent-cyan/5 border border-accent-cyan/20 text-accent-cyan/90 truncate max-w-full"
              >
                {c.description}
              </span>
            ))}
            {(patient.conditions || []).length > 2 && (
              <span className="text-[10px] text-muted-foreground px-1">
                +{(patient.conditions || []).length - 2}
              </span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
