"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookMarked,
  Pill,
  AlertTriangle,
  RefreshCw,
  Loader2,
  CheckCircle2,
  Circle,
  AlertCircle,
  Search,
  Edit3,
  Save,
  XCircle,
  ThumbsUp,
  Clock,
  Eye,
} from "lucide-react";
import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  curatedReviewApi,
  type CuratedStats,
  type Cid10Entry,
  type MedicationEntry,
  type ExpectationEntry,
  type ReviewStatus,
  type PromptSeverity,
} from "@/lib/api-curated-review";

type Tab = "cid10" | "medications" | "expectations";

const REVIEW_CLS: Record<ReviewStatus, string> = {
  draft: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  under_review: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  approved: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

const REVIEW_LABEL: Record<ReviewStatus, string> = {
  draft: "Rascunho",
  under_review: "Em revisão",
  approved: "Aprovado",
};

const SEVERITY_CLS: Record<PromptSeverity, string> = {
  low: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  medium: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  high: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  critical: "bg-red-500/20 text-red-300 border-red-500/40",
};

export default function CuratedReviewPage() {
  const { user, loading: authLoading } = useAuth();
  const allowed = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "clinical_reviewer",
    "medico",
    "farmaceutico",
  );

  const [tab, setTab] = useState<Tab>("cid10");
  const [stats, setStats] = useState<CuratedStats | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const s = await curatedReviewApi.stats();
      setStats(s);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    if (!authLoading && allowed) loadStats();
  }, [authLoading, allowed, loadStats]);

  if (authLoading)
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );

  if (!allowed)
    return (
      <div className="p-8">
        <h1 className="text-xl font-semibold text-slate-100">Acesso negado</h1>
        <p className="text-slate-400 mt-1 text-sm">
          Apenas revisores clínicos: super_admin, admin_tenant, clinical_reviewer,
          médico, farmacêutico.
        </p>
      </div>
    );

  return (
    <div className="px-6 lg:px-8 pt-6 pb-8 max-w-[1500px]">
      <header className="mb-5">
        <h1 className="text-xl font-semibold text-slate-100 flex items-center gap-2">
          <BookMarked className="w-5 h-5 text-cyan-400" />
          Revisão · Bases Curadas
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">
          Bases clínicas usadas pelo wizard de cadastro de paciente. Revise e
          aprove (ou edite) cada item. Auditoria completa: quem aprovou, quando,
          com qual nota.
        </p>
      </header>

      {/* STATS GLOBAIS */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
          <StatsCard
            label="CIDs (catálogo)"
            stats={stats.tables.cid10}
            icon={<BookMarked className="w-4 h-4" />}
          />
          <StatsCard
            label="Medicamentos"
            stats={stats.tables.medications}
            icon={<Pill className="w-4 h-4" />}
          />
          <StatsCard
            label="Cross-validation"
            stats={stats.tables.expectations}
            icon={<AlertTriangle className="w-4 h-4" />}
          />
        </div>
      )}

      {/* TABS */}
      <nav className="flex items-center gap-1 border-b border-white/10 mb-5">
        {[
          { id: "cid10" as Tab, label: "CID-10", icon: BookMarked },
          { id: "medications" as Tab, label: "Medicamentos", icon: Pill },
          { id: "expectations" as Tab, label: "Cross-validation", icon: AlertTriangle },
        ].map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition flex items-center gap-1.5 ${
                active
                  ? "border-cyan-400 text-cyan-300"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-white/20"
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          );
        })}
      </nav>

      {tab === "cid10" && <Cid10Tab onChange={loadStats} />}
      {tab === "medications" && <MedicationsTab onChange={loadStats} />}
      {tab === "expectations" && <ExpectationsTab onChange={loadStats} />}
    </div>
  );
}

