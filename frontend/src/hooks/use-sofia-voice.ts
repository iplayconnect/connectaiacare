"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";

/**
 * Sofia Voice Live — sessão WebSocket bidirecional com Gemini Live API.
 *
 * Pipeline:
 *   1. Browser pega token JWT short-TTL do api (/api/sofia/voice/token)
 *   2. Conecta WebSocket em sofia-voice.connectaia.com.br/voice/ws?token=...
 *   3. getUserMedia → AudioWorklet captura PCM Int16 16kHz → WS frames
 *   4. Server (sofia-voice) faz proxy pro Gemini Live e devolve áudio
 *      PCM 24kHz que tocamos via Web Audio API encadeada
 *
 * Encerramento limpo: mic stop, audio context close, WS close. Sem
 * vazamento de stream em interrupt/error.
 *
 * Tom: usa AudioContext 16kHz no input e 24kHz no output (sample rates
 * exigidos pela Live API). echoCancellation+noiseSuppression ligados
 * pra evitar que o microfone capte a fala da Sofia.
 */

type Status =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "ready"
  | "listening"
  | "speaking"
  | "thinking"
  | "interrupted"
  | "error";

type Transcript = {
  role: "user" | "assistant";
  text: string;
  at: string;
};

type ServerMessage =
  | { type: "ready"; sessionId: string; model: string }
  | { type: "audio"; data: string }
  | { type: "transcript"; role: "user" | "assistant"; text: string }
  | { type: "tool_call"; name: string; ok: boolean }
  | { type: "turn_complete" }
  | { type: "interrupted" }
  | { type: "error"; detail: string };

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;

/**
 * AudioWorklet processor — converte Float32 → Int16 PCM e posta pra main
 * thread em chunks de ~100ms. Inline via Blob URL pra evitar arquivo
 * separado em /public.
 */
