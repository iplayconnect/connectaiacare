"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Phone,
  PhoneCall,
  PhoneOff,
  Loader2,
  RefreshCw,
  Clock,
  History,
  Activity,
  User,
  Stethoscope,
} from "lucide-react";

import { api, type CallScenario, type CallHistoryItem } from "@/lib/api";

// ═══════════════════════════════════════════════════════════════════
// /comunicacao — hub de ligações Sofia VoIP (outbound only nesta fase)
//
// 3 tabs:
//   • Nova ligação (escolhe cenário + destino + dispara)
//   • Em curso (chamadas ativas no momento)
//   • Histórico (transcrições de calls finalizadas)
// ═══════════════════════════════════════════════════════════════════

type Tab = "new" | "active" | "history";

export default function ComunicacaoPage() {
  const [tab, setTab] = useState<Tab>("new");

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Phone className="h-6 w-6 text-accent-cyan" />
          Comunicação
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Ligações Sofia VoIP — outbound, com cenário, persona e contexto.
        </p>
      </header>

      <div className="flex gap-1 mb-6 border-b border-white/[0.06]">
        {(
          [
            { k: "new", label: "Nova ligação", icon: PhoneCall },
            { k: "active", label: "Em curso", icon: Activity },
            { k: "history", label: "Histórico", icon: History },
          ] as const
        ).map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.k}
              onClick={() => setTab(t.k)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition flex items-center gap-2 ${
                tab === t.k
                  ? "border-accent-cyan text-accent-cyan"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "new" && <NewCallPanel />}
      {tab === "active" && <ActiveCallsPanel />}
      {tab === "history" && <HistoryPanel />}
    </div>
  );
}

// ─── Nova ligação ───────────────────────────────────────────────────