function StatsCard({
  label,
  stats,
  icon,
}: {
  label: string;
  stats: { total: number; draft: number; under_review: number; approved: number };
  icon: React.ReactNode;
}) {
  const pct = stats.total > 0 ? Math.round((stats.approved / stats.total) * 100) : 0;
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
          <span className="text-cyan-400">{icon}</span>
          {label}
        </h3>
        <span className="text-2xl font-bold text-slate-100 tabular-nums">
          {stats.total}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div>
          <div className="text-amber-300 font-bold tabular-nums">{stats.draft}</div>
          <div className="text-slate-500 text-[10px]">draft</div>
        </div>
        <div>
          <div className="text-cyan-300 font-bold tabular-nums">{stats.under_review}</div>
          <div className="text-slate-500 text-[10px]">em revisão</div>
        </div>
        <div>
          <div className="text-emerald-300 font-bold tabular-nums">{stats.approved}</div>
          <div className="text-slate-500 text-[10px]">aprovado</div>
        </div>
      </div>
      <div className="mt-2 h-1 bg-white/[0.04] rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-[10px] text-slate-500 mt-1 text-right">{pct}% aprovado</div>
    </div>
  );
}

// ────── TAB: CID-10 ──────

function Cid10Tab({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<Cid10Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<ReviewStatus | "">("");
  const [filterCategory, setFilterCategory] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [categories, setCategories] = useState<{ category: string; count: number }[]>([]);
  const [editing, setEditing] = useState<Cid10Entry | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await curatedReviewApi.listCid10({
        status: filterStatus || undefined,
        category: filterCategory || undefined,
        q: search || undefined,
      });
      setItems(r.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterCategory, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    curatedReviewApi.cid10Categories().then((r) => setCategories(r.categories));
  }, []);

  async function quickApprove(code: string) {
    await curatedReviewApi.updateCid10(code, { review_status: "approved" });
    await load();
    onChange();
  }

  async function quickToReview(code: string) {
    await curatedReviewApi.updateCid10(code, { review_status: "under_review" });
    await load();
    onChange();
  }

  return (
    <div>
      <FilterBar
        search={search}
        onSearch={setSearch}
        filterStatus={filterStatus}
        onFilterStatus={setFilterStatus}
        extraFilters={
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5"
          >
            <option value="">Todas categorias</option>
            {categories.map((c) => (
              <option key={c.category} value={c.category}>
                {c.category} ({c.count})
              </option>
            ))}
          </select>
        }
        onRefresh={load}
        loading={loading}
        count={items.length}
      />

      <div className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading && items.length === 0 ? (
          <div className="p-10 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-500" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500 italic">
            Nenhum CID com esse filtro.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Código</th>
                <th className="text-left px-3 py-2.5 font-medium">Descrição</th>
                <th className="text-left px-3 py-2.5 font-medium">Nome leigo</th>
                <th className="text-left px-3 py-2.5 font-medium">Categoria</th>
                <th className="text-center px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr
                  key={it.code}
                  className="border-t border-white/[0.04] hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-cyan-300">
                    {it.code}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-slate-200">
                    {it.description_pt}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-slate-400">
                    {it.description_layman || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-xs">
                    <span className="px-2 py-0.5 rounded bg-white/[0.04] text-slate-300">
                      {it.category}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className={`text-[11px] px-2 py-0.5 rounded border ${
                        REVIEW_CLS[it.review_status]
                      }`}
                    >
                      {REVIEW_LABEL[it.review_status]}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {it.review_status !== "approved" && (
                        <button
                          onClick={() => quickApprove(it.code)}
                          title="Aprovar"
                          className="text-[11px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 rounded px-2 py-1 hover:bg-emerald-500/20 inline-flex items-center gap-1"
                        >
                          <ThumbsUp className="w-3 h-3" />
                          Aprovar
                        </button>
                      )}
                      {it.review_status === "draft" && (
                        <button
                          onClick={() => quickToReview(it.code)}
                          title="Marcar como Em revisão"
                          className="text-[11px] border border-white/10 text-slate-400 rounded px-2 py-1 hover:bg-white/[0.04] inline-flex items-center gap-1"
                        >
                          <Eye className="w-3 h-3" />
                        </button>
                      )}
                      <button
                        onClick={() => setEditing(it)}
                        className="text-[11px] border border-white/10 text-slate-400 rounded px-2 py-1 hover:bg-white/[0.04]"
                      >
                        <Edit3 className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <Cid10EditModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
            onChange();
          }}
        />
      )}
    </div>
  );
}

