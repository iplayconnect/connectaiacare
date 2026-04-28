"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mic,
  MicOff,
  ShieldAlert,
  Trash2,
  UploadCloud,
  UserCircle2,
  Users,
  Volume2,
  X,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";
import { hasRole } from "@/lib/permissions";

// ════════════════════════════════════════════════════════════════════
// /admin/biometria-voz
//
// Painel de biometria de voz por tenant. Permite:
//   • Ver cobertura (pacientes + cuidadores enrolados, qualidade média).
//   • Listar pessoas com enrollment ativo + número de amostras.
//   • Cadastrar nova amostra (gravar 5-10s no microfone do navegador).
//   • Revogar enrollment (LGPD: deleta todos embeddings da pessoa).
//
// LGPD: cada enrollment grava em aia_health_voice_consent_log com IP +
// timestamp. Pra revogar, basta o admin clicar — o backend também
// audita o data_deleted.
//
// RBAC: super_admin, admin_tenant, medico, enfermeiro VEEM. Apenas
// super_admin e admin_tenant podem REVOGAR; todos podem cadastrar
// (médicos/enfermeiros costumam fazer enrollment durante consulta).
// ════════════════════════════════════════════════════════════════════

type EnrollmentRow = {
  person_id: string;
  person_type: "caregiver" | "patient";
  full_name: string;
  sample_count: number;
  avg_quality: number | null;
  last_enrollment: string | null;
};

type Coverage = Record<
  string,
  {
    people_enrolled: number;
    samples_total: number;
    avg_quality?: number;
    last_enrollment?: string;
  }
>;