const PCM_WORKLET_CODE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.targetSamples = 1600; // 100ms a 16kHz
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];
    for (let i = 0; i < channel.length; i++) this.buffer.push(channel[i]);
    while (this.buffer.length >= this.targetSamples) {
      const chunk = this.buffer.splice(0, this.targetSamples);
      const int16 = new Int16Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        const s = Math.max(-1, Math.min(1, chunk[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

function int16BufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToInt16Array(b64: string): Int16Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

export function useSofiaVoice() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [toolEvents, setToolEvents] = useState<{ name: string; ok: boolean }[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const inputCtxRef = useRef<AudioContext | null>(null);
  const outputCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playbackHeadRef = useRef<number>(0);

  // Cleanup completo
  const cleanup = useCallback(() => {
    if (workletNodeRef.current) {
      try { workletNodeRef.current.disconnect(); } catch {}
      workletNodeRef.current = null;
    }
    if (inputCtxRef.current) {
      try { inputCtxRef.current.close(); } catch {}
      inputCtxRef.current = null;
    }
    if (outputCtxRef.current) {
      try { outputCtxRef.current.close(); } catch {}
      outputCtxRef.current = null;
      playbackHeadRef.current = 0;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "close" }));
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  // Toca um chunk PCM 24kHz vindo do servidor encadeando AudioBuffers
  const playPcmChunk = useCallback((int16: Int16Array) => {
    const ctx = outputCtxRef.current;
    if (!ctx) return;
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;
    const buffer = ctx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(playbackHeadRef.current, ctx.currentTime);
    source.start(startAt);
    playbackHeadRef.current = startAt + buffer.duration;
    setStatus((s) => (s === "thinking" || s === "listening" ? "speaking" : s));
  }, []);

  // Habilita pipe mic → WS apenas após ready do server (Live session pronta)
  const startMicPipe = useCallback(() => {
    const ws = wsRef.current;
    const wn = workletNodeRef.current;
    if (!ws || !wn) return;
    wn.port.onmessage = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: "audio",
        data: int16BufferToBase64(e.data as ArrayBuffer),
      }));
    };
  }, []);

  const handleServerMessage = useCallback(
    (msg: ServerMessage) => {
      switch (msg.type) {
        case "ready":
          setStatus("listening");
          startMicPipe();
          break;
        case "audio":
          playPcmChunk(base64ToInt16Array(msg.data));
          break;
        case "transcript":
          setTranscripts((arr) => [
            ...arr,
            { role: msg.role, text: msg.text, at: new Date().toISOString() },
          ]);
          if (msg.role === "user") setStatus("thinking");
          break;
        case "tool_call":
          setToolEvents((arr) => [...arr, { name: msg.name, ok: msg.ok }]);
          break;
        case "turn_complete":
          setStatus("listening");
          break;
        case "interrupted":
          setStatus("interrupted");
          // Limpa fila de playback pendente
          if (outputCtxRef.current) {
            playbackHeadRef.current = outputCtxRef.current.currentTime;
          }
          setTimeout(() => setStatus("listening"), 200);
          break;
        case "error":
          setError(msg.detail);
          setStatus("error");
          break;
      }
    },
    [playPcmChunk],
  );

  const start = useCallback(async () => {
    if (status !== "idle" && status !== "error" && status !== "interrupted") return;
    setError(null);
    setTranscripts([]);
    setToolEvents([]);
    setStatus("requesting_permission");

    try {
      // 1. Token do api
      const tokenRes = await api.sofiaVoiceToken();
      if (tokenRes.status !== "ok" || !tokenRes.wsUrl) {
        throw new Error("token_failed");
      }

      // 2. Pede mic
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      micStreamRef.current = stream;

      // 3. Audio contexts
      const inputCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: INPUT_SAMPLE_RATE,
      });
      inputCtxRef.current = inputCtx;
      const outputCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: OUTPUT_SAMPLE_RATE,
      });
      outputCtxRef.current = outputCtx;
      playbackHeadRef.current = outputCtx.currentTime;

      // 4. Worklet inline
      const blobUrl = URL.createObjectURL(
        new Blob([PCM_WORKLET_CODE], { type: "application/javascript" }),
      );
      await inputCtx.audioWorklet.addModule(blobUrl);
      URL.revokeObjectURL(blobUrl);

      const sourceNode = inputCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(inputCtx, "pcm-capture");
      workletNodeRef.current = workletNode;
      sourceNode.connect(workletNode);
      // Nota: workletNode.connect(inputCtx.destination) causaria feedback;
      // mantemos o node ativo só pelo evento da port.

      // 5. WebSocket
      setStatus("connecting");
      const ws = new WebSocket(tokenRes.wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.addEventListener("open", () => {
        // Apenas sinaliza início. O pipe mic→WS só é habilitado quando
        // o server responde "ready" (Live session pronta). Sem isso,
        // os primeiros audio chunks chegariam antes do server processar
        // start → "not_started".
        ws.send(JSON.stringify({ type: "start" }));
      });

      ws.addEventListener("message", (e) => {
        try {
          const msg = JSON.parse(e.data) as ServerMessage;
          handleServerMessage(msg);
        } catch {
          // ignora frames não-JSON
        }
      });

      ws.addEventListener("error", () => {
        setError("Erro de conexão com o serviço de voz.");
        setStatus("error");
      });

      ws.addEventListener("close", (ev) => {
        if (ev.code === 1008) {
          setError("Token de voz inválido ou expirado.");
          setStatus("error");
        } else if (status !== "error") {
          setStatus("idle");
        }
      });
    } catch (err) {
      const reason = err instanceof ApiError ? err.reason : null;
      if (reason === "outside_hours") {
        setError("Sofia voz fora do horário de atendimento.");
      } else if (err instanceof DOMException && err.name === "NotAllowedError") {
        setError("Permissão de microfone negada.");
      } else {
        setError(err instanceof Error ? err.message : "Falha desconhecida.");
      }
      setStatus("error");
      cleanup();
    }
  }, [status, cleanup, handleServerMessage]);

  const stop = useCallback(() => {
    cleanup();
    setStatus("idle");
  }, [cleanup]);

  const interrupt = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "interrupt" }));
    }
    if (outputCtxRef.current) {
      playbackHeadRef.current = outputCtxRef.current.currentTime;
    }
    setStatus("listening");
  }, []);

  return {
    status,
    error,
    transcripts,
    toolEvents,
    start,
    stop,
    interrupt,
    isActive: status !== "idle" && status !== "error",
  };
}