function Cid10EditModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: Cid10Entry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [descPt, setDescPt] = useState(entry.description_pt);
  const [descLayman, setDescLayman] = useState(entry.description_layman || "");
  const [category, setCategory] = useState(entry.category);
  const [reviewerNotes, setReviewerNotes] = useState(entry.reviewer_notes || "");
  const [status, setStatus] = useState<ReviewStatus>(entry.review_status);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await curatedReviewApi.updateCid10(entry.code, {
        review_status: status,
        description_pt: descPt,
        description_layman: descLayman,
        category,
        reviewer_notes: reviewerNotes || undefined,
      });
      onSaved();
    } catch (e: any) {
      alert(e?.message || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <EditModal
      title={`CID-10 · ${entry.code}`}
      onClose={onClose}
      onSave={save}
      saving={saving}
    >
      <FormRow label="Descrição (técnica)">
        <textarea
          value={descPt}
          onChange={(e) => setDescPt(e.target.value)}
          rows={2}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Nome leigo (opcional)">
        <input
          value={descLayman}
          onChange={(e) => setDescLayman(e.target.value)}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Categoria">
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="form-input">
          <option value="cardiovascular">cardiovascular</option>
          <option value="respiratorio">respiratorio</option>
          <option value="endocrino_metabolico">endocrino_metabolico</option>
          <option value="neurologico">neurologico</option>
          <option value="psiquiatrico">psiquiatrico</option>
          <option value="osteomuscular">osteomuscular</option>
          <option value="infeccioso">infeccioso</option>
          <option value="oncologico">oncologico</option>
          <option value="urinario">urinario</option>
          <option value="digestivo">digestivo</option>
          <option value="sensorial">sensorial</option>
          <option value="cuidados_paliativos">cuidados_paliativos</option>
          <option value="outro">outro</option>
        </select>
      </FormRow>
      <FormRow label="Status de revisão">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as ReviewStatus)}
          className="form-input"
        >
          <option value="draft">Rascunho</option>
          <option value="under_review">Em revisão</option>
          <option value="approved">Aprovado</option>
        </select>
      </FormRow>
      <FormRow label="Nota do revisor">
        <textarea
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          rows={3}
          className="form-input"
          placeholder="Justificativa, dúvida, sugestão de revisão..."
        />
      </FormRow>
    </EditModal>
  );
}

// ────── TAB: MEDICAMENTOS ──────

