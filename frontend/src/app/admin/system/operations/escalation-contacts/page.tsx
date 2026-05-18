"use client";

/**
 * Painel admin — Contatos de escalação por tenant.
 *
 * Acesso: super_admin (qualquer tenant via dropdown), admin_tenant
 * (só o próprio tenant). Substitui anti-pattern do .env
 * P1_ESCALATION_PHONES.
 *
 * Fluxo:
 *   1. Admin abre a página, vê lista de contatos do tenant
 *   2. Cadastra novo plantonista (phone + nome + role + prioridades)
 *   3. Cada P1 que entrar no tenant dispara push WhatsApp pros
 *      contatos cadastrados
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Phone,
  Plus,
  RefreshCw,
  ShieldAlert,
  Trash2,
  User,
  UserCog,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { hasRole } from "@/lib/permissions";
import { ScheduleBadge } from "@/components/escalation/schedule-badge";
import { EscalationHealthDashboard } from "@/components/escalation/health-dashboard";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import {
  ESCALATION_ROLE_LABEL,
  formatPhoneBR,
  maskPhoneInput,
  relativeTimeBR,
  tenantEscalationApi,
  type CreateEscalationContactPayload,
  type EscalationContact,
  type EscalationPriority,
  type EscalationRole,
} from "@/lib/api-tenant-escalation";

const PRIORITY_LABEL: Record<EscalationPriority, { label: string; color: string }> = {
  P1: { label: "P1 — Crítico", color: "text-classification-critical border-classification-critical/40 bg-classification-critical/10" },
  P2: { label: "P2 — Atenção", color: "text-classification-urgent border-classification-urgent/40 bg-classification-urgent/10" },
  P3: { label: "P3 — Rotina", color: "text-classification-attention border-classification-attention/40 bg-classification-attention/10" },
};

const ROLE_OPTIONS: EscalationRole[] = [
  "plantonista_l1",
  "plantonista_l2",
  "medico_responsavel",
  "enfermeiro_chefe",
  "gestor_unidade",
  "admin_tenant",
  "outro",
];

export default function EscalationContactsPage() {
  const { user } = useAuth();
  const allowed = hasRole(user, "super_admin", "admin_tenant");
  const confirm = useConfirm();
  const toast = useToast();

  // Tenant atual — admin_tenant só vê o próprio. super_admin pode
  // futuramente ter dropdown; por enquanto usa o tenant do JWT.
  const tenantId = (user?.tenantId || "connectaiacare_demo") as string;

  const [contacts, setContacts] = useState<EscalationContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [tab, setTab] = useState<"contacts" | "health">("contacts");

  const load = useCallback(
    async (silent = false) => {
      if (silent) setRefreshing(true);
      else setError(null);
      try {
        const res = await tenantEscalationApi.list(tenantId, {
          include_inactive: includeInactive,
        });
        setContacts(res.contacts || []);
      } catch (e) {
        if (!silent) setError(e instanceof Error ? e.message : "Erro carregando");
      } finally {
        if (silent) setRefreshing(false);
        else setLoading(false);
      }
    },
    [tenantId, includeInactive],
  );

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  const activeCount = useMemo(
    () => contacts.filter((c) => c.active).length,
    [contacts],
  );
  const p1Count = useMemo(
    () => contacts.filter((c) => c.active && c.priorities.includes("P1")).length,
    [contacts],
  );

  if (!allowed) {
    return (
      <div className="max-w-md mx-auto px-6 py-12 text-center">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Disponível apenas para super_admin e admin_tenant.
        </p>
      </div>
    );
  }

  async function handleToggleActive(c: EscalationContact) {
    if (c.active) {
      const ok = await confirm({
        title: `Desativar ${c.contact_name}?`,
        description: (
          <>
            Histórico fica preservado pra audit (LGPD).
            Pode reativar depois criando novo cadastro com o mesmo número.
          </>
        ),
        confirmLabel: "Desativar",
        variant: "destructive",
      });
      if (!ok) return;
      try {
        await tenantEscalationApi.deactivate(tenantId, c.id);
        toast.success(`${c.contact_name} desativado.`);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Erro desativando");
        return;
      }
    } else {
      try {
        await tenantEscalationApi.update(tenantId, c.id, { active: true });
        toast.success(`${c.contact_name} reativado.`);
      } catch (e) {
        // Pode falhar se já existe outro active com mesmo phone
        toast.error(e instanceof Error ? e.message : "Erro reativando");
        return;
      }
    }
    await load(true);
  }

  return (
    <div className="space-y-5 max-w-[1200px] animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <UserCog className="h-4 w-4 text-accent-cyan" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Plantão clínico
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            <span className="accent-gradient-text">Contatos de escalação</span>
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
            Pessoas que recebem push WhatsApp quando entra handoff no tenant. Cada
            contato escolhe quais prioridades (P1/P2/P3) recebe. Schedule opcional
            permite turnos. Tenant atual: <span className="font-mono text-accent-cyan">{tenantId}</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => load(true)}
            disabled={refreshing}
            className="text-[11px] px-2 py-1.5 rounded border border-white/[0.08] hover:bg-white/[0.04] disabled:opacity-40 flex items-center gap-1"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} /> Atualizar
          </button>
          <button
            type="button"
            onClick={() => setShowForm(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
          >
            <Plus className="h-3.5 w-3.5" /> Novo contato
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-white/[0.06]">
        <TabButton active={tab === "contacts"} onClick={() => setTab("contacts")}>
          Contatos
        </TabButton>
        <TabButton active={tab === "health"} onClick={() => setTab("health")}>
          Saúde do Plantão
        </TabButton>
      </div>

      {tab === "contacts" ? (
        <>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Contatos ativos" value={activeCount} icon={CheckCircle2} accent="text-accent-cyan" />
            <Stat label="Recebem P1" value={p1Count} icon={AlertCircle} accent="text-classification-critical" />
            <Stat label="Total cadastrados" value={contacts.length} icon={User} accent="text-muted-foreground" />
          </div>

          {/* Filtros */}
          <div className="flex items-center gap-3 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
                className="accent-accent-cyan"
              />
              <span>Mostrar histórico (inativos)</span>
            </label>
          </div>

          {/* Lista */}
          {loading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando…
            </div>
          ) : error ? (
            <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention">
              {error}
            </div>
          ) : contacts.length === 0 ? (
            <EmptyState onAdd={() => setShowForm(true)} />
          ) : (
            <div className="space-y-2">
              {contacts.map((c) => (
                <ContactRow
                  key={c.id}
                  contact={c}
                  onToggleActive={() => handleToggleActive(c)}
                />
              ))}
            </div>
          )}
        </>
      ) : (
        <EscalationHealthDashboard tenantId={tenantId} />
      )}

      {/* Aviso compatibilidade */}
      <div className="text-[10px] text-muted-foreground/70 italic">
        Durante a transição, se o tenant não tiver contatos cadastrados aqui,
        sistema cai no fallback <code className="text-accent-cyan/70">P1_ESCALATION_PHONES</code> do
        .env (P1 apenas). Cadastre contatos pra remover essa dependência.
      </div>

      {/* Form modal */}
      {showForm && (
        <NewContactModal
          tenantId={tenantId}
          existingPhones={new Set(contacts.filter((c) => c.active).map((c) => c.phone))}
          onClose={() => setShowForm(false)}
          onCreated={async () => {
            setShowForm(false);
            await load(true);
          }}
        />
      )}
    </div>
  );
}

