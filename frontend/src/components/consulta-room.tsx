"use client";

import {
  LocalParticipant,
  RemoteParticipant,
  RemoteTrack,
  RemoteTrackPublication,
  Room,
  RoomEvent,
  Track,
  createLocalTracks,
} from "livekit-client";
import {
  AlertTriangle,
  Clock,
  HeartPulse,
  Loader2,
  Mic,
  MicOff,
  PhoneOff,
  Signal,
  Video as VideoIcon,
  VideoOff,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

// ═══════════════════════════════════════════════════════════════
// ConsultaRoom — sala de teleconsulta via LiveKit
// Layout premium: vídeo remoto grande + PiP local + controles inferior
// ═══════════════════════════════════════════════════════════════

const LIVEKIT_WS_URL =
  process.env.NEXT_PUBLIC_LIVEKIT_WS_URL || "wss://meet.connectaia.com.br";

type ConnectionState =
  | "idle"
  | "requesting_media"
  | "connecting"
  | "waiting_other"
  | "in_call"
  | "disconnected"
  | "error";

const API_BASE =
  typeof window === "undefined"
    ? process.env.INTERNAL_API_URL || "http://api:5055"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export function ConsultaRoom({
  roomName,
  token: initialToken,
  role,
  teleconsultaId,
}: {
  roomName: string;
  token: string;
  role: "doctor" | "patient";
  teleconsultaId?: string;
}) {
  const [connState, setConnState] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [remoteParticipantName, setRemoteParticipantName] = useState<string>("");
  const [elapsed, setElapsed] = useState<number>(0);
  const [micEnabled, setMicEnabled] = useState(true);
  const [camEnabled, setCamEnabled] = useState(true);

  // Token pode vir direto na URL (fluxo /events/:id/start) OU ser fetched
  // on-demand (fluxo /teleconsulta/agendar que gera link sem token).
  const [token, setToken] = useState<string>(initialToken);
  const [fetchingToken, setFetchingToken] = useState<boolean>(!initialToken);

  // Busca token automaticamente quando o link vem sem
  useEffect(() => {
    if (initialToken) return; // já tem token, nada a fazer
    if (!roomName) return;

    let mounted = true;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/teleconsulta/${encodeURIComponent(roomName)}/token?role=${role}`,
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          if (mounted) {
            setError(
              body.message || `Não foi possível acessar a sala (HTTP ${res.status})`,
            );
            setConnState("error");
            setFetchingToken(false);
          }
          return;
        }
        const data = await res.json();
        if (mounted && data.token) {
          setToken(data.token);
          setFetchingToken(false);
        }
      } catch (err) {
        if (mounted) {
          setError(
            err instanceof Error
              ? `Erro de rede: ${err.message}`
              : "Erro de rede ao buscar token",
          );
          setConnState("error");
          setFetchingToken(false);
        }
      }
    })();

    return () => {
      mounted = false;
    };
  }, [initialToken, roomName, role]);

  const roomRef = useRef<Room | null>(null);
  const localVideoRef = useRef<HTMLVideoElement | null>(null);
  const remoteVideoRef = useRef<HTMLVideoElement | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const startTimeRef = useRef<number | null>(null);

  // Timer da chamada (só conta quando ambos presentes)
  useEffect(() => {
    if (connState !== "in_call") return;
    if (startTimeRef.current == null) {
      startTimeRef.current = Date.now();
    }
    const id = setInterval(() => {
      if (startTimeRef.current) {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(id);
  }, [connState]);

  // Conecta quando token estiver disponível.
  // Se ainda estamos buscando token (quick-token), aguarda.
  useEffect(() => {
    if (fetchingToken) return; // aguarda fetch
    if (!token) {
      // Só considera erro se o fetch terminou e mesmo assim não temos token
      if (connState !== "error") {
        setError("Token ausente — link inválido ou expirado");
        setConnState("error");
      }
      return;
    }

    let mounted = true;
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      videoCaptureDefaults: { resolution: { width: 1280, height: 720 } },
    });
    roomRef.current = room;

    // Handlers
    room
      .on(RoomEvent.Connected, () => {
        if (!mounted) return;
        const participantCount = room.remoteParticipants.size;
        setConnState(participantCount > 0 ? "in_call" : "waiting_other");
        if (participantCount > 0) {
          const other = Array.from(room.remoteParticipants.values())[0];
          setRemoteParticipantName(other.name || other.identity);
          attachRemoteTracks(other);
        }
      })
      .on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
        if (!mounted) return;
        setRemoteParticipantName(p.name || p.identity);
        setConnState("in_call");
        attachRemoteTracks(p);
      })
      .on(RoomEvent.ParticipantDisconnected, () => {
        if (!mounted) return;
        if (room.remoteParticipants.size === 0) {
          setConnState("waiting_other");
          setRemoteParticipantName("");
        }
      })
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub: RemoteTrackPublication, p: RemoteParticipant) => {
        if (!mounted) return;
        if (track.kind === Track.Kind.Video && remoteVideoRef.current) {
          track.attach(remoteVideoRef.current);
        } else if (track.kind === Track.Kind.Audio && remoteAudioRef.current) {
          track.attach(remoteAudioRef.current);
        }
        setRemoteParticipantName(p.name || p.identity);
      })
      .on(RoomEvent.Disconnected, () => {
        if (!mounted) return;
        setConnState("disconnected");
      });

    async function connect() {
      try {
        setConnState("requesting_media");
        const tracks = await createLocalTracks({ audio: true, video: true });
        if (!mounted) return;

        setConnState("connecting");
        await room.connect(LIVEKIT_WS_URL, token);
        if (!mounted) return;

        for (const t of tracks) {
          await room.localParticipant.publishTrack(t);
          if (t.kind === Track.Kind.Video && localVideoRef.current) {
            t.attach(localVideoRef.current);
          }
        }
      } catch (err) {
        if (!mounted) return;
        console.error("livekit_connect_failed", err);
        setError(err instanceof Error ? err.message : "Falha ao conectar na sala");
        setConnState("error");
      }
    }

    connect();

    return () => {
      mounted = false;
      room.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, fetchingToken]);

  function attachRemoteTracks(p: RemoteParticipant) {
    for (const pub of p.trackPublications.values()) {
      if (pub.track) {
        if (pub.track.kind === Track.Kind.Video && remoteVideoRef.current) {
          pub.track.attach(remoteVideoRef.current);
        } else if (pub.track.kind === Track.Kind.Audio && remoteAudioRef.current) {
          pub.track.attach(remoteAudioRef.current);
        }
      }
    }
  }

  async function toggleMic() {
    const room = roomRef.current;
    if (!room) return;
    await (room.localParticipant as LocalParticipant).setMicrophoneEnabled(!micEnabled);
    setMicEnabled(!micEnabled);
  }

  async function toggleCam() {
    const room = roomRef.current;
    if (!room) return;
    await (room.localParticipant as LocalParticipant).setCameraEnabled(!camEnabled);
    setCamEnabled(!camEnabled);
  }

  async function endCall() {
    const room = roomRef.current;
    if (room) await room.disconnect();

    if (role === "doctor" && teleconsultaId) {
      // Médico: navega pro editor SOAP — fluxo pós-consulta
      window.location.href = `/teleconsulta/${teleconsultaId}/documentacao`;
    } else {
      // Paciente: exibe tela de agradecimento ou fecha aba
      window.location.href = "/consulta/finalizada";
    }
  }

  return (
    <div className="w-full h-full flex flex-col text-foreground">
      {/* Ambient gradient */}
      <div
        aria-hidden
        className="fixed inset-0 pointer-events-none z-0"
        style={{
          background:
            "radial-gradient(1200px circle at 20% 0%, hsla(187,100%,40%,0.10), transparent 55%), radial-gradient(1000px circle at 85% 30%, hsla(160,84%,39%,0.07), transparent 60%)",
        }}
      />

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-6 py-3 border-b border-white/[0.05] bg-[hsl(225,80%,7%)]/70 backdrop-blur-xl flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="accent-gradient p-1.5 rounded-lg shadow-glow-cyan">
            <HeartPulse className="h-4 w-4 text-slate-900" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight">
              Teleconsulta ConnectaIACare
            </div>
            <div className="text-[11px] text-muted-foreground font-mono uppercase tracking-wider">
              {roomName}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {connState === "in_call" && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-classification-routine/10 border border-classification-routine/25">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-classification-routine opacity-75 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-classification-routine" />
              </span>
              <span className="text-[11px] font-medium text-classification-routine uppercase tracking-wider tabular">
                em chamada · {formatTime(elapsed)}
              </span>
            </div>
          )}
          {role === "doctor" && (
            <span className="text-[10px] uppercase tracking-wider bg-accent-cyan/10 text-accent-cyan px-2 py-1 rounded border border-accent-cyan/25">
              Profissional
            </span>
          )}
          {role === "patient" && (
            <span className="text-[10px] uppercase tracking-wider bg-white/[0.05] text-muted-foreground px-2 py-1 rounded">
              Paciente
            </span>
          )}
        </div>
      </header>

      {/* Main area */}
      <main className="relative z-10 flex-1 flex items-center justify-center p-6 overflow-hidden">
        {connState === "error" && <ErrorOverlay message={error || "Erro desconhecido"} />}

        {(connState === "requesting_media" || connState === "connecting") && (
          <ConnectingOverlay state={connState} />
        )}

        {connState === "waiting_other" && (
          <WaitingOverlay role={role} />
        )}

        {/* Vídeos — sempre presentes no DOM pra streams se anexarem */}
        <div
          className={`relative w-full h-full max-w-[1400px] ${connState === "in_call" ? "opacity-100" : "opacity-0 pointer-events-none absolute"}`}
        >
          {/* Vídeo remoto (tela grande) */}
          <div className="w-full h-full rounded-2xl overflow-hidden bg-black border border-white/[0.08] relative">
            <video
              ref={remoteVideoRef}
              autoPlay
              playsInline
              className="w-full h-full object-cover bg-gradient-to-br from-slate-950 to-slate-900"
            />
            <audio ref={remoteAudioRef} autoPlay />

            {/* Nome do remoto */}
            {remoteParticipantName && (
              <div className="absolute bottom-4 left-4 px-3 py-1.5 rounded-lg bg-black/60 backdrop-blur-sm border border-white/[0.08]">
                <div className="text-sm font-medium">{remoteParticipantName}</div>
              </div>
            )}

            {/* Signal indicator */}
            <div className="absolute top-4 right-4 flex items-center gap-1.5 px-2 py-1 rounded-md bg-black/60 backdrop-blur-sm">
              <Signal className="h-3 w-3 text-classification-routine" />
              <span className="text-[10px] uppercase tracking-wider text-classification-routine">HD</span>
            </div>
          </div>

          {/* PiP local */}
          <div className="absolute bottom-6 right-6 w-48 h-32 md:w-60 md:h-40 rounded-xl overflow-hidden bg-black border-2 border-white/10 shadow-2xl">
            <video
              ref={localVideoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover scale-x-[-1]"
            />
            {!camEnabled && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/80">
                <VideoOff className="h-6 w-6 text-muted-foreground" />
              </div>
            )}
            <div className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded bg-black/60 text-[9px] uppercase tracking-wider">
              Você
            </div>
          </div>
        </div>
      </main>

      {/* Controls bar */}
      <footer className="relative z-10 flex items-center justify-center gap-2 p-4 border-t border-white/[0.05] bg-[hsl(225,80%,7%)]/70 backdrop-blur-xl flex-shrink-0">
        <ControlButton
          onClick={toggleMic}
          active={micEnabled}
          icon={micEnabled ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
          label={micEnabled ? "Desativar mic" : "Ativar mic"}
        />
        <ControlButton
          onClick={toggleCam}
          active={camEnabled}
          icon={camEnabled ? <VideoIcon className="h-4 w-4" /> : <VideoOff className="h-4 w-4" />}
          label={camEnabled ? "Desativar câmera" : "Ativar câmera"}
        />
        <div className="w-px h-6 bg-white/[0.08] mx-1" />
        <button
          onClick={endCall}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-classification-critical text-white text-sm font-semibold hover:bg-classification-critical/90 transition-all shadow-glow-cyan"
          title="Encerrar consulta"
        >
          <PhoneOff className="h-4 w-4" />
          Encerrar
        </button>
      </footer>
    </div>
  );
}

function ControlButton({
  onClick,
  active,
  icon,
  label,
}: {
  onClick: () => void;
  active: boolean;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={`
        w-11 h-11 rounded-full flex items-center justify-center transition-all
        ${
          active
            ? "bg-white/[0.06] text-foreground border border-white/[0.08] hover:bg-white/[0.10]"
            : "bg-classification-critical/15 text-classification-critical border border-classification-critical/30 hover:bg-classification-critical/25"
        }
      `}
    >
      {icon}
    </button>
  );
}

function ConnectingOverlay({ state }: { state: ConnectionState }) {
  const label =
    state === "requesting_media"
      ? "Liberando câmera e microfone..."
      : "Conectando à sala...";
  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <Loader2 className="h-10 w-10 animate-spin text-accent-cyan" />
      <div>
        <div className="text-lg font-medium">{label}</div>
        <div className="text-sm text-muted-foreground mt-1">
          {state === "requesting_media" &&
            "Permita o acesso no navegador para continuar."}
          {state === "connecting" && "Estabelecendo conexão segura WebRTC."}
        </div>
      </div>
    </div>
  );
}

function WaitingOverlay({ role }: { role: "doctor" | "patient" }) {
  return (
    <div className="flex flex-col items-center gap-4 text-center max-w-md">
      <div className="relative">
        <div className="absolute inset-0 bg-accent-cyan/20 rounded-full blur-2xl animate-pulse-soft" />
        <div className="relative w-20 h-20 rounded-full bg-accent-cyan/10 border border-accent-cyan/25 flex items-center justify-center">
          <Clock className="h-8 w-8 text-accent-cyan" />
        </div>
      </div>
      <div>
        <div className="text-xl font-semibold">Aguardando outro participante</div>
        <div className="text-sm text-muted-foreground mt-1.5 max-w-sm">
          {role === "doctor"
            ? "O paciente será avisado assim que abrir o link enviado via WhatsApp."
            : "O profissional entrará em breve. Relaxe — estamos conectando."}
        </div>
      </div>
      <div className="flex items-center gap-2 mt-2 text-[11px] text-muted-foreground">
        <span className="w-1.5 h-1.5 rounded-full bg-classification-routine animate-pulse-soft" />
        Sua câmera e microfone já estão ativos
      </div>
    </div>
  );
}

function ErrorOverlay({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-4 text-center max-w-md">
      <div className="w-16 h-16 rounded-full bg-classification-critical/10 border border-classification-critical/30 flex items-center justify-center">
        <AlertTriangle className="h-6 w-6 text-classification-critical" />
      </div>
      <div>
        <div className="text-lg font-semibold">Não foi possível conectar</div>
        <div className="text-sm text-muted-foreground mt-1 leading-relaxed">{message}</div>
      </div>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 rounded-lg bg-white/[0.05] border border-white/[0.08] text-xs font-medium hover:bg-white/[0.08] transition-colors"
      >
        Tentar novamente
      </button>
    </div>
  );
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}
