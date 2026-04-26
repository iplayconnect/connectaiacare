"use client";

import { useEffect, useState } from "react";
import {
  Phone,
  Loader2,
  Plus,
  X,
  Save,
  Trash2,
  AlertTriangle,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { api, type CallScenario } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /admin/cenarios-sofia — CRUD dos playbooks de ligação Sofia.
// Editar prompt, voz, tools permitidas e ações pós-call sem deploy.
// Permissão: super_admin OU admin_tenant.
// ═══════════════════════════════════════════════════════════════════

export default function CenariosSofiaPage() {
  const { user } = useAuth();
  const [scenarios, setScenarios] = useState<CallScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CallScenario | null>(null);
  const [creating, setCreating] = useState(false);

  const allowed = hasRole(user, "super_admin", "admin_tenant");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.communicationsScenarios();
      setScenarios(r.scenarios);
    } catch (e: any) {
      setError(e?.message || "Erro carregando");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (allowed) load();
  }, [allowed]);

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
            <Phone className="h-6 w-6 text-accent-cyan" />
            Cenários da Sofia VoIP
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Playbooks que definem tom, prompt e tools por tipo de ligação.
            Mudanças entram em vigor na próxima ligação (sem rebuild).
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90"
        >
          <Plus className="h-4 w-4" />
          Novo cenário
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
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {scenarios.map((s) => (
            <ScenarioCard
              key={s.id}
              scenario={s}
              onEdit={() => setEditing(s)}
              onChanged={load}
            />
          ))}
        </div>
      )}

      {editing && (
        <ScenarioModal
          scenario={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {creating && (
        <ScenarioModal
          scenario={null}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function ScenarioCard({
  scenario,
  onEdit,
  onChanged,
}: {
  scenario: CallScenario;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (!confirm(`Desativar cenário "${scenario.label}"?`)) return;
    setBusy(true);
    try {
      await api.communicationsScenarioDelete(scenario.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActive() {
    setBusy(true);
    try {
      await api.communicationsScenarioUpdate(scenario.id, {
        active: !scenario.active,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 rounded-xl border border-white/[0.06] hover:border-white/[0.12] transition">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
                scenario.direction === "outbound"
                  ? "bg-accent-cyan/15 text-accent-cyan"
                  : "bg-purple-500/15 text-purple-400"
              }`}
            >
              {scenario.direction}
            </span>
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-white/[0.06] text-muted-foreground">
              {scenario.persona}
            </span>
            {!scenario.active && (
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/15 text-amber-400">
                Inativo
              </span>
            )}
          </div>
          <h3 className="font-semibold mt-1.5 truncate">{scenario.label}</h3>
          <div className="text-[11px] font-mono text-muted-foreground mt-0.5">
            {scenario.code}
          </div>
        </div>
      </div>

      {scenario.description && (
        <p className="text-xs text-muted-foreground mt-3 line-clamp-2">
          {scenario.description}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-1">
        {scenario.allowed_tools.slice(0, 5).map((t) => (
          <span
            key={t}
            className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] font-mono"
          >
            {t}
          </span>
        ))}
        {scenario.allowed_tools.length > 5 && (
          <span className="text-[10px] text-muted-foreground">
            +{scenario.allowed_tools.length - 5}
          </span>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <button
          onClick={onEdit}
          className="text-xs px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/10"
        >
          Editar
        </button>
        <button
          onClick={handleToggleActive}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 disabled:opacity-50"
        >
          {scenario.active ? "Desativar" : "Ativar"}
        </button>
        <button
          onClick={handleDelete}
          disabled={busy}
          className="text-xs px-3 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 ml-auto disabled:opacity-50"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}

function ScenarioModal({
  scenario,
  onClose,
  onSaved,
}: {
  scenario: CallScenario | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [code, setCode] = useState(scenario?.code || "");
  const [label, setLabel] = useState(scenario?.label || "");
  const [direction, setDirection] = useState<"outbound" | "inbound">(
    scenario?.direction || "outbound",
  );
  const [persona, setPersona] = useState(scenario?.persona || "medico");
  const [description, setDescription] = useState(scenario?.description || "");
  const [systemPrompt, setSystemPrompt] = useState(scenario?.system_prompt || "");
  const [voice, setVoice] = useState(scenario?.voice || "ara");
  const [allowedTools, setAllowedTools] = useState(
    (scenario?.allowed_tools || []).join(", "),
  );
  const [maxSec, setMaxSec] = useState(scenario?.max_duration_seconds || 600);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsPrompt, setNeedsPrompt] = useState(!scenario);

  useEffect(() => {
    // Quando edita, busca o full scenario com system_prompt
    if (scenario && !systemPrompt) {
      api.communicationsScenarioGet(scenario.id).then((r) => {
        setSystemPrompt(r.scenario.system_prompt || "");
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    const tools = allowedTools
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const body: any = {
      label,
      description: description || null,
      system_prompt: systemPrompt,
      voice,
      allowed_tools: tools,
      max_duration_seconds: Number(maxSec),
    };
    try {
      if (scenario) {
        await api.communicationsScenarioUpdate(scenario.id, body);
      } else {
        await api.communicationsScenarioCreate({
          ...body,
          code,
          direction,
          persona,
        });
      }
      onSaved();
    } catch (e: any) {
      setError(e?.message || "Erro salvando");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="bg-[hsl(222,47%,7%)] border border-white/10 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <header className="sticky top-0 bg-[hsl(222,47%,7%)] border-b border-white/[0.06] px-5 py-3 flex items-center justify-between">
          <h2 className="font-semibold">
            {scenario ? `Editar: ${scenario.label}` : "Novo cenário"}
          </h2>
          <button onClick={onClose}>
            <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
          </button>
        </header>

        <div className="p-5 space-y-4">
          {!scenario && (
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Código (slug)
                </label>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="check_in_matinal"
                  className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm font-mono"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Direção
                </label>
                <select
                  value={direction}
                  onChange={(e) =>
                    setDirection(e.target.value as "outbound" | "inbound")
                  }
                  className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm"
                >
                  <option value="outbound">outbound</option>
                  <option value="inbound" disabled>
                    inbound (Fase 2)
                  </option>
                </select>
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-muted-foreground">
                  Persona
                </label>
                <select
                  value={persona}
                  onChange={(e) => setPersona(e.target.value)}
                  className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm"
                >
                  {[
                    "medico",
                    "enfermeiro",
                    "cuidador_pro",
                    "familia",
                    "paciente_b2c",
                    "admin_tenant",
                    "comercial",
                  ].map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Rótulo (UI)
            </label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm"
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Descrição (curta)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm"
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground flex items-center justify-between">
              <span>Prompt de sistema (playbook completo)</span>
              <span className="text-[10px] opacity-60">
                {systemPrompt.length} chars
              </span>
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={16}
              placeholder="# QUEM VOCÊ É AGORA..."
              className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-xs font-mono leading-relaxed"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs uppercase tracking-wider text-muted-foreground">
                Voz Grok
              </label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm"
              >
                <option value="ara">ara</option>
                <option value="eve">eve</option>
                <option value="leo">leo</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs uppercase tracking-wider text-muted-foreground">
                Tools permitidas (separadas por vírgula)
              </label>
              <input
                value={allowedTools}
                onChange={(e) => setAllowedTools(e.target.value)}
                placeholder="get_patient_summary, list_medication_schedules"
                className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-xs font-mono"
              />
            </div>
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Duração máxima (segundos)
            </label>
            <input
              type="number"
              value={maxSec}
              onChange={(e) => setMaxSec(Number(e.target.value))}
              className="w-full mt-1 px-3 py-2 rounded bg-white/[0.03] border border-white/10 outline-none text-sm font-mono"
            />
          </div>

          {error && (
            <div className="p-2 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>

        <footer className="sticky bottom-0 bg-[hsl(222,47%,7%)] border-t border-white/[0.06] px-5 py-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded border border-white/10 hover:bg-white/[0.04]"
          >
            Cancelar
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !label || !systemPrompt}
            className="flex items-center gap-2 px-3 py-1.5 text-sm rounded bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            Salvar
          </button>
        </footer>
      </div>
    </div>
  );
}