// ─── Componentes ────────────────────────────────────────────────────

function Stat({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
        <Icon className={`h-3 w-3 ${accent}`} />
        {label}
      </div>
      <div className={`text-2xl font-bold tabular mt-1 ${accent}`}>{value}</div>
    </div>
  );
}

function ContactRow({
  contact,
  onToggleActive,
}: {
  contact: EscalationContact;
  onToggleActive: () => void;
}) {
  return (
    <div
      className={[
        "rounded-xl border p-3 transition",
        contact.active
          ? "border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]"
          : "border-white/[0.04] bg-white/[0.01] opacity-60",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold">{contact.contact_name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-muted-foreground">
              {ESCALATION_ROLE_LABEL[contact.role] || contact.role}
            </span>
            {!contact.active && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-classification-attention/10 text-classification-attention">
                Inativo
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1">
              <Phone className="h-3 w-3" /> {formatPhoneBR(contact.phone)}
            </span>
            <span className="flex items-center gap-1.5">
              <Clock className="h-3 w-3" />
              <ScheduleBadge
                weekdays={contact.schedule_weekdays}
                start={contact.schedule_start}
                end={contact.schedule_end}
                showLiveStatus={contact.active}
              />
            </span>
          </div>
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            {contact.priorities.map((p) => (
              <span
                key={p}
                className={`text-[10px] px-1.5 py-0.5 rounded border ${PRIORITY_LABEL[p].color}`}
              >
                {PRIORITY_LABEL[p].label}
              </span>
            ))}
            {/* Última atividade — sinal de vida do contato.
                Verde se recebeu nas últimas 24h, amarelo se 1-7 dias,
                cinza se >7 dias ou nunca. */}
            <LastActivityBadge
              lastReceivedAt={contact.last_p1_received_at}
              totalReceived={contact.total_p1_received}
            />
          </div>
          {contact.notes && (
            <div className="mt-2 text-[11px] text-muted-foreground italic">
              {contact.notes}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onToggleActive}
          className={[
            "text-[10px] px-2 py-1 rounded border whitespace-nowrap",
            contact.active
              ? "border-classification-attention/30 hover:bg-classification-attention/10 text-classification-attention"
              : "border-accent-cyan/30 hover:bg-accent-cyan/10 text-accent-cyan",
          ].join(" ")}
        >
          {contact.active ? "Desativar" : "Reativar"}
        </button>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "px-4 py-2 text-sm font-medium transition border-b-2 -mb-px",
        active
          ? "text-accent-cyan border-accent-cyan"
          : "text-muted-foreground border-transparent hover:text-foreground",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function LastActivityBadge({
  lastReceivedAt,
  totalReceived,
}: {
  lastReceivedAt: string | null;
  totalReceived: number;
}) {
  const rel = relativeTimeBR(lastReceivedAt);

  // Nunca recebeu push P1: badge cinza
  if (!lastReceivedAt) {
    return (
      <span
        className="text-[10px] px-1.5 py-0.5 rounded border border-white/[0.05] bg-white/[0.02] text-muted-foreground/70"
        title="Esse contato ainda não recebeu nenhum push P1."
      >
        Sem atividade
      </span>
    );
  }

  // Cor baseada em frescor (verde <24h, amarelo 1-7d, cinza >7d)
  const ageHours =
    (Date.now() - new Date(lastReceivedAt).getTime()) / 1_000 / 3_600;
  const color =
    ageHours < 24
      ? "border-classification-routine/40 bg-classification-routine/10 text-classification-routine"
      : ageHours < 168 // 7 dias
      ? "border-classification-attention/30 bg-classification-attention/10 text-classification-attention"
      : "border-white/[0.06] bg-white/[0.02] text-muted-foreground";

  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded border ${color}`}
      title={`Último push P1: ${new Date(lastReceivedAt).toLocaleString("pt-BR")}\nTotal de P1s recebidos: ${totalReceived}`}
    >
      Último P1: {rel} · {totalReceived}×
    </span>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] p-12 text-center">
      <UserCog className="h-8 w-8 mx-auto text-muted-foreground/50 mb-3" />
      <h3 className="text-sm font-medium">Nenhum contato cadastrado ainda</h3>
      <p className="text-xs text-muted-foreground mt-1 max-w-md mx-auto">
        Sem contatos, P1 cai no fallback do <code className="text-accent-cyan/70">.env</code> (legacy)
        ou fica só na Central 24h genérica. Cadastre pra receber push direto
        no WhatsApp do plantonista quando entrar emergência.
      </p>
      <button
        type="button"
        onClick={onAdd}
        className="mt-4 inline-flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
      >
        <Plus className="h-3.5 w-3.5" /> Cadastrar primeiro contato
      </button>
    </div>
  );
}

// ─── Modal de criação ──────────────────────────────────────────────

function NewContactModal({
  tenantId,
  existingPhones,
  onClose,
  onCreated,
}: {
  tenantId: string;
  existingPhones: Set<string>;
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [phoneMasked, setPhoneMasked] = useState("");
  const [contactName, setContactName] = useState("");
  const [role, setRole] = useState<EscalationRole>("plantonista_l1");
  const [priorities, setPriorities] = useState<EscalationPriority[]>(["P1"]);
  const [notes, setNotes] = useState("");
  // Schedule opcional — default vazio (= 24/7)
  const [scheduleMode, setScheduleMode] = useState<"24/7" | "custom">("24/7");
  const [weekdays, setWeekdays] = useState<number[]>([1, 2, 3, 4, 5]); // Seg-Sex default
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("18:00");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function togglePriority(p: EscalationPriority) {
    setPriorities((prev) =>
      prev.includes(p)
        ? (prev.filter((x) => x !== p) as EscalationPriority[])
        : ([...prev, p] as EscalationPriority[]),
    );
  }

  function toggleWeekday(d: number) {
    setWeekdays((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort(),
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const phoneDigits = phoneMasked.replace(/\D/g, "");
    if (phoneDigits.length < 12 || phoneDigits.length > 13) {
      setErr("Phone inválido — formato: DDI + DDD + número (12 ou 13 dígitos).");
      return;
    }
    if (existingPhones.has(phoneDigits)) {
      setErr("Esse phone já tem cadastro ativo. Desative o anterior antes.");
      return;
    }
    if (contactName.trim().length < 2) {
      setErr("Nome obrigatório (mínimo 2 caracteres).");
      return;
    }
    if (priorities.length === 0) {
      setErr("Selecione ao menos uma prioridade.");
      return;
    }
    if (scheduleMode === "custom" && weekdays.length === 0) {
      setErr("Schedule custom precisa de pelo menos 1 dia da semana.");
      return;
    }
    setSaving(true);
    try {
      const payload: CreateEscalationContactPayload = {
        phone: phoneDigits,
        contact_name: contactName.trim(),
        role,
        priorities,
        notes: notes.trim() || null,
        // Schedule: 24/7 manda null pra todos; custom manda os 3.
        schedule_weekdays:
          scheduleMode === "custom" ? weekdays : null,
        schedule_start:
          scheduleMode === "custom" ? `${startTime}:00` : null,
        schedule_end:
          scheduleMode === "custom" ? `${endTime}:00` : null,
      };
      await tenantEscalationApi.create(tenantId, payload);
      await onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Falha ao criar contato");
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-bg-elevated p-6 space-y-4 shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Novo contato de escalação</h2>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Receberá push WhatsApp quando entrar handoff no tenant{" "}
              <span className="font-mono text-accent-cyan">{tenantId}</span>.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/[0.04] text-muted-foreground"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">Nome *</span>
          <input
            autoFocus
            required
            className="input w-full"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            placeholder="Nome humano pra audit (ex: Dr. Henrique Bordin)"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">
            Phone WhatsApp * (DDI + DDD + número)
          </span>
          <input
            required
            className="input w-full font-mono"
            value={phoneMasked}
            onChange={(e) => setPhoneMasked(maskPhoneInput(e.target.value))}
            placeholder="55 (51) 99234-5678"
            maxLength={20}
          />
          <span className="text-[10px] text-muted-foreground/60 block">
            Use o número que recebe WhatsApp ativo. Push vai chegar igual mensagem normal.
          </span>
        </label>

        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">Papel *</span>
          <select
            className="input w-full"
            value={role}
            onChange={(e) => setRole(e.target.value as EscalationRole)}
          >
            {ROLE_OPTIONS.map((r) => (
              <option key={r} value={r}>
                {ESCALATION_ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-1">
          <span className="text-[11px] text-muted-foreground block">
            Prioridades que recebe push *
          </span>
          <div className="grid grid-cols-3 gap-2">
            {(["P1", "P2", "P3"] as EscalationPriority[]).map((p) => (
              <label
                key={p}
                className={[
                  "flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs cursor-pointer transition",
                  priorities.includes(p)
                    ? `${PRIORITY_LABEL[p].color}`
                    : "border-white/[0.06] hover:bg-white/[0.04] text-muted-foreground",
                ].join(" ")}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={priorities.includes(p)}
                  onChange={() => togglePriority(p)}
                />
                {PRIORITY_LABEL[p].label}
              </label>
            ))}
          </div>
          <span className="text-[10px] text-muted-foreground/60 block">
            Recomendação inicial: <b>só P1</b> (emergência clínica). P2/P3 vira ruído rápido.
          </span>
        </div>

        {/* Schedule (opcional, default 24/7) */}
        <div className="space-y-2">
          <span className="text-[11px] text-muted-foreground block">
            Turno de plantão
          </span>
          <div className="grid grid-cols-2 gap-2">
            <label
              className={[
                "flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs cursor-pointer transition",
                scheduleMode === "24/7"
                  ? "border-accent-cyan/40 bg-accent-cyan/5 text-accent-cyan"
                  : "border-white/[0.06] hover:bg-white/[0.04] text-muted-foreground",
              ].join(" ")}
            >
              <input
                type="radio"
                name="schedule_mode"
                className="sr-only"
                checked={scheduleMode === "24/7"}
                onChange={() => setScheduleMode("24/7")}
              />
              ♾️ Sempre disponível (24/7)
            </label>
            <label
              className={[
                "flex items-center justify-center gap-1.5 p-2 rounded-lg border text-xs cursor-pointer transition",
                scheduleMode === "custom"
                  ? "border-accent-cyan/40 bg-accent-cyan/5 text-accent-cyan"
                  : "border-white/[0.06] hover:bg-white/[0.04] text-muted-foreground",
              ].join(" ")}
            >
              <input
                type="radio"
                name="schedule_mode"
                className="sr-only"
                checked={scheduleMode === "custom"}
                onChange={() => setScheduleMode("custom")}
              />
              ⏰ Turno específico
            </label>
          </div>

          {scheduleMode === "custom" && (
            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-3">
              {/* Dias da semana */}
              <div>
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1.5">
                  Dias da semana
                </span>
                <div className="flex items-center gap-1">
                  {[
                    { d: 1, l: "Seg" },
                    { d: 2, l: "Ter" },
                    { d: 3, l: "Qua" },
                    { d: 4, l: "Qui" },
                    { d: 5, l: "Sex" },
                    { d: 6, l: "Sáb" },
                    { d: 7, l: "Dom" },
                  ].map(({ d, l }) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => toggleWeekday(d)}
                      className={[
                        "flex-1 py-1.5 rounded text-[10px] font-semibold transition",
                        weekdays.includes(d)
                          ? "bg-accent-cyan/15 border border-accent-cyan/40 text-accent-cyan"
                          : "bg-white/[0.02] border border-white/[0.06] text-muted-foreground hover:bg-white/[0.04]",
                      ].join(" ")}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Janela horária */}
              <div className="grid grid-cols-2 gap-2">
                <label className="block space-y-1">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Início
                  </span>
                  <input
                    type="time"
                    className="input w-full font-mono"
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Fim
                  </span>
                  <input
                    type="time"
                    className="input w-full font-mono"
                    value={endTime}
                    onChange={(e) => setEndTime(e.target.value)}
                  />
                </label>
              </div>
              <span className="text-[10px] text-muted-foreground/60 block">
                Turno que cruza meia-noite (ex: 22:00 → 06:00) é aceito —
                fica ativo durante a noite toda.
              </span>
            </div>
          )}
        </div>

        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">Notas (opcional)</span>
          <textarea
            rows={2}
            className="input w-full resize-none"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="ex: plantão revezamento mensal, férias até dd/mm, …"
          />
        </label>

        {err && (
          <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-2.5 text-[11px] text-classification-attention">
            {err}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="text-xs px-3 py-2 rounded-lg hover:bg-white/[0.04] disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Cadastrar contato
          </button>
        </div>
      </form>
    </div>
  );
}
