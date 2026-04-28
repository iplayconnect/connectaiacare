"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  Phone,
  PhoneCall,
  Plus,
  ShieldAlert,
  Smartphone,
  Trash2,
  Users,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ════════════════════════════════════════════════════════════════════
// /admin/plantoes
//
// Insight do panel LLM (Grok fase 2). Tem 2 propósitos:
//
// 1. Cadastrar plantões fixos (manhã/tarde/noite/custom) por
//    cuidador. Quando áudio chega, biometria 1:N busca SÓ no pool
//    do plantão atual em vez de todos os cuidadores do tenant.
//    Pool de 3-4 vozes vs 10-15 = muito mais preciso.
//
// 2. Marcar phone_type de cada cuidador:
//    - personal = WhatsApp pessoal (biometria normal)
//    - shared   = celular do plantão (biometria off, força pergunta)
//    - unknown  = ainda não classificado (default seguro: shared)
//
// Painel "agora" mostra plantão ativo + cuidadores no pool atual.
// ════════════════════════════════════════════════════════════════════

type Shift = {
  id: string;
  caregiver_id: string;
  full_name: string;
  phone?: string;
  phone_type: "personal" | "shared" | "unknown";
  shift_name: string;
  starts_at: string;
  ends_at: string;
  weekdays: number[];
  active: boolean;
  notes?: string;
};