function MedicationsTab({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<MedicationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<ReviewStatus | "">("");
  const [filterClass, setFilterClass] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [classes, setClasses] = useState<{ class: string; count: number }[]>([]);
  const [editing, setEditing] = useState<MedicationEntry | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await curatedReviewApi.listMedications({
        status: filterStatus || undefined,
        therapeutic_class: filterClass || undefined,
        q: search || undefined,
      });
      setItems(r.items);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterClass, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    curatedReviewApi.therapeuticClasses().then((r) => setClasses(r.classes));
  }, []);

  async function quickApprove(id: string) {
    await curatedReviewApi.updateMedication(id, { review_status: "approved" });
    await load();
    onChange();
  }

  return (
    <div>
      <FilterBar
        search={search}
        onSearch={setSearch}
        filterStatus={filterStatus}
        onFilterStatus={setFilterStatus}
        extraFilters={
          <select
            value={filterClass}
            onChange={(e) => setFilterClass(e.target.value)}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5"
          >
            <option value="">Todas classes</option>
            {classes.map((c) => (
              <option key={c.class} value={c.class}>
                {c.class} ({c.count})
              </option>
            ))}
          </select>
        }
        onRefresh={load}
        loading={loading}
        count={items.length}
      />

      <div className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading && items.length === 0 ? (
          <div className="p-10 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-500" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500 italic">
            Nenhum medicamento com esse filtro.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Princípio ativo</th>
                <th className="text-left px-3 py-2.5 font-medium">Marcas</th>
                <th className="text-left px-3 py-2.5 font-medium">Classes terapêuticas</th>
                <th className="text-left px-3 py-2.5 font-medium">Indicações</th>
                <th className="text-center px-3 py-2.5 font-medium">Status</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-t border-white/[0.04] hover:bg-white/[0.03]">
                  <td className="px-4 py-2.5 text-sm text-slate-100 font-medium">
                    {it.active_ingredient}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-slate-400">
                    {(it.brand_names || []).slice(0, 3).join(", ")}
                    {(it.brand_names?.length ?? 0) > 3 && "…"}
                  </td>
                  <td className="px-3 py-2.5 text-xs">
                    <div className="flex flex-wrap gap-1">
                      {(it.therapeutic_classes || []).map((cls) => (
                        <span
                          key={cls}
                          className="px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 text-[10px]"
                        >
                          {cls}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-slate-400">
                    {(it.main_indications || []).join(", ")}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className={`text-[11px] px-2 py-0.5 rounded border ${
                        REVIEW_CLS[it.review_status]
                      }`}
                    >
                      {REVIEW_LABEL[it.review_status]}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {it.review_status !== "approved" && (
                        <button
                          onClick={() => quickApprove(it.id)}
                          className="text-[11px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 rounded px-2 py-1 hover:bg-emerald-500/20 inline-flex items-center gap-1"
                        >
                          <ThumbsUp className="w-3 h-3" />
                          Aprovar
                        </button>
                      )}
                      <button
                        onClick={() => setEditing(it)}
                        className="text-[11px] border border-white/10 text-slate-400 rounded px-2 py-1 hover:bg-white/[0.04]"
                      >
                        <Edit3 className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <MedicationEditModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
            onChange();
          }}
        />
      )}
    </div>
  );
}

function MedicationEditModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: MedicationEntry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [activeIngredient, setActiveIngredient] = useState(entry.active_ingredient);
  const [brandNames, setBrandNames] = useState((entry.brand_names || []).join(", "));
  const [matchPatterns, setMatchPatterns] = useState((entry.match_patterns || []).join(", "));
  const [therapeuticClasses, setTherapeuticClasses] = useState((entry.therapeutic_classes || []).join(", "));
  const [mainIndications, setMainIndications] = useState((entry.main_indications || []).join(", "));
  const [notes, setNotes] = useState(entry.notes || "");
  const [reviewerNotes, setReviewerNotes] = useState(entry.reviewer_notes || "");
  const [status, setStatus] = useState<ReviewStatus>(entry.review_status);
  const [saving, setSaving] = useState(false);

  function splitCsv(s: string): string[] {
    return s.split(",").map((x) => x.trim()).filter(Boolean);
  }

  async function save() {
    setSaving(true);
    try {
      await curatedReviewApi.updateMedication(entry.id, {
        review_status: status,
        active_ingredient: activeIngredient,
        brand_names: splitCsv(brandNames),
        match_patterns: splitCsv(matchPatterns),
        therapeutic_classes: splitCsv(therapeuticClasses),
        main_indications: splitCsv(mainIndications),
        notes: notes || undefined,
        reviewer_notes: reviewerNotes || undefined,
      });
      onSaved();
    } catch (e: any) {
      alert(e?.message || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <EditModal
      title={`Medicamento · ${entry.active_ingredient}`}
      onClose={onClose}
      onSave={save}
      saving={saving}
      wide
    >
      <FormRow label="Princípio ativo">
        <input
          value={activeIngredient}
          onChange={(e) => setActiveIngredient(e.target.value)}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Marcas comerciais (separadas por vírgula)">
        <input
          value={brandNames}
          onChange={(e) => setBrandNames(e.target.value)}
          className="form-input"
          placeholder="Cozaar, Aradois"
        />
      </FormRow>
      <FormRow label="Match patterns (texto livre que casa)">
        <input
          value={matchPatterns}
          onChange={(e) => setMatchPatterns(e.target.value)}
          className="form-input"
          placeholder="losartana, losartan"
        />
        <p className="text-[10px] text-slate-500 mt-1">
          Substrings case-insensitive — "losartana 50mg" do paciente casa com "losartana".
        </p>
      </FormRow>
      <FormRow label="Classes terapêuticas (separadas por vírgula)">
        <input
          value={therapeuticClasses}
          onChange={(e) => setTherapeuticClasses(e.target.value)}
          className="form-input"
          placeholder="anti_hipertensivo, BRA"
        />
      </FormRow>
      <FormRow label="Indicações principais">
        <input
          value={mainIndications}
          onChange={(e) => setMainIndications(e.target.value)}
          className="form-input"
          placeholder="HAS, IC"
        />
      </FormRow>
      <FormRow label="Notas (audit clínico)">
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="form-input" />
      </FormRow>
      <FormRow label="Status de revisão">
        <select value={status} onChange={(e) => setStatus(e.target.value as ReviewStatus)} className="form-input">
          <option value="draft">Rascunho</option>
          <option value="under_review">Em revisão</option>
          <option value="approved">Aprovado</option>
        </select>
      </FormRow>
      <FormRow label="Nota do revisor">
        <textarea
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          rows={2}
          className="form-input"
          placeholder="Justificativa da edição/aprovação"
        />
      </FormRow>
    </EditModal>
  );
}

// ────── TAB: EXPECTATIONS (cross-validation) ──────

function ExpectationsTab({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<ExpectationEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<ReviewStatus | "">("");
  const [filterSeverity, setFilterSeverity] = useState<PromptSeverity | "">("");
  const [editing, setEditing] = useState<ExpectationEntry | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await curatedReviewApi.listExpectations({
        status: filterStatus || undefined,
        severity: filterSeverity || undefined,
      });
      setItems(r.items);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterSeverity]);

  useEffect(() => {
    load();
  }, [load]);

  async function quickApprove(id: string) {
    await curatedReviewApi.updateExpectation(id, { review_status: "approved" });
    await load();
    onChange();
  }

  return (
    <div>
      <FilterBar
        filterStatus={filterStatus}
        onFilterStatus={setFilterStatus}
        extraFilters={
          <select
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value as PromptSeverity | "")}
            className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5"
          >
            <option value="">Todas severities</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
        }
        onRefresh={load}
        loading={loading}
        count={items.length}
      />

      <div className="space-y-3">
        {loading && items.length === 0 ? (
          <div className="p-10 text-center">
            <Loader2 className="w-6 h-6 animate-spin mx-auto text-slate-500" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-sm text-slate-500 italic rounded-lg border border-white/10 bg-white/[0.02]">
            Nenhuma regra com esse filtro.
          </div>
        ) : (
          items.map((it) => (
            <div
              key={it.id}
              className="rounded-lg border border-white/10 bg-white/[0.02] p-4"
            >
              <div className="flex items-center justify-between mb-2 gap-2">
                <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                  {it.condition_label}
                  {it.cid10_code && (
                    <span className="text-[11px] font-mono text-cyan-300 bg-cyan-500/10 px-1.5 py-0.5 rounded">
                      {it.cid10_code}
                    </span>
                  )}
                </h3>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded border uppercase font-bold ${
                      SEVERITY_CLS[it.prompt_severity]
                    }`}
                  >
                    {it.prompt_severity}
                  </span>
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded border ${
                      REVIEW_CLS[it.review_status]
                    }`}
                  >
                    {REVIEW_LABEL[it.review_status]}
                  </span>
                </div>
              </div>

              <div className="text-xs text-slate-400 mb-3">
                <span className="font-semibold text-slate-300">Espera classes:</span>{" "}
                {(it.expected_therapeutic_classes || []).map((cls) => (
                  <span
                    key={cls}
                    className="inline-block px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 mr-1 text-[10px]"
                  >
                    {cls}
                  </span>
                ))}
              </div>

              <div className="bg-amber-500/[0.06] border border-amber-500/20 rounded p-3 text-xs text-slate-200 mb-3 italic">
                "{it.prompt_message}"
              </div>

              {it.clinical_rationale && (
                <details className="text-xs text-slate-400 mb-3">
                  <summary className="cursor-pointer hover:text-slate-200">
                    Justificativa clínica (audit)
                  </summary>
                  <p className="mt-2 pl-3 border-l border-white/10">
                    {it.clinical_rationale}
                  </p>
                </details>
              )}

              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span>
                  Match: {(it.condition_match_patterns || []).slice(0, 3).join(", ")}
                  {(it.condition_match_patterns?.length ?? 0) > 3 && "…"}
                </span>
                <div className="flex items-center gap-1.5">
                  {it.review_status !== "approved" && (
                    <button
                      onClick={() => quickApprove(it.id)}
                      className="text-[11px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 rounded px-2 py-1 hover:bg-emerald-500/20 inline-flex items-center gap-1"
                    >
                      <ThumbsUp className="w-3 h-3" />
                      Aprovar
                    </button>
                  )}
                  <button
                    onClick={() => setEditing(it)}
                    className="text-[11px] border border-white/10 text-slate-300 rounded px-2 py-1 hover:bg-white/[0.04] inline-flex items-center gap-1"
                  >
                    <Edit3 className="w-3 h-3" />
                    Editar
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {editing && (
        <ExpectationEditModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
            onChange();
          }}
        />
      )}
    </div>
  );
}

