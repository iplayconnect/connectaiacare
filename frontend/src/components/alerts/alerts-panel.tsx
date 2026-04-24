"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  Heart,
  Info,
  Mic,
  Phone,
  Play,
  Search,
  ShieldAlert,
  Sparkles,
  Thermometer,
  Wind,
  X,
  type LucideIcon,
} from "lucide-react";

import {
  SEVERITY_ORDER,
  STATUS_SYSTEM,
  AlertStatusBadge,
} from "./alert-status-badge";
import { CallConfirmModal } from "./call-confirm-modal";
import type { AlertClassification, ClinicalAlert } from "@/hooks/use-alerts";
import { startVoipCall } from "@/hooks/use-voip";

// ══════════════════════════════════════════════════════════════════
// Panel principal (client component)
// ══════════════════════════════════════════════════════════════════

interface Props {
  initialAlerts: ClinicalAlert[];
}

export function AlertsPanel({ initialAlerts }: Props) {
  const [alerts, setAlerts] = useState<ClinicalAlert[]>(initialAlerts);
  const [filter, setFilter] = useState<AlertClassification | null>(null);
  const [showAck, setShowAck] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialpadFor, setDialpadFor] = useState<ClinicalAlert | null>(null);

  // Contagens sobre alertas ATIVOS (fonte única)
  const liveCounts = useMemo(() => {
    const c: Record<AlertClassification, number> = {
      routine: 0,
      attention: 0,
      urgent: 0,
      critical: 0,
    };
    alerts.forEach((a) => {
      if (!a.acknowledged_at) c[a.classification]++;
    });
    return c;
  }, [alerts]);

  const filtered = useMemo(() => {
    let list = alerts;
    if (!showAck) list = list.filter((a) => !a.acknowledged_at);
    if (filter) list = list.filter((a) => a.classification === filter);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (a) =>
          a.patient.name.toLowerCase().includes(q) ||
          a.excerpt.toLowerCase().includes(q),
      );
    }
    return [...list].sort((a, b) => {
      const s = SEVERITY_ORDER[a.classification] - SEVERITY_ORDER[b.classification];
      if (s !== 0) return s;
      return a.minutes_ago - b.minutes_ago;
    });
  }, [alerts, filter, showAck, query]);

  const selected = useMemo(
    () => alerts.find((a) => a.id === selectedId) ?? null,
    [alerts, selectedId],
  );

  // ─── Actions (optimistic) ─────────────────────────────────────
  const handleAck = (id: string) => {
    setAlerts((prev) =>
      prev.map((a) =>
        a.id === id
          ? {
              ...a,
              acknowledged_at: new Date().toISOString(),
              acknowledged_by: "Enf. Júlia Amorim",
            }
          : a,
      ),
    );
  };
  const handleEscalate = (id: string) => {
    setAlerts((prev) =>
      prev.map((a) =>
        a.id === id ? { ...a, escalated_to: "Dr. Rafael Nunes · plantão" } : a,
      ),
    );
  };
  // Clicar "Ligar família" → abre dialpad (NÃO disca direto)
  const handleCall = (id: string) => {
    const alert = alerts.find((a) => a.id === id);
    if (!alert) return;
    setDialpadFor(alert);
  };

  // User clicou no botão verde "Ligar" DENTRO do dialpad → aí sim disca
  const handleDialpadConfirm = async (finalPhone: string) => {
    const alert = dialpadFor;
    if (!alert) return;
    const id = alert.id;
    const targetName = alert.patient.family_contact?.name ?? "Família";

    // Fecha dialpad imediatamente pra user ver o feedback na lista
    setDialpadFor(null);

    // Otimista: UI mostra "ligando…" enquanto VoIP conecta
    setAlerts((prev) =>
      prev.map((a) =>
        a.id === id
          ? {
              ...a,
              call_state: {
                status: "dialing",
                target: targetName,
                started_at: new Date().toISOString(),
              },
            }
          : a,
      ),
    );

    const result = await startVoipCall({
      destination: finalPhone,
      patient_id: alert.patient.id,
      alert_id: alert.id,
      alert_summary: alert.excerpt,
      caller_name: "Sofia · ConnectaIACare",
      mode: "ai_pipeline",
    });

    if (result.status === "ok") {
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                call_state: {
                  status: (result.call_status as "dialing" | "connected") || "dialing",
                  target: targetName,
                  started_at: new Date().toISOString(),
                  call_id: result.call_id,
                },
              }
            : a,
        ),
      );
    } else {
      setAlerts((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                call_state: {
                  status: "failed",
                  target: result.message || "VoIP indisponível",
                  started_at: new Date().toISOString(),
                },
              }
            : a,
        ),
      );
    }
  };

  const totalActive =
    liveCounts.routine + liveCounts.attention + liveCounts.urgent + liveCounts.critical;

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Hero */}
      <header>
        <div className="flex items-center gap-2 mb-1.5">
          <ShieldAlert className="h-3.5 w-3.5 text-classification-urgent" />
          <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
            Fila de triagem · plantão
          </span>
        </div>
        <h1 className="text-3xl font-bold tracking-tight">
          O que resolver <span className="accent-gradient-text">agora</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-[620px]">
          Alertas ordenados por severidade e recência. Reconheça, escale ou acione a
          família diretamente da lista.
        </p>
      </header>

      {/* Controles */}
      <section className="glass-card rounded-2xl p-4 flex flex-wrap gap-3 items-center">
        <div className="flex flex-wrap gap-2">
          <FilterPill
            label="Todos"
            count={totalActive}
            active={filter === null}
            onClick={() => setFilter(null)}
            colorKey={null}
          />
          {(["critical", "urgent", "attention", "routine"] as AlertClassification[]).map(
            (k) => (
              <FilterPill
                key={k}
                classification={k}
                count={liveCounts[k]}
                active={filter === k}
                onClick={() => setFilter(filter === k ? null : k)}
              />
            ),
          )}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-muted-foreground">
            <input
              type="checkbox"
              checked={showAck}
              onChange={(e) => setShowAck(e.target.checked)}
              className="accent-accent-cyan w-3.5 h-3.5"
            />
            Mostrar reconhecidos
          </label>
          <div className="relative w-60">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground/70 h-3 w-3"
              aria-hidden
            />
            <input
              placeholder="Buscar paciente…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-[hsl(222,30%,10%)] border border-white/10 rounded-lg pl-9 pr-3 py-2 text-xs focus:border-accent-cyan/50 focus:outline-none transition-colors"
            />
          </div>
        </div>
      </section>

      {/* Fila */}
      <section className="glass-card rounded-2xl overflow-hidden">
        {filtered.length === 0 ? (
          <EmptyState />
        ) : (
          filtered.map((a) => (
            <AlertRow
              key={a.id}
              alert={a}
              selected={selectedId === a.id}
              onSelect={setSelectedId}
              onAck={handleAck}
              onEscalate={handleEscalate}
              onCall={handleCall}
            />
          ))
        )}
      </section>

      {selected && (
        <AlertDrawer
          alert={selected}
          onClose={() => setSelectedId(null)}
          onAck={handleAck}
          onEscalate={handleEscalate}
          onCall={handleCall}
        />
      )}

      {/* Dialpad aberto quando user clica "Ligar família" */}
      {dialpadFor && (
        <CallConfirmModal
          alert={dialpadFor}
          onConfirm={handleDialpadConfirm}
          onCancel={() => setDialpadFor(null)}
        />
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Empty state
// ══════════════════════════════════════════════════════════════════

function EmptyState() {
  return (
    <div className="py-16 px-8 text-center">
      <CheckCircle2 className="h-10 w-10 text-classification-routine mx-auto mb-3" />
      <div className="text-base font-semibold">Nenhum alerta pendente</div>
      <div className="text-sm text-muted-foreground mt-1">
        Sua fila está limpa. A equipe está em dia com os reconhecimentos.
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// Filter pill (header)
// ══════════════════════════════════════════════════════════════════

interface FilterPillProps {
  classification?: AlertClassification;
  label?: string;
  count: number;
  active: boolean;
  onClick: () => void;
  colorKey?: AlertClassification | null;
}

function FilterPill({
  classification,
  label,
  count,
  active,
  onClick,
}: FilterPillProps) {
  if (classification) {
    const s = STATUS_SYSTEM[classification];
    const Icon = s.icon;
    return (
      <button
        onClick={onClick}
        aria-pressed={active}
        className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all border"
        style={{
          background: active ? s.colorSoft : "rgba(15, 23, 42, 0.55)",
          borderColor: active ? s.border : "rgba(148, 163, 184, 0.10)",
          color: active ? s.color : "rgba(214, 232, 246, 0.75)",
        }}
      >
        <Icon size={13} strokeWidth={2.5} aria-hidden />
        <span>{s.label}</span>
        <span
          className="font-mono font-bold tabular ml-0.5"
          style={{ color: active ? s.color : "rgba(214, 232, 246, 0.55)" }}
        >
          {count}
        </span>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all border ${
        active
          ? "bg-accent-cyan/8 border-accent-cyan/30 text-accent-cyan"
          : "bg-[hsl(222,30%,10%)]/55 border-white/10 text-foreground/75 hover:bg-white/5"
      }`}
    >
      {label}
      <span
        className={`font-mono font-bold tabular opacity-70 ${active ? "text-accent-cyan" : ""}`}
      >
        {count}
      </span>
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════
// AlertRow
// ══════════════════════════════════════════════════════════════════

interface AlertRowProps {
  alert: ClinicalAlert;
  selected: boolean;
  onSelect: (id: string) => void;
  onAck: (id: string) => void;
  onEscalate: (id: string) => void;
  onCall: (id: string) => void;
}

function AlertRow({
  alert,
  selected,
  onSelect,
  onAck,
  onEscalate,
  onCall,
}: AlertRowProps) {
  const s = STATUS_SYSTEM[alert.classification];
  const isAck = !!alert.acknowledged_at;
  const canCall = alert.classification === "urgent" || alert.classification === "critical";
  const calling = alert.call_state?.status === "dialing";

  const timeLabel =
    alert.minutes_ago < 60
      ? `há ${alert.minutes_ago} min`
      : alert.minutes_ago < 1440
        ? `há ${Math.floor(alert.minutes_ago / 60)} h`
        : `há ${Math.floor(alert.minutes_ago / 1440)} d`;

  const stripeWidth =
    alert.classification === "critical"
      ? 6
      : alert.classification === "urgent"
        ? 4
        : 3;
  const stripeHeight =
    alert.classification === "critical" || alert.classification === "urgent" ? "100%" : "64%";

  return (
    <div
      onClick={() => onSelect(alert.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(alert.id);
        }
      }}
      className={`
        grid items-center gap-4 py-4 pr-5 border-b border-white/5 cursor-pointer transition-colors
        ${selected ? "bg-accent-cyan/5" : isAck ? "bg-[hsl(222,30%,10%)]/25" : "hover:bg-white/[0.02]"}
        ${isAck ? "opacity-60" : ""}
      `}
      style={{
        gridTemplateColumns: "6px 140px 220px 1fr auto auto",
      }}
    >
      {/* Stripe lateral */}
      <div
        className={
          alert.classification === "critical" ? "animate-pulse-soft" : ""
        }
        style={{
          height: stripeHeight,
          width: stripeWidth,
          background: s.color,
          marginLeft: alert.classification === "critical" ? 0 : 1.5,
          borderRadius: "0 3px 3px 0",
          boxShadow:
            alert.classification === "critical"
              ? `0 0 12px ${s.color}55`
              : alert.classification === "urgent"
                ? `0 0 8px ${s.color}33`
                : "none",
        }}
        aria-hidden
      />

      {/* Badge */}
      <div className="pl-2">
        <AlertStatusBadge classification={alert.classification} />
      </div>

      {/* Paciente */}
      <div className="flex items-center gap-3 min-w-0">
        <Avatar
          name={alert.patient.name}
          size={40}
          seed={alert.patient.seed ?? 0}
        />
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">{alert.patient.name}</div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
            {alert.patient.age} a · {alert.patient.ward} · Qto {alert.patient.room}
          </div>
        </div>
      </div>

      {/* Excerpt */}
      <div className="min-w-0">
        <p className="text-[13px] text-foreground/85 line-clamp-2 leading-snug">
          {alert.excerpt}
        </p>
        {alert.ai_reason && (
          <p className="text-[11px] text-accent-cyan/80 line-clamp-1 mt-1 flex items-center gap-1">
            <Sparkles className="h-2.5 w-2.5 flex-shrink-0" />
            <span className="truncate">{alert.ai_reason}</span>
          </p>
        )}
      </div>

      {/* Estado (tempo + ACK/call/escalation) */}
      <div className="flex flex-col items-end gap-1 min-w-[112px]">
        <span className="text-[11px] font-medium text-foreground/65 tabular">
          {timeLabel}
        </span>
        {isAck && (
          <span className="text-[10px] text-classification-routine flex items-center gap-1">
            <CheckCircle2 className="h-2.5 w-2.5" /> ACK ·{" "}
            {alert.acknowledged_by?.split(" ").slice(-1)[0]}
          </span>
        )}
        {calling && (
          <span className="text-[10px] text-classification-urgent flex items-center gap-1">
            <Phone className="h-2.5 w-2.5" /> ligando…
          </span>
        )}
        {alert.call_state?.status === "failed" && (
          <span
            className="text-[10px] text-classification-critical flex items-center gap-1"
            title={alert.call_state.target}
          >
            <Phone className="h-2.5 w-2.5" /> VoIP falhou
          </span>
        )}
        {alert.call_state?.status === "connected" && (
          <span className="text-[10px] text-classification-routine flex items-center gap-1">
            <Phone className="h-2.5 w-2.5" /> em chamada
          </span>
        )}
        {alert.escalated_to && (
          <span className="text-[10px] text-purple-400 flex items-center gap-1">
            <ArrowUpRight className="h-2.5 w-2.5" /> escalado
          </span>
        )}
      </div>

      {/* Ações inline */}
      <div
        className="flex gap-1.5"
        onClick={(e) => e.stopPropagation()}
      >
        {!isAck && (
          <IconBtn
            label="Reconhecer (ACK)"
            onClick={() => onAck(alert.id)}
            Icon={CheckCircle2}
            tone="routine"
          />
        )}
        {!isAck && (
          <IconBtn
            label="Escalar ao médico"
            onClick={() => onEscalate(alert.id)}
            Icon={ArrowUpRight}
            tone="accent"
          />
        )}
        {canCall && !isAck && (
          <IconBtn
            label="Ligar para família (Sofia Voz)"
            onClick={() => onCall(alert.id)}
            Icon={Phone}
            tone="urgent"
            active={calling}
          />
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// IconBtn
// ══════════════════════════════════════════════════════════════════

interface IconBtnProps {
  Icon: LucideIcon;
  label: string;
  onClick: () => void;
  tone?: "default" | "routine" | "accent" | "urgent";
  active?: boolean;
}

function IconBtn({ Icon, label, onClick, tone = "default", active = false }: IconBtnProps) {
  const tones = {
    default: {
      fg: "rgba(214,232,246,0.75)",
      bg: "rgba(255,255,255,0.04)",
      bd: "rgba(255,255,255,0.08)",
    },
    routine: { fg: "#6ee7b7", bg: "rgba(52,211,153,0.10)", bd: "rgba(52,211,153,0.28)" },
    accent: { fg: "#31e1ff", bg: "rgba(49,225,255,0.08)", bd: "rgba(49,225,255,0.26)" },
    urgent: { fg: "#fb923c", bg: "rgba(251,146,60,0.10)", bd: "rgba(251,146,60,0.32)" },
  }[tone];

  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className="rounded-lg grid place-items-center transition-all hover:brightness-125"
      style={{
        width: 34,
        height: 34,
        background: active ? tones.fg : tones.bg,
        border: `1px solid ${tones.bd}`,
        color: active ? "#050b1f" : tones.fg,
      }}
    >
      <Icon size={15} strokeWidth={2} />
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════
// Avatar (simples, por seed)
// ══════════════════════════════════════════════════════════════════

function Avatar({ name, size = 40, seed = 0 }: { name: string; size?: number; seed?: number }) {
  const initials = name
    .split(" ")
    .filter((n) => n.length > 1)
    .slice(0, 2)
    .map((n) => n[0])
    .join("")
    .toUpperCase();

  const hues = [195, 165, 25, 340, 270, 45];
  const hue = hues[seed % hues.length];

  return (
    <div
      className="rounded-full flex items-center justify-center font-bold text-slate-900 flex-shrink-0 border border-white/10"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: `linear-gradient(135deg, hsl(${hue}, 85%, 70%) 0%, hsl(${hue - 20}, 70%, 50%) 100%)`,
      }}
    >
      {initials}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
// AlertDrawer (detalhes)
// ══════════════════════════════════════════════════════════════════

interface AlertDrawerProps {
  alert: ClinicalAlert;
  onClose: () => void;
  onAck: (id: string) => void;
  onEscalate: (id: string) => void;
  onCall: (id: string) => void;
}

function AlertDrawer({ alert, onClose, onAck, onEscalate, onCall }: AlertDrawerProps) {
  const [tab, setTab] = useState<"relato" | "transcricao" | "vitais" | "historico">(
    "relato",
  );
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const s = STATUS_SYSTEM[alert.classification];
  const canCall = alert.classification === "urgent" || alert.classification === "critical";
  const isAck = !!alert.acknowledged_at;
  const calling = alert.call_state?.status === "dialing";

  // Lock body scroll enquanto drawer aberto
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, []);

  // Esc fecha drawer
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const tabs: { k: typeof tab; label: string }[] = [
    { k: "relato", label: "Relato" },
    { k: "transcricao", label: "Transcrição" },
    { k: "vitais", label: "Vitais" },
    { k: "historico", label: "Histórico 30d" },
  ];

  if (!mounted) return null;

  // Portal pra document.body — escapa do stacking context do <main z-10>
  return createPortal(
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm"
        style={{ animation: "fade-in 160ms ease" }}
        aria-hidden
      />

      {/* Drawer */}
      <aside
        role="dialog"
        aria-label={`Detalhes do alerta de ${alert.patient.name}`}
        className="fixed top-0 right-0 bottom-0 z-[101] flex flex-col bg-[hsl(222,47%,7%)]/98 shadow-[-24px_0_48px_rgba(0,0,0,0.5)]"
        style={{
          width: "min(640px, 48vw)",
          borderLeft: `3px solid ${s.color}`,
          animation: "slide-in-right 280ms cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-white/10">
          <div className="flex items-start justify-between gap-3">
            <AlertStatusBadge classification={alert.classification} />
            <button
              onClick={onClose}
              aria-label="Fechar"
              className="w-8 h-8 rounded-lg border border-white/10 bg-white/5 text-foreground/80 grid place-items-center hover:bg-white/10 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
          <div className="mt-3.5 flex items-center gap-3.5">
            <Avatar name={alert.patient.name} size={52} seed={alert.patient.seed ?? 0} />
            <div className="min-w-0">
              <h2 className="text-lg font-bold truncate">{alert.patient.name}</h2>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mt-1">
                {alert.patient.age} anos · {alert.patient.ward} · Quarto {alert.patient.room}
              </p>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-6 border-b border-white/10">
          {tabs.map((t) => (
            <button
              key={t.k}
              onClick={() => setTab(t.k)}
              aria-selected={tab === t.k}
              role="tab"
              className={`px-3.5 py-3 text-xs font-semibold border-b-2 transition-colors ${
                tab === t.k
                  ? "border-accent-cyan text-foreground"
                  : "border-transparent text-foreground/60 hover:text-foreground/90"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {tab === "relato" && <RelatoTab alert={alert} />}
          {tab === "transcricao" && <TranscricaoTab alert={alert} />}
          {tab === "vitais" && <VitaisTab alert={alert} />}
          {tab === "historico" && <HistoricoTab alert={alert} />}
        </div>

        {/* Footer actions */}
        <div className="px-6 py-3.5 border-t border-white/10 bg-[hsl(222,30%,10%)]/60 flex gap-2.5 items-center">
          {isAck ? (
            <div className="flex-1 text-xs text-classification-routine flex items-center gap-2">
              <CheckCircle2 size={14} /> Reconhecido por{" "}
              <strong className="text-foreground">{alert.acknowledged_by}</strong>
            </div>
          ) : (
            <>
              <ActionButton
                Icon={CheckCircle2}
                label="Reconhecer"
                onClick={() => onAck(alert.id)}
                tone="routine"
                primary
              />
              <ActionButton
                Icon={ArrowUpRight}
                label="Escalar ao médico"
                onClick={() => onEscalate(alert.id)}
                tone="accent"
              />
              {canCall && (
                <ActionButton
                  Icon={Phone}
                  label={calling ? "Ligando…" : "Ligar para família"}
                  onClick={() => onCall(alert.id)}
                  tone="urgent"
                  disabled={calling}
                />
              )}
            </>
          )}
        </div>
      </aside>
    </>,
    document.body,
  );
}

// ══════════════════════════════════════════════════════════════════
// ActionButton (drawer)
// ══════════════════════════════════════════════════════════════════

interface ActionButtonProps {
  Icon: LucideIcon;
  label: string;
  onClick: () => void;
  tone: "routine" | "accent" | "urgent";
  primary?: boolean;
  disabled?: boolean;
}

function ActionButton({
  Icon,
  label,
  onClick,
  tone,
  primary = false,
  disabled = false,
}: ActionButtonProps) {
  const tones = {
    routine: { fg: "#34d399", bg: "rgba(52,211,153,0.14)", bd: "rgba(52,211,153,0.40)" },
    accent: { fg: "#31e1ff", bg: "rgba(49,225,255,0.10)", bd: "rgba(49,225,255,0.34)" },
    urgent: { fg: "#fb923c", bg: "rgba(251,146,60,0.14)", bd: "rgba(251,146,60,0.42)" },
  }[tone];

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-60 disabled:cursor-wait"
      style={{
        background: primary ? tones.fg : tones.bg,
        color: primary ? "#050b1f" : tones.fg,
        border: `1px solid ${primary ? tones.fg : tones.bd}`,
      }}
    >
      <Icon size={14} strokeWidth={2.5} /> {label}
    </button>
  );
}

// ══════════════════════════════════════════════════════════════════
// Tabs
// ══════════════════════════════════════════════════════════════════

function RelatoTab({ alert }: { alert: ClinicalAlert }) {
  return (
    <div className="flex flex-col gap-4">
      <Section title="Observação do cuidador">
        <p className="text-sm leading-relaxed text-foreground/90">{alert.excerpt}</p>
      </Section>
      {alert.ai_reason && (
        <Section title="Análise clínica da IA" accent>
          <p className="text-sm leading-relaxed text-foreground/90">{alert.ai_reason}</p>
          <p className="text-[11px] text-muted-foreground/70 mt-2.5 flex items-start gap-1.5 italic">
            <Info className="h-3 w-3 mt-0.5 flex-shrink-0" />
            A IA apoia o plantão; a decisão clínica é do médico responsável (CFM 2.314/2022).
          </p>
        </Section>
      )}
      <Section title="Timestamp">
        <div className="text-sm text-foreground/85">
          Criado{" "}
          {new Date(alert.created_at).toLocaleString("pt-BR", {
            dateStyle: "short",
            timeStyle: "short",
          })}
        </div>
      </Section>
    </div>
  );
}

function TranscricaoTab({ alert: _alert }: { alert: ClinicalAlert }) {
  return (
    <div>
      <div className="flex items-center gap-3 p-4 rounded-xl bg-[hsl(222,30%,10%)]/60 border border-white/10 mb-3.5">
        <Mic className="h-[18px] w-[18px] text-accent-cyan" />
        <div className="flex-1">
          <div className="text-sm font-semibold">Áudio original · 1min 24s</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            Cuidadora: Joana Pereira · transcrito em pt-BR
          </div>
        </div>
        <button className="w-9 h-9 rounded-full accent-gradient grid place-items-center">
          <Play size={14} className="text-slate-900 ml-0.5" />
        </button>
      </div>
      <p className="p-4 rounded-lg bg-[hsl(222,30%,10%)]/40 border border-white/5 text-sm leading-relaxed text-foreground/85">
        <em className="not-italic text-muted-foreground/60 tabular">[00:04] </em>
        Doutor, a dona Maria depois do almoço ficou meio esquisita, não quis tomar o
        remédio, tá falando embolado…
        <em className="not-italic text-muted-foreground/60"> [00:18] </em>
        Aferi a pressão aqui, deu cento e setenta por cem, ela tá suando frio também…
        <em className="not-italic text-muted-foreground/60"> [00:34] </em>
        Nunca vi ela assim, sempre tá bem depois do almoço. Acho que é bom chamar alguém.
      </p>
    </div>
  );
}

function VitaisTab({ alert }: { alert: ClinicalAlert }) {
  const v = alert.vitals_snapshot || {};
  const items: { Icon: LucideIcon; label: string; value?: string | number; unit: string }[] =
    [
      { Icon: Heart, label: "Pressão arterial", value: v.bp, unit: "mmHg" },
      { Icon: Activity, label: "Freq. cardíaca", value: v.hr, unit: "bpm" },
      { Icon: Wind, label: "Saturação O₂", value: v.spo2, unit: "%" },
      { Icon: Thermometer, label: "Temperatura", value: v.temp, unit: "°C" },
    ];

  return (
    <div className="grid grid-cols-2 gap-2.5">
      {items.map(({ Icon, label, value, unit }) => (
        <div
          key={label}
          className="p-3.5 rounded-xl bg-[hsl(222,30%,10%)]/55 border border-white/5"
        >
          <div className="flex items-center gap-2 mb-2">
            <Icon size={14} className="text-muted-foreground/70" />
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
              {label}
            </span>
          </div>
          <div className="text-2xl font-bold tabular tracking-tight">
            {value ?? "—"}
            <span className="text-sm text-muted-foreground ml-1 font-medium">{unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function HistoricoTab({ alert }: { alert: ClinicalAlert }) {
  const events: { t: string; label: string; cls: AlertClassification; active?: boolean }[] = [
    { t: "hoje · 14:32", label: "Relato atual", cls: alert.classification, active: true },
    { t: "ontem · 22:14", label: "Dor torácica (SCA)", cls: "critical" },
    { t: "há 3 dias · 09:40", label: "Glicemia 218 mg/dL", cls: "attention" },
    { t: "há 7 dias · 11:10", label: "Aferição de rotina", cls: "routine" },
    { t: "há 12 dias · 08:50", label: "Aferição de rotina", cls: "routine" },
    { t: "há 21 dias · 16:22", label: "Queixa de tontura leve", cls: "attention" },
  ];

  return (
    <ul className="space-y-0.5">
      {events.map((e, i) => {
        const s = STATUS_SYSTEM[e.cls];
        return (
          <li
            key={i}
            className={`flex items-center gap-3.5 py-2.5 border-b border-white/5 last:border-b-0 ${
              !e.active ? "opacity-75" : ""
            }`}
          >
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{
                background: s.color,
                boxShadow: e.active ? `0 0 10px ${s.color}` : "none",
              }}
            />
            <div className="flex-1 min-w-0">
              <div
                className={`text-sm font-semibold truncate ${
                  e.active ? "text-foreground" : "text-foreground/85"
                }`}
              >
                {e.label}
              </div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
                {e.t}
              </div>
            </div>
            <AlertStatusBadge classification={e.cls} size="sm" />
          </li>
        );
      })}
    </ul>
  );
}

function Section({
  title,
  children,
  accent = false,
}: {
  title: string;
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div>
      <div
        className={`text-[10px] uppercase tracking-[0.14em] font-semibold mb-2 inline-flex items-center gap-1.5 ${
          accent ? "text-accent-cyan" : "text-muted-foreground"
        }`}
      >
        {accent && <Sparkles size={11} />} {title}
      </div>
      <div
        className={`p-3.5 rounded-xl border ${
          accent
            ? "bg-accent-cyan/5 border-accent-cyan/20"
            : "bg-[hsl(222,30%,10%)]/55 border-white/5"
        }`}
      >
        {children}
      </div>
    </div>
  );
}
