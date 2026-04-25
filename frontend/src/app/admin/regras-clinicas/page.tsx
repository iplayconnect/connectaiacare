"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Loader2,
  Pill,
  Plus,
  ShieldAlert,
  Stethoscope,
  Tag,
  Trash2,
  Wrench,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ═══════════════════════════════════════════════════════════════════
// /admin/regras-clinicas — CRUD do motor de cruzamentos clínicos
//
// Tabs:
//   • Visão geral (stats agregados)
//   • Doses máximas + Aliases (editáveis)
//   • Interações (editáveis, com time_separation)
//   • Outras tabelas (read-only por enquanto: alergias, contraindicações,
//     ajuste renal/hepático, fall risk, ACB, vital constraints)
// ═══════════════════════════════════════════════════════════════════

type TabKey =
  | "overview"
  | "dose-limits"
  | "aliases"
  | "interactions"
  | "allergy-mappings"
  | "condition-contraindications"
  | "renal-adjustments"
  | "hepatic-adjustments"
  | "fall-risk"
  | "anticholinergic-burden"
  | "vital-constraints";

const TABS: { key: TabKey; label: string; readonly?: boolean }[] = [
  { key: "overview", label: "Visão geral" },
  { key: "dose-limits", label: "Doses máximas" },
  { key: "aliases", label: "Aliases" },
  { key: "interactions", label: "Interações" },
  { key: "allergy-mappings", label: "Alergias", readonly: true },
  { key: "condition-contraindications", label: "Por condição", readonly: true },
  { key: "renal-adjustments", label: "Ajuste renal", readonly: true },
  { key: "hepatic-adjustments", label: "Ajuste hepático", readonly: true },
  { key: "fall-risk", label: "Risco queda", readonly: true },
  { key: "anticholinergic-burden", label: "ACB Score", readonly: true },
  { key: "vital-constraints", label: "Sinais vitais", readonly: true },
];

