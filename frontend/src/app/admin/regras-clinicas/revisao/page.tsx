"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Filter,
  Loader2,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ════════════════════════════════════════════════════════════════════
// /admin/regras-clinicas/revisao
//
// Fila unificada de regras com review_status='auto_pending' aguardando
// curadoria clínica. Cada item vem de uma tabela do motor (dose máxima,
// contraindicação Beers, ACB, fall risk). O revisor:
//   • Aprova → review_status='verified' (+ audit_log + reviewed_by)
//   • Rejeita → active=FALSE (+ motivo obrigatório)
//
// RBAC: super_admin e admin_tenant aprovam/rejeitam. Médico/enfermeiro
// só visualiza fila pendente (sem ação).
// ════════════════════════════════════════════════════════════════════

type TableSlug = "dose_limits" | "contraindications" | "acb" | "fall_risk";

type ReviewBundle = {
  total_pending: number;
  by_table: Record<
    string,
    {
      label: string;
      table: string;
      count: number;
      items: Record<string, any>[];
    }
  >;
};

const TABS: { slug: TableSlug; short: string }[] = [
  { slug: "dose_limits", short: "Dose máxima" },
  { slug: "contraindications", short: "Beers/Condição" },
  { slug: "acb", short: "ACB Score" },
  { slug: "fall_risk", short: "Risco queda" },
];