export default function BiometriaVozPage() {
  const { user } = useAuth();
  const canSee = hasRole(
    user,
    "super_admin",
    "admin_tenant",
    "medico",
    "enfermeiro",
  );
  const canRevoke = hasRole(user, "super_admin", "admin_tenant");

  const [enrollments, setEnrollments] = useState<EnrollmentRow[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "caregiver" | "patient">("all");
  const [enrollOpen, setEnrollOpen] = useState(false);

  const reload = () => {
    setLoading(true);
    setErr(null);
    Promise.all([api.voiceListEnrollments(), api.voiceCoverage()])
      .then(([list, cov]) => {
        setEnrollments(list.items);
        setCoverage(cov.coverage);
      })
      .catch((e: any) => setErr(e?.message || "Erro ao carregar"))
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
          Biometria de voz é dado biométrico sensível (LGPD Art. 11).
          Restrito à equipe clínica e administrativa.
        </p>
      </div>
    );
  }

  const filtered = useMemo(() => {
    let r = enrollments;
    if (filter !== "all") r = r.filter((e) => e.person_type === filter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter((e) => e.full_name.toLowerCase().includes(q));
    }
    return r;
  }, [enrollments, search, filter]);

  return (
    <div className="space-y-5 max-w-7xl">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Volume2 className="h-5 w-5 text-accent-cyan" />
            Biometria de Voz — Cadastro & Gestão
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
            Cadastre amostras de voz de pacientes e cuidadores para que a
            Sofia identifique automaticamente quem está reportando sintomas
            via WhatsApp ou ligação. Recomendado 3+ amostras de 5-10
            segundos por pessoa em ambiente silencioso.
          </p>
          <p className="text-[10px] text-muted-foreground/70 mt-1.5 italic max-w-2xl">
            Dado biométrico sensível conforme LGPD Art. 11. Toda
            captura/exclusão é auditada.
          </p>
        </div>
        <button
          onClick={() => setEnrollOpen(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium shadow-glow-cyan hover:brightness-110"
        >
          <Mic className="h-3.5 w-3.5" />
          Cadastrar amostra
        </button>
      </header>

      {coverage && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <CoverageCard
            label="Pacientes"
            icon={UserCircle2}
            people={coverage.patient?.people_enrolled ?? 0}
            samples={coverage.patient?.samples_total ?? 0}
            quality={coverage.patient?.avg_quality}
          />
          <CoverageCard
            label="Cuidadores"
            icon={Users}
            people={coverage.caregiver?.people_enrolled ?? 0}
            samples={coverage.caregiver?.samples_total ?? 0}
            quality={coverage.caregiver?.avg_quality}
          />
          <CoverageCard
            label="Amostras totais"
            icon={UploadCloud}
            people={
              (coverage.patient?.samples_total ?? 0) +
              (coverage.caregiver?.samples_total ?? 0)
            }
            samples={null}
            tagline="todas as enrolladas"
          />
          <CoverageCard
            label="Qualidade média"
            icon={CheckCircle2}
            people={null}
            samples={null}
            tagline={
              coverage.patient?.avg_quality || coverage.caregiver?.avg_quality
                ? `${(((coverage.patient?.avg_quality ?? 0) + (coverage.caregiver?.avg_quality ?? 0)) / 2).toFixed(2)}`
                : "—"
            }
          />
        </div>
      )}

      <div className="flex items-end gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar nome..."
          className="input flex-1 min-w-[200px]"
        />
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as any)}
          className="input max-w-[180px]"
        >
          <option value="all">Todas as pessoas</option>
          <option value="caregiver">Apenas cuidadores</option>
          <option value="patient">Apenas pacientes</option>
        </select>
        <span className="text-xs text-muted-foreground tabular">
          {filtered.length} / {enrollments.length}
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin mr-2" /> Carregando...
        </div>
      ) : err ? (
        <div className="rounded-lg border border-classification-attention/20 bg-classification-attention/5 p-3 text-xs text-classification-attention">
          {err}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState onEnroll={() => setEnrollOpen(true)} />
      ) : (
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-white/[0.02] text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Nome</th>
                <th className="px-3 py-2 text-left">Tipo</th>
                <th className="px-3 py-2 text-left">Amostras</th>
                <th className="px-3 py-2 text-left">Qualidade</th>
                <th className="px-3 py-2 text-left">Última</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <EnrollmentRow
                  key={`${row.person_type}_${row.person_id}`}
                  row={row}
                  canRevoke={canRevoke}
                  onRevoke={async () => {
                    if (
                      !confirm(
                        `Revogar enrollment de ${row.full_name}? Vai apagar TODOS os embeddings dessa pessoa (irreversível).`,
                      )
                    ) {
                      return;
                    }
                    try {
                      if (row.person_type === "caregiver") {
                        await api.voiceCaregiverDelete(row.person_id);
                      } else {
                        await api.voicePatientDelete(row.person_id);
                      }
                      reload();
                    } catch (e: any) {
                      alert(e?.message || "Erro ao revogar");
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {enrollOpen && (
        <EnrollModal
          onClose={() => setEnrollOpen(false)}
          onDone={() => {
            setEnrollOpen(false);
            reload();
          }}
        />
      )}
    </div>
  );
}

// ─── Coverage card ────────────────────────────────────────

function CoverageCard({
  label,
  icon: Icon,
  people,
  samples,
  quality,
  tagline,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  people: number | null;
  samples: number | null;
  quality?: number;
  tagline?: string;
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        <Icon className="h-3.5 w-3.5" />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-2xl font-semibold tabular">
        {people !== null ? people : tagline || "—"}
      </div>
      <div className="text-[10px] text-muted-foreground mt-0.5">
        {samples !== null && samples !== undefined && people !== null
          ? `${samples} amostras${quality ? ` · q≈${quality.toFixed(2)}` : ""}`
          : tagline && people !== null
          ? tagline
          : "—"}
      </div>
    </div>
  );
}

// ─── Enrollment row ───────────────────────────────────────

function EnrollmentRow({
  row,
  canRevoke,
  onRevoke,
}: {
  row: EnrollmentRow;
  canRevoke: boolean;
  onRevoke: () => void;
}) {
  const complete = row.sample_count >= 3;
  return (
    <tr className="border-t border-white/[0.04]">
      <td className="px-3 py-2 font-medium">{row.full_name}</td>
      <td className="px-3 py-2">
        <span
          className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${
            row.person_type === "patient"
              ? "bg-accent-cyan/15 text-accent-cyan"
              : "bg-white/[0.05] text-muted-foreground"
          }`}
        >
          {row.person_type === "patient" ? "Paciente" : "Cuidador"}
        </span>
      </td>
      <td className="px-3 py-2 tabular">
        <span
          className={
            complete
              ? "text-classification-routine"
              : "text-classification-attention"
          }
        >
          {row.sample_count}/3
        </span>
        {complete ? (
          <CheckCircle2 className="inline h-3 w-3 ml-1 text-classification-routine" />
        ) : (
          <AlertCircle className="inline h-3 w-3 ml-1 text-classification-attention" />
        )}
      </td>
      <td className="px-3 py-2 tabular text-muted-foreground">
        {row.avg_quality != null ? row.avg_quality.toFixed(2) : "—"}
      </td>
      <td className="px-3 py-2 text-muted-foreground">
        {row.last_enrollment
          ? new Date(row.last_enrollment).toLocaleDateString("pt-BR")
          : "—"}
      </td>
      <td className="px-3 py-2 text-right">
        {canRevoke && (
          <button
            onClick={onRevoke}
            title="Revogar (LGPD: apaga todos embeddings)"
            className="p-1 rounded hover:bg-classification-attention/10 text-classification-attention"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </td>
    </tr>
  );
}

function EmptyState({ onEnroll }: { onEnroll: () => void }) {
  return (
    <div className="text-center py-16">
      <Mic className="h-10 w-10 mx-auto text-muted-foreground/40 mb-3" />
      <h3 className="text-sm font-semibold">Nenhum enrollment ainda</h3>
      <p className="text-xs text-muted-foreground mt-1 mb-4">
        Cadastre a primeira amostra de voz para que a Sofia comece a
        identificar quem está enviando áudios.
      </p>
      <button
        onClick={onEnroll}
        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium"
      >
        <Mic className="h-3.5 w-3.5" />
        Cadastrar primeira amostra
      </button>
    </div>
  );
}

// ─── Modal de enrollment ──────────────────────────────────

function EnrollModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<"select" | "record" | "review">("select");
  const [personType, setPersonType] = useState<"caregiver" | "patient">("patient");
  const [personId, setPersonId] = useState<string>("");
  const [personName, setPersonName] = useState<string>("");
  const [people, setPeople] = useState<{ id: string; full_name: string }[]>([]);
  const [loadingPeople, setLoadingPeople] = useState(true);

  useEffect(() => {
    setLoadingPeople(true);
    setPersonId("");
    setPersonName("");
    if (personType === "caregiver") {
      api
        .voiceListCaregivers()
        .then((r) =>
          setPeople(
            (r.caregivers || []).map((c) => ({
              id: c.id,
              full_name: c.full_name,
            })),
          ),
        )
        .catch(() => setPeople([]))
        .finally(() => setLoadingPeople(false));
    } else {
      api
        .listPatients()
        .then((r) =>
          setPeople(
            (r.patients || []).map((p: any) => ({
              id: p.id,
              full_name: p.full_name,
            })),
          ),
        )
        .catch(() => setPeople([]))
        .finally(() => setLoadingPeople(false));
    }
  }, [personType]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-[hsl(225,80%,8%)] border border-white/[0.08] rounded-xl w-full max-w-xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Mic className="h-4 w-4 text-accent-cyan" />
            Cadastrar amostra de voz
          </h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-white/[0.05]">
            <X className="h-4 w-4" />
          </button>
        </div>

        {step === "select" && (
          <div className="space-y-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Tipo de pessoa
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setPersonType("patient")}
                  className={`p-3 rounded-lg border text-left ${
                    personType === "patient"
                      ? "bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan"
                      : "border-white/[0.06] hover:bg-white/[0.04]"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <UserCircle2 className="h-4 w-4" />
                    <span className="text-sm font-medium">Paciente</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Voz da própria pessoa monitorada
                  </p>
                </button>
                <button
                  onClick={() => setPersonType("caregiver")}
                  className={`p-3 rounded-lg border text-left ${
                    personType === "caregiver"
                      ? "bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan"
                      : "border-white/[0.06] hover:bg-white/[0.04]"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Users className="h-4 w-4" />
                    <span className="text-sm font-medium">Cuidador</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Familiar, técnico ou auxiliar
                  </p>
                </button>
              </div>
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">
                Selecionar {personType === "patient" ? "paciente" : "cuidador"}
              </div>
              {loadingPeople ? (
                <div className="text-xs text-muted-foreground py-2">
                  <Loader2 className="h-3.5 w-3.5 inline animate-spin mr-1.5" />
                  Carregando...
                </div>
              ) : people.length === 0 ? (
                <div className="text-xs text-muted-foreground py-2">
                  Nenhum cadastrado.
                </div>
              ) : (
                <select
                  value={personId}
                  onChange={(e) => {
                    setPersonId(e.target.value);
                    setPersonName(
                      people.find((p) => p.id === e.target.value)?.full_name || "",
                    );
                  }}
                  className="input"
                >
                  <option value="">— escolher —</option>
                  {people.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.full_name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={onClose} className="text-xs px-3 py-2">
                Cancelar
              </button>
              <button
                disabled={!personId}
                onClick={() => setStep("record")}
                className="px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium disabled:opacity-40"
              >
                Próximo: gravar
              </button>
            </div>
          </div>
        )}

        {step === "record" && (
          <RecordStep
            personType={personType}
            personId={personId}
            personName={personName}
            onBack={() => setStep("select")}
            onDone={onDone}
          />
        )}
      </div>
    </div>
  );
}

// ─── Record step (MediaRecorder API) ──────────────────────

function RecordStep({
  personType,
  personId,
  personName,
  onBack,
  onDone,
}: {
  personType: "caregiver" | "patient";
  personId: string;
  personName: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [recording, setRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  async function start() {
    setErr(null);
    setAudioBlob(null);
    setDuration(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => chunksRef.current.push(e.data);
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        setAudioBlob(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      mr.start();
      recorderRef.current = mr;
      setRecording(true);
      timerRef.current = setInterval(
        () => setDuration((d) => d + 1),
        1000,
      );
    } catch (e: any) {
      setErr(e?.message || "Microfone bloqueado");
    }
  }

  function stop() {
    recorderRef.current?.stop();
    setRecording(false);
    if (timerRef.current) clearInterval(timerRef.current);
  }

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      recorderRef.current?.stream
        ?.getTracks()
        .forEach((t) => t.stop());
    };
  }, []);

  async function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const data = reader.result as string;
        resolve(data.split(",")[1] || "");
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  async function submit() {
    if (!audioBlob) return;
    setSubmitting(true);
    setErr(null);
    try {
      const audio_base64 = await blobToBase64(audioBlob);
      const body = {
        audio_base64,
        sample_label: `enrollment_${new Date().toISOString().slice(0, 19)}`,
        sample_rate: 0,
      };
      const res =
        personType === "patient"
          ? await api.voicePatientEnroll({ patient_id: personId, ...body })
          : await api.voiceCaregiverEnroll({ caregiver_id: personId, ...body });

      setResult(res);
      if (!res.success) {
        setErr(res.message || "Áudio rejeitado");
      }
    } catch (e: any) {
      setErr(e?.message || "Erro ao enviar");
    } finally {
      setSubmitting(false);
    }
  }

  if (result?.success) {
    return (
      <div className="text-center py-6">
        <CheckCircle2 className="h-12 w-12 mx-auto text-classification-routine mb-3" />
        <h3 className="text-sm font-semibold">Amostra cadastrada!</h3>
        <p className="text-xs text-muted-foreground mt-1">
          {personName} agora tem <b>{result.samples_count}</b> amostra(s).
          {result.enrollment_complete
            ? " Enrollment completo (3+ amostras)."
            : ` Faltam ${3 - result.samples_count} amostra(s) pra completar.`}
        </p>
        <p className="text-[10px] text-muted-foreground mt-2">
          Qualidade desta amostra:{" "}
          <span className="tabular">
            {result.quality_score?.toFixed(2) || "?"}
          </span>
        </p>
        <div className="flex justify-center gap-2 mt-5">
          <button
            onClick={() => {
              setResult(null);
              setAudioBlob(null);
              setDuration(0);
            }}
            className="text-xs px-3 py-2 rounded-lg border border-white/[0.06] hover:bg-white/[0.04]"
          >
            Cadastrar outra amostra
          </button>
          <button
            onClick={onDone}
            className="text-xs px-4 py-2 rounded-lg accent-gradient text-slate-900 font-medium"
          >
            Concluir
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-xs">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
          Cadastrando
        </div>
        <div className="font-medium">{personName}</div>
        <div className="text-muted-foreground text-[10px]">
          {personType === "patient" ? "Paciente" : "Cuidador"} ·{" "}
          <span className="tabular">{personId.slice(0, 8)}…</span>
        </div>
      </div>

      <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 text-center">
        {!recording && !audioBlob && (
          <>
            <p className="text-xs text-muted-foreground mb-3">
              Peça pra pessoa falar uma frase neutra por 5-10 segundos
              (ex: "Oi Sofia, meu nome é {personName.split(" ")[0]} e
              estou aqui pra cadastrar minha voz").
            </p>
            <button
              onClick={start}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-sm font-medium"
            >
              <Mic className="h-4 w-4" /> Iniciar gravação
            </button>
          </>
        )}

        {recording && (
          <>
            <div className="text-3xl font-semibold tabular text-classification-attention mb-2">
              {duration}s
            </div>
            <div className="text-xs text-muted-foreground mb-3">
              Gravando... {duration < 5 && "(meta: ≥5s)"}
            </div>
            <button
              onClick={stop}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-classification-attention/15 text-classification-attention border border-classification-attention/30 text-sm font-medium"
            >
              <MicOff className="h-4 w-4" /> Parar
            </button>
          </>
        )}

        {!recording && audioBlob && (
          <>
            <div className="text-xs text-classification-routine mb-3">
              <CheckCircle2 className="h-4 w-4 inline mr-1" />
              Gravado: {duration}s
            </div>
            <audio
              controls
              src={URL.createObjectURL(audioBlob)}
              className="mx-auto w-full max-w-xs"
            />
            <div className="flex justify-center gap-2 mt-4">
              <button
                onClick={() => {
                  setAudioBlob(null);
                  setDuration(0);
                }}
                className="text-xs px-3 py-2 rounded-lg border border-white/[0.06] hover:bg-white/[0.04]"
              >
                Regravar
              </button>
              <button
                disabled={submitting}
                onClick={submit}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg accent-gradient text-slate-900 text-xs font-medium disabled:opacity-50"
              >
                {submitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <UploadCloud className="h-3.5 w-3.5" />
                )}
                Enviar amostra
              </button>
            </div>
          </>
        )}
      </div>

      {err && (
        <div className="text-xs text-classification-attention bg-classification-attention/5 border border-classification-attention/20 rounded p-2">
          {err}
        </div>
      )}

      <div className="flex justify-between pt-2">
        <button onClick={onBack} className="text-xs px-3 py-2">
          ← Trocar pessoa
        </button>
      </div>
    </div>
  );
}
