"use client";

import { useEffect, useState } from "react";
import {
  GitFork,
  Loader2,
  AlertTriangle,
  RefreshCw,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  api,
  type DrugCascade,
  type CascadeSeverity,
  ApiError,
} from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/regras-clinicas/cascadas — Visualizador read-only das
// cascatas de prescrição configuradas (dimensão 13 do motor).
// Permissão: super_admin, admin_tenant, medico, enfermeiro.
// ═══════════════════════════════════════════════════════════════════

const SEVERITY_BADGE: Record<CascadeSeverity, string> = {
  contraindicated: "bg-red-500/20 text-red-300 border-red-500/40",
  major: "bg-orange-500/20 text-orange-300 border-orange-500/40",
  moderate: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  minor: "bg-sky-500/15 text-sky-200 border-sky-500/30",
};

const SEVERITY_LABELS: Record<CascadeSeverity, string> = {
  contraindicated: "Contraindicada",
  major: "Grave",
  moderate: "Moderada",
  minor: "Leve",
};

const SEVERITY_ORDER: Record<CascadeSeverity, number> = {
  contraindicated: 0,
  major: 1,
  moderate: 2,
  minor: 3,
};

const PATTERN_LABELS = {
  a_and_c: "A + C",
  a_b_and_c: "A + B + C (triplo)",
} as const;

const SOURCE_LABELS: Record<string, string> = {
  beers_2023: "Beers 2023",
  stopp_start_v2: "STOPP/START v2",
  rochon_bmj_2017: "Rochon BMJ 2017",
  lexicomp: "Lexicomp",
  manual: "Manual",
};

export default function CascadasPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<DrugCascade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<DrugCascade | null>(null);

  const allowed = hasRole(
    user, "super_admin", "admin_tenant", "medico", "enfermeiro",
  );

  async function load() {
    setError(null);
    try {
      const r = await api.cascadesList();
      const sorted = [...r.items].sort((a, b) => {
        const so = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        if (so !== 0) return so;
        return a.name.localeCompare(b.name);
      });
      setItems(sorted);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro carregando");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (allowed) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowed]);

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm text-muted-foreground">Sem permissão.</p>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <GitFork className="h-6 w-6 text-accent-cyan" />
            Cascatas de prescrição
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
            Padrões clássicos de prescrição em cascata — droga A causa efeito
            adverso, médico prescreve droga C pra tratar em vez de suspender A.
            Detector roda automaticamente nas medicações ativas de cada paciente.
            <span className="block mt-1 text-xs">
              Padrão <span className="font-mono">A+C</span>: bate em A E em C.{" "}
              <span className="font-mono">A+B+C</span>: triplo (ex Triple Whammy).
            </span>
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
        >
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </header>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando…
        </div>
      ) : items.length === 0 ? (
        <div className="text-center p-16 text-muted-foreground border border-dashed border-white/10 rounded-lg">
          <p className="text-sm">Nenhuma cascata cadastrada.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((c) => (
            <CascadeRow
              key={c.id}
              cascade={c}
              onClick={() => setActive(c)}
            />
          ))}
        </div>
      )}

      {active && (
        <CascadeDrawer cascade={active} onClose={() => setActive(null)} />
      )}
    </div>
  );
}

