"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  GitBranch,
  Loader2,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Archive,
  FilePen,
  X,
  Plus,
  ChevronRight,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import {
  api,
  type CallScenario,
  type ScenarioVersion,
  type ScenarioVersionStatus,
  ApiError,
} from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/cenarios-sofia/versoes — Versionamento de prompts dos cenários.
// Editar prompt vai pra DRAFT, admin testa, promove pra TESTING e
// depois PUBLISHED. Cada promoção arquiva a anterior. Histórico inviolável.
// Permissão: super_admin OU admin_tenant.
// ═══════════════════════════════════════════════════════════════════

const STATUS_BADGE: Record<ScenarioVersionStatus, string> = {
  draft: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  testing: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  published: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  archived: "bg-white/5 text-muted-foreground border-white/10",
};

const STATUS_LABELS: Record<ScenarioVersionStatus, string> = {
  draft: "Rascunho",
  testing: "Em teste",
  published: "Publicada",
  archived: "Arquivada",
};

const STATUS_ICONS: Record<
  ScenarioVersionStatus,
  React.ComponentType<{ className?: string }>
> = {
  draft: FilePen,
  testing: FlaskConical,
  published: CheckCircle2,
  archived: Archive,
};

export default function CenariosVersoesPage() {
  const { user } = useAuth();
  const [scenarios, setScenarios] = useState<CallScenario[]>([]);
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(null);
  const [versions, setVersions] = useState<ScenarioVersion[]>([]);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeVersion, setActiveVersion] = useState<ScenarioVersion | null>(null);
  const [creating, setCreating] = useState(false);

  const allowed = hasRole(user, "super_admin", "admin_tenant");

  const loadScenarios = useCallback(async () => {
    setError(null);
    try {
      const r = await api.communicationsScenarios();
      setScenarios(r.scenarios);
      if (r.scenarios.length > 0 && !activeScenarioId) {
        setActiveScenarioId(r.scenarios[0].id);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro carregando cenários");
    } finally {
      setLoading(false);
    }
  }, [activeScenarioId]);

  const loadVersions = useCallback(async (scenarioId: string) => {
    setLoadingVersions(true);
    setError(null);
    try {
      const r = await api.scenarioVersionsList(scenarioId);
      setVersions(r.items);
      setCurrentVersionId(r.current_version_id || null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erro carregando versões");
    } finally {
      setLoadingVersions(false);
    }
  }, []);

  useEffect(() => {
    if (allowed) loadScenarios();
  }, [allowed, loadScenarios]);

  useEffect(() => {
    if (activeScenarioId) loadVersions(activeScenarioId);
  }, [activeScenarioId, loadVersions]);

  const activeScenario = useMemo(
    () => scenarios.find((s) => s.id === activeScenarioId) || null,
    [scenarios, activeScenarioId],
  );

  async function promote(
    version: ScenarioVersion,
    target: "testing" | "published" | "archived",
  ) {
    if (!activeScenarioId) return;
    const labels = { testing: "Em teste", published: "Publicada", archived: "Arquivar" };
    if (target === "published") {
      if (
        !confirm(
          `Publicar v${version.version_number}? Vai ARQUIVAR a versão publicada atual e ATIVAR esta em produção. Próximas ligações usarão o novo prompt.`,
        )
      )
        return;
    } else if (
      !confirm(`Mover v${version.version_number} para "${labels[target]}"?`)
    )
      return;
    try {
      await api.scenarioVersionPromote(activeScenarioId, version.id, target);
      setActiveVersion(null);
      await loadVersions(activeScenarioId);
    } catch (e) {
      alert(`Falhou: ${e instanceof Error ? e.message : "erro"}`);
    }
  }

  if (!allowed) {
    return (
      <div className="max-w-[800px] mx-auto px-6 py-12 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-amber-500" />
        <p className="text-sm text-muted-foreground">
          Apenas super_admin ou admin_tenant.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <GitBranch className="h-6 w-6 text-accent-cyan" />
            Versionamento de Cenários
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Toda mudança em prompt cria nova versão. Fluxo:{" "}
            <span className="text-sky-300">draft</span> →{" "}
            <span className="text-amber-300">testing</span> →{" "}
            <span className="text-emerald-300">published</span>. Promover para
            published arquiva a anterior automaticamente.
          </p>
        </div>
      </header>

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando cenários…
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          <aside className="space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2 px-2">
              Cenários
            </div>
            {scenarios.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveScenarioId(s.id)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition flex items-center gap-2 ${
                  s.id === activeScenarioId
                    ? "bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan"
                    : "border border-transparent hover:bg-white/5"
                }`}
              >
                <ChevronRight
                  className={`h-3.5 w-3.5 ${s.id === activeScenarioId ? "" : "opacity-30"}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium">{s.label}</div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {s.code}
                  </div>
                </div>
              </button>
            ))}
          </aside>

          <main>
            {error && (
              <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
                {error}
              </div>
            )}

            {activeScenario && (
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{activeScenario.label}</h2>
                  <p className="text-xs text-muted-foreground font-mono">
                    {activeScenario.code} · {activeScenario.direction} ·{" "}
                    {activeScenario.persona}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() =>
                      activeScenarioId && loadVersions(activeScenarioId)
                    }
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-white/10 hover:bg-white/5"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Atualizar
                  </button>
                  <button
                    onClick={() => setCreating(true)}
                    className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90"
                  >
                    <Plus className="h-4 w-4" />
                    Novo draft
                  </button>
                </div>
              </div>
            )}

            {loadingVersions ? (
              <div className="flex items-center gap-2 text-muted-foreground p-8 justify-center">
                <Loader2 className="h-4 w-4 animate-spin" />
                Carregando versões…
              </div>
            ) : versions.length === 0 ? (
              <div className="text-center p-12 text-muted-foreground border border-dashed border-white/10 rounded-lg text-sm">
                Nenhuma versão para este cenário.
              </div>
            ) : (
              <div className="space-y-2">
                {versions.map((v) => (
                  <VersionRow
                    key={v.id}
                    version={v}
                    isCurrent={v.id === currentVersionId}
                    onClick={() => setActiveVersion(v)}
                  />
                ))}
              </div>
            )}
          </main>
        </div>
      )}

      {activeVersion && (
        <VersionDrawer
          version={activeVersion}
          isCurrent={activeVersion.id === currentVersionId}
          onClose={() => setActiveVersion(null)}
          onPromote={(t) => promote(activeVersion, t)}
        />
      )}

      {creating && activeScenario && (
        <CreateDraftDialog
          scenario={activeScenario}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            if (activeScenarioId) loadVersions(activeScenarioId);
          }}
        />
      )}
    </div>
  );
}