function ExpectationEditModal({
  entry,
  onClose,
  onSaved,
}: {
  entry: ExpectationEntry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [conditionLabel, setConditionLabel] = useState(entry.condition_label);
  const [matchPatterns, setMatchPatterns] = useState((entry.condition_match_patterns || []).join(", "));
  const [expectedClasses, setExpectedClasses] = useState((entry.expected_therapeutic_classes || []).join(", "));
  const [severity, setSeverity] = useState<PromptSeverity>(entry.prompt_severity);
  const [promptMessage, setPromptMessage] = useState(entry.prompt_message);
  const [rationale, setRationale] = useState(entry.clinical_rationale || "");
  const [reviewerNotes, setReviewerNotes] = useState(entry.reviewer_notes || "");
  const [status, setStatus] = useState<ReviewStatus>(entry.review_status);
  const [saving, setSaving] = useState(false);

  function splitCsv(s: string): string[] {
    return s.split(",").map((x) => x.trim()).filter(Boolean);
  }

  async function save() {
    setSaving(true);
    try {
      await curatedReviewApi.updateExpectation(entry.id, {
        review_status: status,
        condition_label: conditionLabel,
        condition_match_patterns: splitCsv(matchPatterns),
        expected_therapeutic_classes: splitCsv(expectedClasses),
        prompt_severity: severity,
        prompt_message: promptMessage,
        clinical_rationale: rationale,
        reviewer_notes: reviewerNotes || undefined,
      });
      onSaved();
    } catch (e: any) {
      alert(e?.message || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <EditModal
      title={`Cross-validation · ${entry.condition_label.split("(")[0].trim()}`}
      onClose={onClose}
      onSave={save}
      saving={saving}
      wide
    >
      <FormRow label="Condição (label completo)">
        <input
          value={conditionLabel}
          onChange={(e) => setConditionLabel(e.target.value)}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Match patterns (texto livre da condição que casa)">
        <input
          value={matchPatterns}
          onChange={(e) => setMatchPatterns(e.target.value)}
          className="form-input"
          placeholder="hipertens, pressao alta, has"
        />
      </FormRow>
      <FormRow label="Classes terapêuticas esperadas">
        <input
          value={expectedClasses}
          onChange={(e) => setExpectedClasses(e.target.value)}
          className="form-input"
          placeholder="anti_hipertensivo, IECA, BRA"
        />
        <p className="text-[10px] text-slate-500 mt-1">
          Basta UMA delas estar presente nas medicações pra "ok" (sem prompt).
        </p>
      </FormRow>
      <FormRow label="Severidade do prompt">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as PromptSeverity)}
          className="form-input"
        >
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
      </FormRow>
      <FormRow label="Mensagem ao paciente (visível na UI do wizard)">
        <textarea
          value={promptMessage}
          onChange={(e) => setPromptMessage(e.target.value)}
          rows={3}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Justificativa clínica (audit, não vai pro paciente)">
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          rows={3}
          className="form-input"
        />
      </FormRow>
      <FormRow label="Status de revisão">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as ReviewStatus)}
          className="form-input"
        >
          <option value="draft">Rascunho</option>
          <option value="under_review">Em revisão</option>
          <option value="approved">Aprovado</option>
        </select>
      </FormRow>
      <FormRow label="Nota do revisor">
        <textarea
          value={reviewerNotes}
          onChange={(e) => setReviewerNotes(e.target.value)}
          rows={2}
          className="form-input"
        />
      </FormRow>
    </EditModal>
  );
}