export default function ClinicalReviewPage() {
  const { user } = useAuth();
  const canAct = hasRole(user, "super_admin", "admin_tenant");
  const canSee =
    canAct || hasRole(user, "medico", "enfermeiro");

  const [bundle, setBundle] = useState<ReviewBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<TableSlug>("dose_limits");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [reject, setReject] = useState<{
    slug: TableSlug;
    rowId: string;
    label: string;
  } | null>(null);

  const reload = () => {
    setLoading(true);
    setErr(null);
    api
      .clinicalReviewPending()
      .then((r) => setBundle({ total_pending: r.total_pending, by_table: r.by_table }))
      .catch((e: any) => setErr(e?.message || "Erro ao carregar fila"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (canSee) reload();
  }, [canSee]);

  if (!canSee) {
    return (
      <div className="rounded-xl border border-classification-attention/20 bg-classification-attention/5 p-6 text-center max-w-md mx-auto">
        <ShieldAlert className="h-8 w-8 mx-auto text-classification-attention mb-2" />
        <h2 className="text-sm font-semibold">Acesso restrito</h2>
        <p className="text-xs text-muted-foreground mt-1">
          A revisão clínica é exclusiva da equipe técnica (admin, médico,
          enfermeiro).
        </p>
      </div>
    );
  }

  const counts = bundle?.by_table || {};
  const items = bundle?.by_table?.[tab]?.items || [];
  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((it) =>
      Object.values(it).some(
        (v) => typeof v === "string" && v.toLowerCase().includes(q),
      ),
    );
  }, [items, search]);

  async function approve(slug: TableSlug, rowId: string) {
    setBusyId(rowId);
    try {
      await api.clinicalReviewApprove(slug, rowId);
      reload();
    } catch (e: any) {
      alert(e?.message || "Erro ao aprovar");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5 max-w-7xl">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-accent-cyan" />
            Revisão Clínica — Fila de Curadoria
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
            Regras populadas automaticamente a partir de fontes (RENAME 2024,
            Beers, STOPP/START) que aguardam validação por curador clínico.
            Cada aprovação muda a flag para <span className="tabular">verified</span>{" "}
            e remove o aviso "fonte preliminar" das respostas da Sofia.
          </p>
        </div>
        {bundle && (
          <div className="rounded-lg border border-accent-cyan/20 bg-accent-cyan/5 px-3 py-2 text-xs">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Pendentes
            </div>
            <div className="text-2xl font-semibold tabular text-accent-cyan">
              {bundle.total_pending}
            </div>
          </div>
        )}
      </header>

      {!canAct && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs text-muted-foreground flex items-start gap-2">
          <AlertTriangle className="h-3.5 w-3.5 text-classification-attention flex-shrink-0 mt-0.5" />
          <span>
            Você tem permissão de <b>visualização</b>. Aprovação e rejeição
            estão restritas a super_admin e admin_tenant.
          </span>
        </div>
      )}

      <nav className="flex flex-wrap gap-1.5 border-b border-white/[0.06] pb-2">
        {TABS.map((t) => {
          const c = counts[t.slug]?.count ?? 0;
          const active = tab === t.slug;
          return (
            <button
              key={t.slug}
              onClick={() => setTab(t.slug)}
              className={`text-xs px-3 py-1.5 rounded-md transition-all flex items-center gap-1.5 ${
                active
                  ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan"
                  : "border border-transparent hover:bg-white/[0.04] text-muted-foreground"
              }`}
            >
              <span>{t.short}</span>
              <span
                className={`tabular px-1.5 py-0.5 rounded text-[10px] ${
                  c > 0
                    ? "bg-classification-attention/15 text-classification-attention"
                    : "bg-white/[0.05] text-muted-foreground"
                }`}
              >
                {c}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="flex items-end gap-2">
        <div className="flex-1 relative">
          <Filter className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/50" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por princípio, classe, condição..."
            className="input pl-8"
          />
        </div>
        <span className="text-xs text-muted-foreground tabular">
          {filtered.length} / {items.length}
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando fila...
        </div>
      ) : err ? (
        <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention">
          {err}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-2">
          {filtered.map((it, idx) => (
            <ReviewCard
              key={String(it.row_id || idx)}
              tab={tab}
              item={it}
              canAct={canAct}
              busy={busyId === String(it.row_id)}
              onApprove={() => approve(tab, String(it.row_id))}
              onReject={() =>
                setReject({
                  slug: tab,
                  rowId: String(it.row_id),
                  label:
                    it.principle_active ||
                    it.condition_term ||
                    it.therapeutic_class ||
                    String(it.row_id),
                })
              }
            />
          ))}
        </div>
      )}

      {reject && (
        <RejectModal
          target={reject}
          onClose={() => setReject(null)}
          onDone={() => {
            setReject(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ─── Card por linha ───────────────────────────────────────

function ReviewCard({
  tab,
  item,
  canAct,
  busy,
  onApprove,
  onReject,
}: {
  tab: TableSlug;
  item: Record<string, any>;
  canAct: boolean;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const title =
    item.principle_active ||
    item.condition_term ||
    item.therapeutic_class ||
    "(sem rótulo)";

  const subtitle =
    tab === "dose_limits"
      ? `${item.max_daily_dose_value || "?"} ${
          item.max_daily_dose_unit || ""
        } / dia · ${item.therapeutic_class || "—"}`
      : tab === "contraindications"
      ? `Afeta: ${
          item.affected_principle_active ||
          item.affected_therapeutic_class ||
          "—"
        } · ${item.severity || "—"}`
      : tab === "acb"
      ? `Score ${item.burden_score ?? "?"} · ${item.notes || "—"}`
      : `Risco ${item.fall_risk_score ?? "?"} · ${item.therapeutic_class || "—"}`;

  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 hover:bg-white/[0.03] transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-medium text-sm">{title}</span>
            <span className="px-1.5 py-0.5 rounded bg-classification-attention/15 text-classification-attention text-[10px] uppercase tracking-wider">
              auto_pending
            </span>
          </div>
          <div className="text-xs text-muted-foreground">{subtitle}</div>

          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
            {Object.entries(item).map(([k, v]) => {
              if (k === "row_id") return null;
              if (v == null || v === "") return null;
              if (
                ["principle_active", "condition_term", "therapeutic_class"].includes(
                  k,
                ) &&
                v === title
              ) {
                return null;
              }
              const text = typeof v === "object" ? JSON.stringify(v) : String(v);
              if (text.length > 240) return null;
              return (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 text-muted-foreground"
                >
                  <span className="text-[10px] uppercase tracking-wider opacity-70">
                    {k.replace(/_/g, " ")}:
                  </span>
                  <span className="text-foreground/80">{text}</span>
                </span>
              );
            })}
          </div>
        </div>

        {canAct && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              disabled={busy}
              onClick={onApprove}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-classification-routine/10 text-classification-routine border border-classification-routine/20 hover:bg-classification-routine/15 text-xs font-medium disabled:opacity-50"
              title="Aprovar (verified)"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ThumbsUp className="h-3.5 w-3.5" />
              )}
              Aprovar
            </button>
            <button
              disabled={busy}
              onClick={onReject}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-classification-attention/10 text-classification-attention border border-classification-attention/20 hover:bg-classification-attention/15 text-xs font-medium disabled:opacity-50"
              title="Rejeitar (desativa)"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
              Rejeitar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-16">
      <CheckCircle2 className="h-10 w-10 mx-auto text-classification-routine mb-3" />
      <h3 className="text-sm font-semibold">Fila vazia nesta dimensão</h3>
      <p className="text-xs text-muted-foreground mt-1">
        Sem regras aguardando revisão. Volte quando novos fármacos forem
        importados.
      </p>
    </div>
  );
}

// ─── Modal de rejeição ────────────────────────────────────

function RejectModal({
  target,
  onClose,
  onDone,
}: {
  target: { slug: TableSlug; rowId: string; label: string };
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!reason.trim()) {
      setErr("Motivo obrigatório.");
      return;
    }
    setErr(null);
    setSaving(true);
    try {
      await api.clinicalReviewReject(target.slug, target.rowId, reason.trim());
      onDone();
    } catch (e: any) {
      setErr(e?.message || "Erro ao rejeitar");
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
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <ThumbsDown className="h-4 w-4 text-classification-attention" />
            Rejeitar regra
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/[0.05]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="text-xs text-muted-foreground mb-3">
          Vai desativar (active=FALSE) a regra <b>{target.label}</b>. O motor
          deixa de aplicá-la, mas o registro fica preservado pra auditoria.
        </p>

        <form onSubmit={submit} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-[11px] text-muted-foreground">
              Motivo da rejeição *
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="ex: dose máxima divergente da bula ANVISA, fonte primária não confiável, classe genérica demais..."
              className="input resize-none"
            />
          </label>

          {err && (
            <div className="text-xs text-classification-attention">{err}</div>
          )}

          <div className="flex justify-end gap-2 pt-1">
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
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-classification-attention/15 text-classification-attention border border-classification-attention/30 text-xs font-medium hover:bg-classification-attention/20 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ThumbsDown className="h-3.5 w-3.5" />
              )}
              Confirmar rejeição
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