function VersionRow({
  version,
  isCurrent,
  onClick,
}: {
  version: ScenarioVersion;
  isCurrent: boolean;
  onClick: () => void;
}) {
  const Icon = STATUS_ICONS[version.status];
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-lg border transition hover:bg-white/[0.03] ${
        isCurrent
          ? "border-accent-cyan/40 bg-accent-cyan/5"
          : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 mt-0.5 flex-shrink-0 text-accent-cyan" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-mono text-sm">v{version.version_number}</span>
            <span
              className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${STATUS_BADGE[version.status]}`}
            >
              {STATUS_LABELS[version.status]}
            </span>
            {isCurrent && (
              <span className="px-2 py-0.5 text-[11px] uppercase font-semibold rounded bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30">
                Em uso
              </span>
            )}
            <span className="text-xs text-muted-foreground ml-auto">
              {new Date(version.created_at).toLocaleString("pt-BR")}
            </span>
          </div>
          <div className="text-sm text-foreground/90">
            {version.label}
          </div>
          {version.notes && (
            <div className="text-xs text-muted-foreground mt-1 line-clamp-1">
              {version.notes}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function VersionDrawer({
  version,
  isCurrent,
  onClose,
  onPromote,
}: {
  version: ScenarioVersion;
  isCurrent: boolean;
  onClose: () => void;
  onPromote: (t: "testing" | "published" | "archived") => void;
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
              <span className="font-mono text-sm">
                v{version.version_number}
              </span>
              <span
                className={`px-2 py-0.5 text-[11px] uppercase font-semibold rounded border ${STATUS_BADGE[version.status]}`}
              >
                {STATUS_LABELS[version.status]}
              </span>
              {isCurrent && (
                <span className="px-2 py-0.5 text-[11px] uppercase font-semibold rounded bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30">
                  Em uso
                </span>
              )}
            </div>
            <h2 className="text-lg font-semibold">{version.label}</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
              System prompt
            </div>
            <pre className="text-xs font-mono p-3 rounded bg-black/30 border border-white/5 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
              {version.system_prompt}
            </pre>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Voz">
              <span>{version.voice}</span>
            </Field>
            <Field label="Duração máxima">
              <span>{version.max_duration_seconds}s</span>
            </Field>
            <Field label="Tools permitidas">
              <div className="flex flex-wrap gap-1 mt-1">
                {(version.allowed_tools || []).map((t) => (
                  <span
                    key={t}
                    className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-white/5 border border-white/10"
                  >
                    {t}
                  </span>
                ))}
                {(!version.allowed_tools || version.allowed_tools.length === 0) && (
                  <span className="text-xs text-muted-foreground">—</span>
                )}
              </div>
            </Field>
            <Field label="Ações pós-call">
              <div className="flex flex-wrap gap-1 mt-1">
                {(version.post_call_actions || []).map((a) => (
                  <span
                    key={a}
                    className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-white/5 border border-white/10"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </Field>
          </div>

          {version.notes && (
            <Field label="Notas">
              <p className="text-sm whitespace-pre-wrap">{version.notes}</p>
            </Field>
          )}

          <div className="text-xs text-muted-foreground">
            Criada em {new Date(version.created_at).toLocaleString("pt-BR")}
            {version.published_at && (
              <>
                {" "}
                · publicada em{" "}
                {new Date(version.published_at).toLocaleString("pt-BR")}
              </>
            )}
          </div>
        </div>

        <div className="sticky bottom-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-4 flex gap-2 justify-end flex-wrap">
          {version.status === "draft" && (
            <button
              onClick={() => onPromote("testing")}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-200"
            >
              <FlaskConical className="h-4 w-4" />
              Mover para teste
            </button>
          )}
          {(version.status === "draft" || version.status === "testing") && (
            <button
              onClick={() => onPromote("published")}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-200 font-medium"
            >
              <CheckCircle2 className="h-4 w-4" />
              Publicar
            </button>
          )}
          {(version.status === "draft" || version.status === "testing") &&
            !isCurrent && (
              <button
                onClick={() => onPromote("archived")}
                className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-muted-foreground"
              >
                <Archive className="h-4 w-4" />
                Arquivar
              </button>
            )}
          {version.status === "published" && (
            <span className="text-xs text-muted-foreground self-center">
              Versão publicada — para alterar, crie nova draft.
            </span>
          )}
          {version.status === "archived" && (
            <span className="text-xs text-muted-foreground self-center">
              Versão arquivada.
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function CreateDraftDialog({
  scenario,
  onClose,
  onSaved,
}: {
  scenario: CallScenario;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [label, setLabel] = useState(scenario.label);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // carrega o prompt da published atual como base
  useEffect(() => {
    let cancelled = false;
    api
      .communicationsScenarioGet(scenario.id)
      .then((r) => {
        if (!cancelled) setSystemPrompt(r.scenario.system_prompt || "");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [scenario.id]);

  async function save() {
    if (!systemPrompt.trim()) {
      setError("system_prompt obrigatório");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.scenarioVersionCreateDraft(scenario.id, {
        label: label || undefined,
        system_prompt: systemPrompt,
        notes: notes || null,
      });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro");
    } finally {
      setLoading(false);
    }
  }

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
          <h2 className="text-lg font-semibold">
            Nova versão (draft) · {scenario.code}
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label className="text-xs uppercase tracking-wide text-muted-foreground block mb-1">
              Label
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 rounded-md bg-black/30 border border-white/10 text-sm"
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-wide text-muted-foreground block mb-1">
              System prompt
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={20}
              className="w-full px-3 py-2 rounded-md bg-black/30 border border-white/10 text-xs font-mono"
              placeholder="O prompt que define personalidade, tom, regras de escalação…"
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Carregado a partir da versão publicada atual. Edite e crie um draft.
            </p>
          </div>

          <div>
            <label className="text-xs uppercase tracking-wide text-muted-foreground block mb-1">
              Notas / changelog
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 rounded-md bg-black/30 border border-white/10 text-sm"
              placeholder="O que mudou e por quê. Ajuda revisão futura."
            />
          </div>
        </div>

        <div className="sticky bottom-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-4 flex gap-2 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-md border border-white/10 hover:bg-white/5"
          >
            Cancelar
          </button>
          <button
            onClick={save}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90 disabled:opacity-50"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            Salvar como draft
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}