function NewCallPanel() {
  const [scenarios, setScenarios] = useState<CallScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [destination, setDestination] = useState("");
  const [patientId, setPatientId] = useState("");
  const [fullName, setFullName] = useState("");
  const [dialing, setDialing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .communicationsScenarios()
      .then((r) => {
        const outbound = r.scenarios.filter(
          (s) => s.direction === "outbound" && s.active,
        );
        setScenarios(outbound);
        if (outbound.length > 0 && !scenarioId) setScenarioId(outbound[0].id);
      })
      .catch((e) => setError(e?.message || "Erro carregando cenários"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(
    () => scenarios.find((s) => s.id === scenarioId),
    [scenarios, scenarioId],
  );

  async function handleDial() {
    if (!scenarioId || !destination.trim()) {
      setError("Cenário e destino são obrigatórios");
      return;
    }
    setDialing(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.communicationsDial({
        scenario_id: scenarioId,
        destination: destination.trim().replace(/\D/g, ""),
        patient_id: patientId.trim() || undefined,
        full_name: fullName.trim() || undefined,
      });
      setResult(`Ligação iniciada · call_id: ${r.call_id}`);
    } catch (e: any) {
      setError(e?.message || "Falha ao iniciar ligação");
    } finally {
      setDialing(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando cenários…
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <div>
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Cenário
          </label>
          <select
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 focus:border-accent-cyan outline-none text-sm"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label} · persona: {s.persona}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs uppercase tracking-wider text-muted-foreground">
            Telefone destino (E.164 sem +)
          </label>
          <input
            type="tel"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="5551996161700"
            className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 focus:border-accent-cyan outline-none text-sm font-mono"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Nome completo (override)
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Dr. Alexandre Veras"
              className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 focus:border-accent-cyan outline-none text-sm"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-muted-foreground">
              Paciente ID (opcional)
            </label>
            <input
              type="text"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="UUID"
              className="w-full mt-1 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/10 focus:border-accent-cyan outline-none text-sm font-mono"
            />
          </div>
        </div>

        <button
          onClick={handleDial}
          disabled={dialing || !destination.trim() || !scenarioId}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent-cyan text-slate-900 font-medium hover:bg-accent-cyan/90 disabled:opacity-50"
        >
          {dialing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <PhoneCall className="h-4 w-4" />
          )}
          {dialing ? "Discando…" : "Iniciar ligação"}
        </button>

        {result && (
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-300">
            {result}
          </div>
        )}
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
            {error}
          </div>
        )}
      </div>

      {selected && (
        <div className="p-4 rounded-xl border border-white/[0.06] bg-white/[0.02] space-y-3">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Cenário selecionado
            </div>
            <div className="font-semibold mt-1">{selected.label}</div>
            <div className="text-xs text-muted-foreground mt-0.5 font-mono">
              {selected.code}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Persona
            </div>
            <div className="text-sm mt-1 flex items-center gap-1.5">
              <User className="h-3.5 w-3.5" />
              {selected.persona}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Voz
            </div>
            <div className="text-sm mt-1">{selected.voice}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Tools disponíveis
            </div>
            <div className="text-xs mt-1 flex flex-wrap gap-1">
              {selected.allowed_tools.map((t) => (
                <span
                  key={t}
                  className="px-2 py-0.5 rounded bg-white/[0.04] font-mono text-[10px]"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
          {selected.description && (
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">
                Descrição
              </div>
              <p className="text-xs mt-1 text-muted-foreground leading-relaxed">
                {selected.description}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Em curso ───────────────────────────────────────────────────────

function ActiveCallsPanel() {
  const [calls, setCalls] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.communicationsActiveCalls();
      setCalls(r.calls || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  async function handleHangup(id: string) {
    await api.communicationsHangup(id);
    await load();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-muted-foreground">
          {calls.length} chamada{calls.length === 1 ? "" : "s"} em curso
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-white/10 hover:bg-white/[0.04]"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Atualizar
        </button>
      </div>

      {calls.length === 0 ? (
        <div className="p-12 rounded-xl border border-white/[0.06] text-center text-muted-foreground">
          <Activity className="h-8 w-8 mx-auto mb-2 opacity-40" />
          Nenhuma ligação em curso.
        </div>
      ) : (
        <ul className="space-y-2">
          {calls.map((id) => (
            <li
              key={id}
              className="flex items-center justify-between p-3 rounded-lg border border-white/[0.06] bg-emerald-500/5"
            >
              <div className="flex items-center gap-3">
                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-mono text-xs">{id}</span>
              </div>
              <button
                onClick={() => handleHangup(id)}
                className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300"
              >
                <PhoneOff className="h-3.5 w-3.5" />
                Desligar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Histórico ──────────────────────────────────────────────────────

function HistoryPanel() {
  const [history, setHistory] = useState<CallHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [openSession, setOpenSession] = useState<string | null>(null);

  useEffect(() => {
    api
      .communicationsHistory({ limit: 50 })
      .then((r) => setHistory(r.history))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground p-12 justify-center">
        <Loader2 className="h-4 w-4 animate-spin" />
        Carregando…
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {history.length === 0 ? (
        <div className="p-12 rounded-xl border border-white/[0.06] text-center text-muted-foreground">
          Sem ligações ainda.
        </div>
      ) : (
        history.map((h) => (
          <CallHistoryRow
            key={h.id}
            item={h}
            open={openSession === h.id}
            onToggle={() => setOpenSession(openSession === h.id ? null : h.id)}
          />
        ))
      )}
    </div>
  );
}

function CallHistoryRow({
  item,
  open,
  onToggle,
}: {
  item: CallHistoryItem;
  open: boolean;
  onToggle: () => void;
}) {
  const [transcript, setTranscript] = useState<any[]>([]);
  const [loadingTx, setLoadingTx] = useState(false);

  useEffect(() => {
    if (open && transcript.length === 0) {
      setLoadingTx(true);
      api
        .communicationsTranscript(item.id)
        .then((r) => setTranscript(r.transcript))
        .finally(() => setLoadingTx(false));
    }
  }, [open, item.id, transcript.length]);

  return (
    <div className="rounded-lg border border-white/[0.06] overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full p-3 flex items-center justify-between hover:bg-white/[0.03] transition text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <Phone className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">
              {item.patient_nickname ||
                item.patient_name ||
                item.phone ||
                "Desconhecido"}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              persona: {item.persona} · {item.message_count} mensagens
              {item.caller_name ? ` · originada por ${item.caller_name}` : ""}
            </div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground flex items-center gap-1 tabular flex-shrink-0">
          <Clock className="h-3 w-3" />
          {item.last_active_at
            ? new Date(item.last_active_at).toLocaleString("pt-BR")
            : "—"}
        </div>
      </button>
      {open && (
        <div className="border-t border-white/[0.04] p-3 bg-black/20">
          {loadingTx ? (
            <div className="text-xs text-muted-foreground">Carregando transcrição…</div>
          ) : transcript.length === 0 ? (
            <div className="text-xs text-muted-foreground">Sem mensagens.</div>
          ) : (
            <ul className="space-y-2 max-h-96 overflow-y-auto">
              {transcript.map((m, i) => (
                <li
                  key={i}
                  className={`text-xs ${
                    m.role === "user"
                      ? "text-foreground"
                      : m.role === "assistant"
                        ? "text-accent-cyan"
                        : "text-muted-foreground italic"
                  }`}
                >
                  <span className="font-mono opacity-60 mr-1.5">
                    [{m.role}]
                  </span>
                  {m.content || `(tool: ${m.tool_name})`}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