// ────── COMPONENTES UTILITÁRIOS ──────

function FilterBar({
  search,
  onSearch,
  filterStatus,
  onFilterStatus,
  extraFilters,
  onRefresh,
  loading,
  count,
}: {
  search?: string;
  onSearch?: (s: string) => void;
  filterStatus: ReviewStatus | "";
  onFilterStatus: (s: ReviewStatus | "") => void;
  extraFilters?: React.ReactNode;
  onRefresh: () => void;
  loading: boolean;
  count: number;
}) {
  return (
    <div className="flex flex-wrap gap-2 items-center mb-3">
      {onSearch !== undefined && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-white/[0.04] border border-white/10 rounded">
          <Search className="w-3.5 h-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="buscar..."
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            className="bg-transparent outline-none text-xs w-48 text-slate-100 placeholder:text-slate-600"
          />
        </div>
      )}
      <select
        value={filterStatus}
        onChange={(e) => onFilterStatus(e.target.value as ReviewStatus | "")}
        className="text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-2 py-1.5"
      >
        <option value="">Todos status</option>
        <option value="draft">Rascunho</option>
        <option value="under_review">Em revisão</option>
        <option value="approved">Aprovado</option>
      </select>
      {extraFilters}
      <span className="text-[11px] text-slate-500 ml-2">{count} {count === 1 ? "item" : "itens"}</span>
      <button
        onClick={onRefresh}
        disabled={loading}
        className="ml-auto text-xs bg-white/[0.04] border border-white/10 text-slate-200 rounded px-3 py-1.5 hover:bg-white/[0.07] disabled:opacity-50 flex items-center gap-1.5"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        Atualizar
      </button>
    </div>
  );
}

function EditModal({
  title,
  children,
  onClose,
  onSave,
  saving,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
  wide?: boolean;
}) {
  return (
    <>
      <div className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-[101] flex items-center justify-center p-4">
        <div
          className={`bg-slate-950 border border-white/10 rounded-xl shadow-2xl w-full ${
            wide ? "max-w-3xl" : "max-w-xl"
          } max-h-[90vh] overflow-y-auto`}
        >
          <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between sticky top-0 bg-slate-950 z-10">
            <h2 className="text-base font-semibold text-slate-100">{title}</h2>
            <button
              onClick={onClose}
              className="p-1.5 rounded border border-white/10 hover:bg-white/[0.04] text-slate-400"
            >
              <XCircle className="w-4 h-4" />
            </button>
          </div>
          <div className="p-5 space-y-3">{children}</div>
          <div className="px-5 py-4 border-t border-white/10 flex items-center justify-end gap-2 sticky bottom-0 bg-slate-950">
            <button
              onClick={onClose}
              className="text-xs border border-white/10 text-slate-300 rounded px-3 py-1.5 hover:bg-white/[0.04]"
            >
              Cancelar
            </button>
            <button
              onClick={onSave}
              disabled={saving}
              className="text-xs bg-cyan-500/15 border border-cyan-500/40 text-cyan-300 rounded px-4 py-1.5 hover:bg-cyan-500/20 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Salvar
            </button>
          </div>
        </div>
      </div>
      <style jsx>{`
        :global(.form-input) {
          width: 100%;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 0.375rem;
          padding: 0.375rem 0.75rem;
          font-size: 0.875rem;
          color: rgb(241 245 249);
          outline: none;
          resize: vertical;
        }
        :global(.form-input:focus) {
          border-color: rgba(34, 211, 238, 0.4);
        }
      `}</style>
    </>
  );
}

function FormRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 block">
        {label}
      </label>
      {children}
    </div>
  );
}