function CascadeRow({
  cascade,
  onClick,
}: {
  cascade: DrugCascade;
  onClick: () => void;
}) {
  const drugSummary = (
    p: string[],
    cls: string[],
  ): string => {
    const parts: string[] = [];
    if (p?.length) parts.push(p.slice(0, 3).join(", ") + (p.length > 3 ? "…" : ""));
    if (cls?.length)
      parts.push(`[${cls.join(", ")}]`);
    return parts.join(" ") || "—";
  };

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-lg border transition hover:bg-white/[0.03] ${
        cascade.active
          ? "border-white/10 bg-white/[0.02]"
          : "border-white/5 bg-transparent opacity-60"
      }`}
    >
      <div className="flex items-start gap-3">
        <GitFork className="h-5 w-5 mt-0.5 flex-shrink-0 text-accent-cyan" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <span className="font-semibold text-sm">{cascade.name}</span>
            <span
              className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${SEVERITY_BADGE[cascade.severity]}`}
            >
              {SEVERITY_LABELS[cascade.severity]}
            </span>
            <span className="text-[11px] uppercase text-muted-foreground font-mono">
              {PATTERN_LABELS[cascade.match_pattern]}
            </span>
            {!cascade.active && (
              <span className="text-[11px] uppercase text-muted-foreground italic">
                inativa
              </span>
            )}
            <span className="text-[11px] text-muted-foreground ml-auto">
              {SOURCE_LABELS[cascade.source] || cascade.source}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mb-2 italic">
            {cascade.adverse_effect}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
            <div className="p-2 rounded bg-red-500/[0.04] border border-red-500/15">
              <div className="text-[10px] uppercase text-red-300/80 mb-0.5">
                A (ofensor)
              </div>
              <div className="font-mono text-foreground/90 truncate">
                {drugSummary(cascade.drug_a_principles, cascade.drug_a_classes)}
              </div>
            </div>
            {cascade.match_pattern === "a_b_and_c" && (
              <div className="p-2 rounded bg-amber-500/[0.04] border border-amber-500/15">
                <div className="text-[10px] uppercase text-amber-300/80 mb-0.5">
                  B (cofator)
                </div>
                <div className="font-mono text-foreground/90 truncate">
                  {drugSummary(cascade.drug_b_principles, cascade.drug_b_classes)}
                </div>
              </div>
            )}
            <div className="p-2 rounded bg-sky-500/[0.04] border border-sky-500/15">
              <div className="text-[10px] uppercase text-sky-300/80 mb-0.5">
                C (cascata)
              </div>
              <div className="font-mono text-foreground/90 truncate">
                {drugSummary(cascade.drug_c_principles, cascade.drug_c_classes)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function CascadeDrawer({
  cascade,
  onClose,
}: {
  cascade: DrugCascade;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="w-full sm:max-w-3xl max-h-[90vh] overflow-y-auto rounded-t-xl sm:rounded-xl bg-slate-900 border border-white/10 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-white/10 p-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${SEVERITY_BADGE[cascade.severity]}`}
              >
                {SEVERITY_LABELS[cascade.severity]}
              </span>
              <span className="text-[11px] uppercase text-muted-foreground font-mono">
                {PATTERN_LABELS[cascade.match_pattern]}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {SOURCE_LABELS[cascade.source] || cascade.source}
                {cascade.source_ref && ` · ${cascade.source_ref}`}
              </span>
              <span className="text-[11px] text-muted-foreground">
                conf {Math.round(cascade.confidence * 100)}%
              </span>
            </div>
            <h2 className="text-lg font-semibold">{cascade.name}</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <Field label="Efeito adverso">
            <p className="text-sm">{cascade.adverse_effect}</p>
          </Field>

          <Field label="Mecanismo da cascata">
            <p className="text-sm whitespace-pre-wrap">
              {cascade.cascade_explanation}
            </p>
          </Field>

          <Field label="Recomendação clínica">
            <p className="text-sm whitespace-pre-wrap">{cascade.recommendation}</p>
          </Field>

          {cascade.alternative && (
            <Field label="Alternativa terapêutica">
              <p className="text-sm whitespace-pre-wrap">
                {cascade.alternative}
              </p>
            </Field>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <DrugBracket
              label="A — ofensor"
              principles={cascade.drug_a_principles}
              classes={cascade.drug_a_classes}
              accent="red"
            />
            {cascade.match_pattern === "a_b_and_c" && (
              <DrugBracket
                label="B — cofator"
                principles={cascade.drug_b_principles}
                classes={cascade.drug_b_classes}
                accent="amber"
              />
            )}
            <DrugBracket
              label="C — tratamento da cascata"
              principles={cascade.drug_c_principles}
              classes={cascade.drug_c_classes}
              accent="sky"
            />
          </div>

          {cascade.exclusion_conditions && (
            <Field label="Exclusões clínicas (suprime cascata)">
              <pre className="text-xs font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(cascade.exclusion_conditions, null, 2)}
              </pre>
            </Field>
          )}
        </div>
      </div>
    </div>
  );
}

function DrugBracket({
  label,
  principles,
  classes,
  accent,
}: {
  label: string;
  principles: string[];
  classes: string[];
  accent: "red" | "amber" | "sky";
}) {
  const bg = {
    red: "bg-red-500/[0.04] border-red-500/20",
    amber: "bg-amber-500/[0.04] border-amber-500/20",
    sky: "bg-sky-500/[0.04] border-sky-500/20",
  }[accent];
  const text = {
    red: "text-red-300/90",
    amber: "text-amber-300/90",
    sky: "text-sky-300/90",
  }[accent];

  return (
    <div className={`p-3 rounded-lg border ${bg}`}>
      <div className={`text-[11px] uppercase tracking-wide mb-2 ${text}`}>
        {label}
      </div>
      {principles?.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] uppercase text-muted-foreground mb-1">
            Princípios ativos
          </div>
          <div className="flex flex-wrap gap-1">
            {principles.map((p) => (
              <span
                key={p}
                className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-white/5 border border-white/10"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      )}
      {classes?.length > 0 && (
        <div>
          <div className="text-[10px] uppercase text-muted-foreground mb-1">
            Classes terapêuticas
          </div>
          <div className="flex flex-wrap gap-1">
            {classes.map((c) => (
              <span
                key={c}
                className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-white/5 border border-white/10"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}
      {!principles?.length && !classes?.length && (
        <div className="text-xs text-muted-foreground italic">—</div>
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}