const WEEKDAY_LABELS = ["", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

export default function PlantoesPage() {
  const { user } = useAuth();
  const canSee = hasRole(
    user, "super_admin", "admin_tenant", "medico", "enfermeiro",
  );
  const canEdit = hasRole(user, "super_admin", "admin_tenant");

  const [shifts, setShifts] = useState<Shift[]>([]);
  const [current, setCurrent] = useState<{
    current_shift_name: string | null;
    active_caregivers: any[];
    pool_size: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [search, setSearch] = useState("");

  const reload = () => {
    setLoading(true);
    setErr(null);
    Promise.all([api.shiftsList(), api.shiftsCurrent()])
      .then(([list, curr]) => {
        setShifts(list.shifts);
        setCurrent(curr);
      })
      .catch((e: any) => setErr(e?.message || "Erro ao carregar"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { if (canSee) reload(); }, [canSee]);

  if (!canSee) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center max-w-md mx-auto">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Cadastro de plantões disponível para equipe administrativa e
          clínica.
        </p>
      </div>
    );
  }

  const filtered = useMemo(() => {
    if (!search.trim()) return shifts;
    const q = search.trim().toLowerCase();
    return shifts.filter((s) =>
      s.full_name.toLowerCase().includes(q) ||
      s.shift_name.toLowerCase().includes(q),
    );
  }, [shifts, search]);

  return (
    <div className="space-y-5 max-w-7xl">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-accent-cyan" />
            Plantões — janelas de turno + tipo de telefone
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
            Cadastre os turnos fixos de cada cuidador. A biometria de voz
            usa essa informação pra reduzir o pool de busca quando
            recebe áudio (de 1:N grande pra 1:N pequeno do plantão).
            phone_type controla se o número é pessoal ou compartilhado.
          </p>
        </div>
        {canEdit && (
          <button
            onClick={() => setNewOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium shadow-glow-cyan hover:brightness-110"
          >
            <Plus className="h-3.5 w-3.5" />
            Novo plantão
          </button>
        )}
      </header>

      {/* Painel "agora" */}
      {current && (
        <div className="rounded-xl border border-accent-cyan/20 bg-accent-cyan/5 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="h-4 w-4 text-accent-cyan" />
            <h2 className="text-sm font-semibold">Plantão ativo agora</h2>
          </div>
          {current.current_shift_name ? (
            <>
              <div className="flex items-baseline gap-3 mb-3">
                <span className="text-2xl font-semibold tabular text-accent-cyan">
                  {current.current_shift_name}
                </span>
                <span className="text-xs text-muted-foreground">
                  pool de biometria: {current.pool_size} cuidador
                  {current.pool_size !== 1 ? "es" : ""}
                </span>
              </div>
              {current.active_caregivers.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {current.active_caregivers.map((c: any) => (
                    <PersonChip
                      key={c.caregiver_id}
                      name={c.full_name}
                      phoneType={c.phone_type}
                      override={c.source === "override"}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-muted-foreground italic">
                  Nenhum cuidador no pool atual. Biometria 1:N vai falhar —
                  fallback será sempre disparado.
                </div>
              )}
            </>
          ) : (
            <div className="text-xs text-muted-foreground italic">
              Sem plantão cadastrado para o horário atual. Cadastre os
              turnos abaixo pra Sofia conseguir reduzir o pool de
              biometria.
            </div>
          )}
        </div>
      )}

      {/* Filtro */}
      <div className="flex items-end gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar nome ou nome do plantão..."
          className="input flex-1"
        />
        <span className="text-xs text-muted-foreground tabular">
          {filtered.length} / {shifts.length}
        </span>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando...
        </div>
      ) : err ? (
        <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention">
          {err}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState onAdd={canEdit ? () => setNewOpen(true) : undefined} />
      ) : (
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Cuidador</th>
                <th className="px-3 py-2 text-left">Plantão</th>
                <th className="px-3 py-2 text-left">Janela</th>
                <th className="px-3 py-2 text-left">Dias</th>
                <th className="px-3 py-2 text-left">Telefone</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <ShiftRow
                  key={s.id}
                  shift={s}
                  canEdit={canEdit}
                  onPhoneTypeChange={async (newType) => {
                    try {
                      await api.caregiverPhoneType(s.caregiver_id, newType);
                      reload();
                    } catch (e: any) {
                      alert(e?.message || "Erro ao atualizar phone_type");
                    }
                  }}
                  onDelete={async () => {
                    if (
                      !confirm(`Desativar plantão ${s.shift_name} de ${s.full_name}?`)
                    ) return;
                    try {
                      await api.shiftDelete(s.id);
                      reload();
                    } catch (e: any) {
                      alert(e?.message || "Erro ao desativar");
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {newOpen && (
        <NewShiftModal
          onClose={() => setNewOpen(false)}
          onDone={() => {
            setNewOpen(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────

function PersonChip({
  name,
  phoneType,
  override,
}: {
  name: string;
  phoneType: string;
  override: boolean;
}) {
  const Icon =
    phoneType === "personal"
      ? Smartphone
      : phoneType === "shared"
      ? PhoneCall
      : Phone;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs border ${
        override
          ? "bg-classification-attention/10 border-classification-attention/30 text-classification-attention"
          : "bg-white/[0.04] border-white/[0.08]"
      }`}
      title={
        override
          ? "Override temporário (cobertura)"
          : `phone_type: ${phoneType}`
      }
    >
      <Icon className="h-3 w-3" />
      {name}
      {override && (
        <span className="text-[9px] uppercase tracking-wider opacity-70">
          override
        </span>
      )}
    </span>
  );
}

function ShiftRow({
  shift,
  canEdit,
  onPhoneTypeChange,
  onDelete,
}: {
  shift: Shift;
  canEdit: boolean;
  onPhoneTypeChange: (newType: "personal" | "shared" | "unknown") => void;
  onDelete: () => void;
}) {
  return (
    <tr className="border-t border-white/[0.04]">
      <td className="px-3 py-2 font-medium">{shift.full_name}</td>
      <td className="px-3 py-2">
        <span className="px-1.5 py-0.5 rounded bg-white/[0.05] text-[10px] uppercase tracking-wider">
          {shift.shift_name}
        </span>
      </td>
      <td className="px-3 py-2 tabular text-muted-foreground">
        {shift.starts_at.slice(0, 5)} – {shift.ends_at.slice(0, 5)}
      </td>
      <td className="px-3 py-2 text-[11px] text-muted-foreground">
        {(shift.weekdays || [])
          .sort((a, b) => a - b)
          .map((d) => WEEKDAY_LABELS[d])
          .join(" · ")}
      </td>
      <td className="px-3 py-2">
        {canEdit ? (
          <select
            value={shift.phone_type}
            onChange={(e) =>
              onPhoneTypeChange(e.target.value as any)
            }
            className="input max-w-[140px] text-[11px] py-1"
            title="phone_type controla se a biometria de voz é ativa"
          >
            <option value="unknown">unknown</option>
            <option value="personal">personal (biometria on)</option>
            <option value="shared">shared (biometria off)</option>
          </select>
        ) : (
          <PhoneTypeBadge type={shift.phone_type} />
        )}
        {shift.phone && (
          <div className="text-[10px] text-muted-foreground/60 mt-0.5 tabular">
            {shift.phone}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-right">
        {canEdit && (
          <button
            onClick={onDelete}
            className="p-1 rounded hover:bg-classification-attention/10 text-classification-attention"
            title="Desativar plantão"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </td>
    </tr>
  );
}

function PhoneTypeBadge({ type }: { type: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    personal: {
      label: "personal",
      cls: "bg-classification-routine/10 text-classification-routine border-classification-routine/30",
    },
    shared: {
      label: "shared",
      cls: "bg-classification-attention/10 text-classification-attention border-classification-attention/30",
    },
    unknown: {
      label: "unknown",
      cls: "bg-white/[0.05] text-muted-foreground border-white/[0.08]",
    },
  };
  const m = map[type] || map.unknown;
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider border ${m.cls}`}
    >
      {m.label}
    </span>
  );
}

function EmptyState({ onAdd }: { onAdd?: () => void }) {
  return (
    <div className="text-center py-16">
      <CalendarClock className="h-10 w-10 mx-auto text-muted-foreground/40 mb-3" />
      <h3 className="text-sm font-semibold">Sem plantões cadastrados</h3>
      <p className="text-xs text-muted-foreground mt-1 mb-4">
        Sem plantões, a biometria 1:N busca em todos os cuidadores do
        tenant. Reduza o pool cadastrando os turnos abaixo.
      </p>
      {onAdd && (
        <button
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
        >
          <Plus className="h-3.5 w-3.5" />
          Cadastrar primeiro plantão
        </button>
      )}
    </div>
  );
}

// ─── Modal de novo plantão ────────────────────────────────

function NewShiftModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [caregivers, setCaregivers] = useState<any[]>([]);
  const [loadingCgs, setLoadingCgs] = useState(true);
  const [form, setForm] = useState({
    caregiver_id: "",
    shift_name: "morning",
    starts_at: "07:00",
    ends_at: "15:00",
    weekdays: [1, 2, 3, 4, 5, 6, 7],
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .voiceListCaregivers()
      .then((r) => setCaregivers(r.caregivers || []))
      .catch(() => setCaregivers([]))
      .finally(() => setLoadingCgs(false));
  }, []);

  const toggleDay = (d: number) => {
    setForm((f) => ({
      ...f,
      weekdays: f.weekdays.includes(d)
        ? f.weekdays.filter((x) => x !== d)
        : [...f.weekdays, d].sort(),
    }));
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.caregiver_id) {
      setErr("Selecione um cuidador.");
      return;
    }
    if (form.weekdays.length === 0) {
      setErr("Selecione pelo menos um dia da semana.");
      return;
    }
    setErr(null);
    setSaving(true);
    try {
      await api.shiftCreate(form);
      onDone();
    } catch (e: any) {
      setErr(e?.message || "Erro");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-[hsl(225,80%,8%)] border border-white/[0.08] rounded-xl w-full max-w-lg p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-accent-cyan" />
            Novo plantão
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-white/[0.05]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Cuidador *
            </span>
            {loadingCgs ? (
              <div className="text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 inline animate-spin mr-1" />
                Carregando…
              </div>
            ) : (
              <select
                value={form.caregiver_id}
                onChange={(e) =>
                  setForm({ ...form, caregiver_id: e.target.value })
                }
                className="input"
              >
                <option value="">— escolher —</option>
                {caregivers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                  </option>
                ))}
              </select>
            )}
          </label>

          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Nome do plantão *
            </span>
            <input
              value={form.shift_name}
              onChange={(e) =>
                setForm({ ...form, shift_name: e.target.value })
              }
              className="input"
              placeholder="ex: morning, afternoon, night"
              list="shift-names"
            />
            <datalist id="shift-names">
              <option value="morning" />
              <option value="afternoon" />
              <option value="night" />
              <option value="overnight" />
            </datalist>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1">
              <span className="text-[11px] text-muted-foreground">
                Início *
              </span>
              <input
                type="time"
                value={form.starts_at}
                onChange={(e) =>
                  setForm({ ...form, starts_at: e.target.value })
                }
                className="input"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[11px] text-muted-foreground">
                Fim *
              </span>
              <input
                type="time"
                value={form.ends_at}
                onChange={(e) =>
                  setForm({ ...form, ends_at: e.target.value })
                }
                className="input"
              />
            </label>
          </div>

          <div>
            <span className="text-[11px] text-muted-foreground">
              Dias da semana *
            </span>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDay(d)}
                  className={`px-2.5 py-1 rounded text-xs ${
                    form.weekdays.includes(d)
                      ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan"
                      : "bg-white/[0.03] border border-white/[0.08] hover:bg-white/[0.06]"
                  }`}
                >
                  {WEEKDAY_LABELS[d]}
                </button>
              ))}
            </div>
          </div>

          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Notas (opcional)
            </span>
            <input
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="input"
            />
          </label>

          {err && (
            <div className="text-xs text-classification-attention">{err}</div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-3 py-2"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" />
              )}
              Cadastrar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