export default function ClinicalRulesPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("overview");

  if (!hasRole(user, "super_admin", "admin_tenant")) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Apenas admins podem gerenciar regras clínicas.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-7xl">
      <header>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Stethoscope className="h-5 w-5 text-accent-cyan" />
          Regras Clínicas — Motor de Cruzamentos
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          Catálogo determinístico que valida toda prescrição contra dose
          máxima diária, alergias, interações, contraindicações por
          condição, ajuste renal/hepático e mais. Toda edição é registrada
          no audit chain (LGPD).
        </p>
      </header>

      <nav className="flex flex-wrap gap-1.5 border-b border-white/[0.06] pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`text-xs px-3 py-1.5 rounded-md transition-all ${
              tab === t.key
                ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan"
                : "border border-transparent hover:bg-white/[0.04] text-muted-foreground"
            }`}
          >
            {t.label}
            {t.readonly && (
              <span className="ml-1 text-[9px] uppercase tracking-wider opacity-60">
                ro
              </span>
            )}
          </button>
        ))}
      </nav>

      <div>
        {tab === "overview" && <OverviewTab />}
        {tab === "dose-limits" && <DoseLimitsTab />}
        {tab === "aliases" && <AliasesTab />}
        {tab === "interactions" && <InteractionsTab />}
        {(tab !== "overview" &&
          tab !== "dose-limits" &&
          tab !== "aliases" &&
          tab !== "interactions") && <ReadonlyTab tableKey={tab} />}
      </div>
    </div>
  );
}

// ─── Overview ─────────────────────────────────────────────

function OverviewTab() {
  const [stats, setStats] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.clinicalRulesStats()
      .then((r) => setStats(r.stats))
      .catch(() => setStats({}))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <Spinner />;
  }
  if (!stats) return null;

  const cards = [
    { key: "dose_limits", label: "Doses máximas", icon: Pill },
    { key: "aliases", label: "Aliases (marcas)", icon: Tag },
    { key: "interactions", label: "Interações", icon: AlertCircle },
    { key: "allergy_mappings", label: "Alergias", icon: AlertCircle },
    { key: "condition_contraindications", label: "Por condição", icon: Stethoscope },
    { key: "renal_adjustments", label: "Ajuste renal", icon: Database },
    { key: "hepatic_adjustments", label: "Ajuste hepático", icon: Database },
    { key: "fall_risk", label: "Risco de queda", icon: AlertCircle },
    { key: "anticholinergic_burden", label: "ACB Score", icon: AlertCircle },
    { key: "vital_constraints", label: "Sinais vitais", icon: Database },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      {cards.map((c) => {
        const Icon = c.icon;
        const value = stats[c.key] ?? 0;
        return (
          <div
            key={c.key}
            className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
          >
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Icon className="h-3.5 w-3.5" />
              <span className="text-[10px] uppercase tracking-wider">
                {c.label}
              </span>
            </div>
            <div className="text-2xl font-semibold tabular">{value}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              entradas ativas
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Dose Limits ──────────────────────────────────────────

function DoseLimitsTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");

  const reload = () => {
    setLoading(true);
    api.clinicalRulesList("dose-limits")
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      [i.principle_active, i.therapeutic_class, i.source]
        .filter(Boolean).some((s: string) => s.toLowerCase().includes(q)),
    );
  }, [items, search]);

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-2 flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por princípio, classe, fonte..."
            className="input"
          />
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium shadow-glow-cyan hover:brightness-110"
        >
          <Plus className="h-3.5 w-3.5" />
          Nova dose máxima
        </button>
      </div>

      {loading ? <Spinner /> : (
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Princípio</th>
                <th className="px-3 py-2 text-left">Classe</th>
                <th className="px-3 py-2 text-left">Dose máx/dia</th>
                <th className="px-3 py-2 text-left">Beers</th>
                <th className="px-3 py-2 text-left">NTI</th>
                <th className="px-3 py-2 text-left">Fonte</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((it) => (
                <tr key={it.id} className="border-t border-white/[0.04]">
                  <td className="px-3 py-2 font-medium">{it.principle_active}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {it.therapeutic_class || "—"}
                  </td>
                  <td className="px-3 py-2 tabular">
                    {it.max_daily_dose_value} {it.max_daily_dose_unit}
                  </td>
                  <td className="px-3 py-2">
                    {it.beers_avoid && (
                      <span className="px-1.5 py-0.5 rounded bg-classification-attention/15 text-classification-attention text-[10px]">
                        AVOID
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {it.narrow_therapeutic_index && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-accent-cyan" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{it.source}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={async () => {
                        if (!confirm(`Desativar ${it.principle_active}?`)) return;
                        await api.doseLimitDelete(it.id);
                        reload();
                      }}
                      className="p-1 rounded hover:bg-classification-attention/10 text-classification-attention"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                    Sem resultados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <DoseLimitModal
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); reload(); }}
        />
      )}
    </div>
  );
}

function DoseLimitModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<any>({
    principle_active: "",
    route: "oral",
    max_daily_dose_value: "",
    max_daily_dose_unit: "mg",
    therapeutic_class: "",
    age_group_min: 60,
    beers_avoid: false,
    beers_rationale: "",
    narrow_therapeutic_index: false,
    nti_monitoring: "",
    source: "manual",
    source_ref: "",
    confidence: 0.85,
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setSaving(true);
    try {
      await api.doseLimitCreate({
        ...form,
        max_daily_dose_value: parseFloat(form.max_daily_dose_value),
        confidence: parseFloat(form.confidence),
      });
      onSaved();
    } catch (e: any) {
      setErr(e?.message || "Erro");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} title="Nova dose máxima diária">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <Input label="Princípio ativo *" value={form.principle_active}
            onChange={(v) => setForm({ ...form, principle_active: v })}
            placeholder="ex: paracetamol" />
          <Input label="Classe terapêutica" value={form.therapeutic_class}
            onChange={(v) => setForm({ ...form, therapeutic_class: v })}
            placeholder="ex: analgesico_paracetamol" />
          <Input label="Via" value={form.route}
            onChange={(v) => setForm({ ...form, route: v })} />
          <Input label="Idade mín (default 60)" type="number" value={form.age_group_min}
            onChange={(v) => setForm({ ...form, age_group_min: parseInt(v) || 60 })} />
          <Input label="Dose máx valor *" value={form.max_daily_dose_value}
            onChange={(v) => setForm({ ...form, max_daily_dose_value: v })}
            placeholder="ex: 3000" />
          <Input label="Unidade *" value={form.max_daily_dose_unit}
            onChange={(v) => setForm({ ...form, max_daily_dose_unit: v })}
            placeholder="mg | g | mcg | ml | ui" />
          <Input label="Fonte *" value={form.source}
            onChange={(v) => setForm({ ...form, source: v })}
            placeholder="anvisa | beers_2023 | sbgg | who_atc | fda | manual" />
          <Input label="Confiança 0-1" type="number" value={form.confidence}
            onChange={(v) => setForm({ ...form, confidence: v })} />
        </div>
        <Input label="Referência (URL, citação)" value={form.source_ref}
          onChange={(v) => setForm({ ...form, source_ref: v })} />
        <div className="flex items-center gap-3 text-xs">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={form.beers_avoid}
              onChange={(e) => setForm({ ...form, beers_avoid: e.target.checked })}
              className="accent-accent-cyan" />
            Beers AVOID
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" checked={form.narrow_therapeutic_index}
              onChange={(e) => setForm({ ...form, narrow_therapeutic_index: e.target.checked })}
              className="accent-accent-cyan" />
            Janela terapêutica estreita
          </label>
        </div>
        {form.beers_avoid && (
          <Input label="Motivo Beers" value={form.beers_rationale}
            onChange={(v) => setForm({ ...form, beers_rationale: v })} />
        )}
        {form.narrow_therapeutic_index && (
          <Input label="Monitorização NTI" value={form.nti_monitoring}
            onChange={(v) => setForm({ ...form, nti_monitoring: v })}
            placeholder="ex: INR alvo 2-3" />
        )}
        <Input label="Notas" value={form.notes}
          onChange={(v) => setForm({ ...form, notes: v })} />

        {err && <div className="text-xs text-classification-attention">{err}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-2">
            Cancelar
          </button>
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Criar
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Aliases ──────────────────────────────────────────────

function AliasesTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");

  const reload = () => {
    setLoading(true);
    api.clinicalRulesList("aliases")
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      [i.alias, i.principle_active].some((s: string) => s?.toLowerCase().includes(q)),
    );
  }, [items, search]);

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar marca ou princípio..."
          className="input flex-1"
        />
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
        >
          <Plus className="h-3.5 w-3.5" /> Novo alias
        </button>
      </div>
      {loading ? <Spinner /> : (
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Alias / Marca</th>
                <th className="px-3 py-2 text-left">Princípio ativo</th>
                <th className="px-3 py-2 text-left">Tipo</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((it) => (
                <tr key={it.id} className="border-t border-white/[0.04]">
                  <td className="px-3 py-2 font-medium">{it.alias}</td>
                  <td className="px-3 py-2 text-muted-foreground">{it.principle_active}</td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.05] text-[10px] uppercase tracking-wider">
                      {it.alias_type}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={async () => {
                        if (!confirm(`Remover alias "${it.alias}"?`)) return;
                        await api.aliasDelete(it.id);
                        reload();
                      }}
                      className="p-1 rounded hover:bg-classification-attention/10 text-classification-attention"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {creating && <AliasModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}
    </div>
  );
}

function AliasModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<any>({
    alias: "", principle_active: "", alias_type: "brand", notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal onClose={onClose} title="Novo alias / marca">
      <form onSubmit={async (e) => {
        e.preventDefault(); setErr(null); setSaving(true);
        try {
          await api.aliasCreate(form);
          onSaved();
        } catch (e: any) {
          setErr(e?.reason === "duplicate_alias" ? "Esse alias já existe" : e?.message);
        } finally { setSaving(false); }
      }} className="space-y-3">
        <Input label="Alias / Marca *" value={form.alias}
          onChange={(v) => setForm({ ...form, alias: v })} placeholder="ex: Tylenol" />
        <Input label="Princípio ativo *" value={form.principle_active}
          onChange={(v) => setForm({ ...form, principle_active: v })}
          placeholder="ex: paracetamol" />
        <Select label="Tipo" value={form.alias_type}
          onChange={(v) => setForm({ ...form, alias_type: v })}
          options={["brand", "synonym", "misspelling"]} />
        <Input label="Notas" value={form.notes}
          onChange={(v) => setForm({ ...form, notes: v })} />
        {err && <div className="text-xs text-classification-attention">{err}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-2">Cancelar</button>
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Criar
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Interactions ─────────────────────────────────────────

function InteractionsTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  const reload = () => {
    setLoading(true);
    api.clinicalRulesList("interactions")
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  };
  useEffect(() => { reload(); }, []);

  const filtered = useMemo(() => {
    let r = items;
    if (severityFilter) r = r.filter((i) => i.severity === severityFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter((i) =>
        [i.principle_a, i.principle_b, i.class_a, i.class_b, i.mechanism]
          .filter(Boolean).some((s: string) => s.toLowerCase().includes(q)),
      );
    }
    return r;
  }, [items, search, severityFilter]);

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por princípio, classe, mecanismo..."
          className="input flex-1 min-w-[240px]"
        />
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="input max-w-[160px]"
        >
          <option value="">Todas severidades</option>
          <option value="contraindicated">Contraindicada</option>
          <option value="major">Major</option>
          <option value="moderate">Moderate</option>
          <option value="minor">Minor</option>
        </select>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
        >
          <Plus className="h-3.5 w-3.5" /> Nova interação
        </button>
      </div>
      {loading ? <Spinner /> : (
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Lado A</th>
                <th className="px-3 py-2 text-left">Lado B</th>
                <th className="px-3 py-2 text-left">Severidade</th>
                <th className="px-3 py-2 text-left">Mecanismo</th>
                <th className="px-3 py-2 text-left">Espaçamento</th>
                <th className="px-3 py-2 text-left">Fonte</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((it) => (
                <tr key={it.id} className="border-t border-white/[0.04]">
                  <td className="px-3 py-2 font-medium">
                    {it.principle_a || it.class_a}
                  </td>
                  <td className="px-3 py-2 font-medium">
                    {it.principle_b || it.class_b}
                  </td>
                  <td className="px-3 py-2">
                    <SeverityBadge severity={it.severity} />
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{it.mechanism}</td>
                  <td className="px-3 py-2 tabular text-muted-foreground">
                    {it.time_separation_minutes
                      ? `${Math.round(it.time_separation_minutes/60*10)/10}h ${it.separation_strategy || ""}`
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{it.source}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={async () => {
                        if (!confirm("Desativar essa interação?")) return;
                        await api.interactionDelete(it.id);
                        reload();
                      }}
                      className="p-1 rounded hover:bg-classification-attention/10 text-classification-attention"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {creating && <InteractionModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); reload(); }} />}
    </div>
  );
}

function InteractionModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<any>({
    principle_a: "", principle_b: "", class_a: "", class_b: "",
    severity: "moderate", mechanism: "", clinical_effect: "",
    recommendation: "", source: "manual", confidence: 0.85,
    time_separation_minutes: "", separation_strategy: "any",
    food_warning: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  return (
    <Modal onClose={onClose} title="Nova interação">
      <form onSubmit={async (e) => {
        e.preventDefault(); setErr(null); setSaving(true);
        try {
          const body = { ...form };
          if (body.time_separation_minutes) {
            body.time_separation_minutes = parseInt(body.time_separation_minutes);
          } else {
            delete body.time_separation_minutes;
            delete body.separation_strategy;
          }
          await api.interactionCreate(body);
          onSaved();
        } catch (e: any) {
          setErr(e?.message || "Erro");
        } finally { setSaving(false); }
      }} className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-2">
          <Input label="Princípio A" value={form.principle_a}
            onChange={(v) => setForm({ ...form, principle_a: v })}
            placeholder="ou class_a" />
          <Input label="Princípio B" value={form.principle_b}
            onChange={(v) => setForm({ ...form, principle_b: v })} />
          <Input label="Classe A" value={form.class_a}
            onChange={(v) => setForm({ ...form, class_a: v })}
            placeholder="ex: analgesico_aine" />
          <Input label="Classe B" value={form.class_b}
            onChange={(v) => setForm({ ...form, class_b: v })} />
        </div>
        <Select label="Severidade *" value={form.severity}
          onChange={(v) => setForm({ ...form, severity: v })}
          options={["contraindicated", "major", "moderate", "minor"]} />
        <Input label="Mecanismo *" value={form.mechanism}
          onChange={(v) => setForm({ ...form, mechanism: v })}
          placeholder="ex: GI bleeding, CYP3A4 inhibition" />
        <Textarea label="Efeito clínico *" value={form.clinical_effect}
          onChange={(v) => setForm({ ...form, clinical_effect: v })} />
        <Textarea label="Recomendação *" value={form.recommendation}
          onChange={(v) => setForm({ ...form, recommendation: v })} />
        <div className="grid grid-cols-2 gap-2">
          <Input label="Fonte *" value={form.source}
            onChange={(v) => setForm({ ...form, source: v })}
            placeholder="beers_2023 | stockleys | lexicomp | fda | manual" />
          <Input label="Confiança 0-1" type="number" value={form.confidence}
            onChange={(v) => setForm({ ...form, confidence: parseFloat(v) || 0.85 })} />
        </div>

        <div className="border-t border-white/[0.06] pt-3 mt-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
            Mitigação por espaçamento (opcional)
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input label="Min separação (minutos)" type="number"
              value={form.time_separation_minutes}
              onChange={(v) => setForm({ ...form, time_separation_minutes: v })}
              placeholder="ex: 240 (=4h)" />
            <Select label="Estratégia" value={form.separation_strategy}
              onChange={(v) => setForm({ ...form, separation_strategy: v })}
              options={["any", "a_first", "b_first"]} />
          </div>
          <Input label="Aviso alimentar (food_warning)" value={form.food_warning}
            onChange={(v) => setForm({ ...form, food_warning: v })}
            placeholder="ex: Levotiroxina exige jejum estrito 30min" />
        </div>

        {err && <div className="text-xs text-classification-attention">{err}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-2">Cancelar</button>
          <button type="submit" disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            Criar
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Read-only tabs (visualização) ─────────────────────

function ReadonlyTab({ tableKey }: { tableKey: TabKey }) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    api.clinicalRulesList(tableKey)
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  }, [tableKey]);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      Object.values(i).some(
        (v) => typeof v === "string" && v.toLowerCase().includes(q),
      ),
    );
  }, [items, search]);

  if (loading) return <Spinner />;
  if (items.length === 0) {
    return <div className="text-muted-foreground text-xs">Sem entradas.</div>;
  }
  const columns = Object.keys(items[0]).filter(
    (k) => !["id", "active", "created_at", "updated_at"].includes(k),
  );

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-2">
        <input value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar..." className="input flex-1" />
        <span className="text-xs text-muted-foreground">
          {filtered.length} / {items.length} entradas
        </span>
      </div>
      <div className="rounded-xl border border-white/[0.06] overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-white/[0.02] text-muted-foreground">
            <tr>
              {columns.map((c) => (
                <th key={c} className="px-3 py-2 text-left whitespace-nowrap">
                  {c.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((it, idx) => (
              <tr key={it.id || idx} className="border-t border-white/[0.04]">
                {columns.map((c) => (
                  <td key={c} className="px-3 py-2 align-top">
                    <Cell value={it[c]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > 200 && (
        <div className="text-[10px] text-muted-foreground">
          Exibindo 200 de {filtered.length}. Use a busca pra refinar.
        </div>
      )}
    </div>
  );
}

function Cell({ value }: { value: any }) {
  if (value == null) return <span className="text-muted-foreground/60">—</span>;
  if (typeof value === "boolean") {
    return value ? <CheckCircle2 className="h-3.5 w-3.5 text-classification-routine" /> : <X className="h-3.5 w-3.5 text-muted-foreground/40" />;
  }
  if (typeof value === "object") {
    return <span className="font-mono text-[10px]">{JSON.stringify(value).slice(0, 80)}</span>;
  }
  const str = String(value);
  if (str.length > 90) {
    return <span title={str}>{str.slice(0, 90)}…</span>;
  }
  return <span>{str}</span>;
}

// ─── shared UI primitives ──────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = {
    contraindicated: "bg-classification-critical/15 text-classification-critical border-classification-critical/30",
    major: "bg-classification-attention/15 text-classification-attention border-classification-attention/30",
    moderate: "bg-classification-routine/10 text-classification-routine border-classification-routine/20",
    minor: "bg-white/[0.04] text-muted-foreground border-white/[0.08]",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider border ${map[severity] || ""}`}>
      {severity}
    </span>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando...
    </div>
  );
}

function Modal({ children, title, onClose }: { children: React.ReactNode; title: string; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
         onClick={onClose}>
      <div className="bg-[hsl(225,80%,8%)] border border-white/[0.08] rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-5"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Wrench className="h-3.5 w-3.5 text-accent-cyan" />
            {title}
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/[0.05]">
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Input({ label, value, onChange, type = "text", placeholder }: {
  label: string; value: any; onChange: (v: string) => void;
  type?: string; placeholder?: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <input type={type} value={value ?? ""} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} className="input" />
    </label>
  );
}

function Textarea({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <textarea value={value ?? ""} rows={2}
        onChange={(e) => onChange(e.target.value)} className="input resize-none" />
    </label>
  );
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: string[];
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="input">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}
