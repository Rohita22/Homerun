/**
 * Browser side of the voice assistant: streams microphone audio to `WS /api/voice/ws` and plays
 * the assistant's audio back gaplessly. No framework code here, so the component stays thin.
 *
 * Wire format: binary frames up = 16 kHz mono PCM16 mic audio, binary frames down = 24 kHz mono
 * PCM16 assistant audio; JSON text frames carry control events (see backend/app/services/voice_session.py).
 */

import type { BuyerProfile } from "../api/types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const MIC_RATE = 16000;
const PLAY_RATE = 24000;
const CHUNK_SAMPLES = 480; // 30 ms of mic audio per frame

export interface VoiceState {
  max_price_sgd: number | null;
  no_budget_limit: boolean;
  bedrooms: number[];
  property_types: string[];
  towns: string[];
  anywhere: boolean;
  answered: { budget: boolean; bedrooms: boolean; property_type: boolean; town: boolean };
}

export type VoiceEvent =
  | { type: "ready" }
  | { type: "transcript"; role: "user" | "assistant"; text: string }
  | ({ type: "state" } & VoiceState)
  | { type: "interrupted" }
  | { type: "turn_complete" }
  | ({ type: "complete"; profile: Omit<BuyerProfile, "session_id"> } & VoiceState)
  | { type: "error"; message: string };

// Runs on the audio thread: downsample to 16 kHz, convert to PCM16, post fixed-size frames.
const WORKLET_SRC = `
class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / ${MIC_RATE};
    this.pos = 0;
    this.out = new Int16Array(${CHUNK_SAMPLES});
    this.n = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    while (this.pos < ch.length) {
      const i = Math.floor(this.pos);
      const a = ch[i];
      const b = i + 1 < ch.length ? ch[i + 1] : a;
      const v = Math.max(-1, Math.min(1, a + (b - a) * (this.pos - i)));
      this.out[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
      if (this.n === ${CHUNK_SAMPLES}) {
        this.port.postMessage(this.out.buffer);
        this.out = new Int16Array(${CHUNK_SAMPLES});
        this.n = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= ch.length;
    return true;
  }
}
registerProcessor("capture", Capture);
`;

export function voiceSocketUrl(): string {
  return BASE_URL.replace(/^http/, "ws").replace(/\/$/, "") + "/voice/ws";
}

export class VoiceClient {
  private ws: WebSocket | null = null;
  private micCtx: AudioContext | null = null;
  private playCtx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private micAnalyser: AnalyserNode | null = null;
  private outAnalyser: AnalyserNode | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private nextStart = 0;
  private muted = false;
  private closed = false;
  private levelBuf = new Uint8Array(256);

  private onEvent: (e: VoiceEvent) => void;
  private onClose: () => void;

  constructor(onEvent: (e: VoiceEvent) => void, onClose: () => void) {
    this.onEvent = onEvent;
    this.onClose = onClose;
  }

  /** Opens the socket and the microphone in parallel so the greeting starts as early as possible. */
  async start(): Promise<void> {
    this.playCtx = new AudioContext({ sampleRate: PLAY_RATE, latencyHint: "interactive" });
    void this.playCtx.resume();
    this.outAnalyser = this.playCtx.createAnalyser();
    this.outAnalyser.fftSize = 256;
    this.outAnalyser.connect(this.playCtx.destination);

    const socket = new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(voiceSocketUrl());
      ws.binaryType = "arraybuffer";
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("Couldn't connect to the voice service."));
      ws.onmessage = (m) => this.handleMessage(m);
      ws.onclose = () => {
        if (!this.closed) this.onClose();
      };
      this.ws = ws;
    });
    const mic = this.startMic();
    const results = await Promise.allSettled([socket, mic]);
    const failed = results.find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
    if (failed) {
      this.stop();
      throw failed.reason;
    }
  }

  private async startMic(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser doesn't support microphone access.");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      throw new Error("Microphone access was blocked. Please allow it and try again.");
    }
    if (this.closed) return;
    const ctx = new AudioContext({ latencyHint: "interactive" });
    this.micCtx = ctx;
    void ctx.resume();
    const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));
    try {
      await ctx.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    if (this.closed) return;
    const source = ctx.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(ctx, "capture");
    node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      if (!this.muted && this.ws?.readyState === WebSocket.OPEN) this.ws.send(e.data);
    };
    this.micAnalyser = ctx.createAnalyser();
    this.micAnalyser.fftSize = 256;
    source.connect(node);
    source.connect(this.micAnalyser);
  }

  private handleMessage(m: MessageEvent) {
    if (m.data instanceof ArrayBuffer) {
      this.enqueueAudio(m.data);
      return;
    }
    const event = JSON.parse(m.data as string) as VoiceEvent;
    if (event.type === "interrupted") this.flushPlayback();
    this.onEvent(event);
  }

  private enqueueAudio(data: ArrayBuffer) {
    const ctx = this.playCtx;
    if (!ctx || this.closed) return;
    const pcm = new Int16Array(data, 0, Math.floor(data.byteLength / 2));
    const buf = ctx.createBuffer(1, pcm.length, PLAY_RATE);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.outAnalyser!);
    // Small lead on the first chunk absorbs network jitter; later chunks queue back to back.
    const startAt = Math.max(ctx.currentTime + 0.03, this.nextStart);
    src.start(startAt);
    this.nextStart = startAt + buf.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  /** Barge-in: the caller spoke over the assistant, so drop everything still queued. */
  private flushPlayback() {
    this.sources.forEach((s) => {
      s.onended = null;
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    });
    this.sources.clear();
    this.nextStart = 0;
  }

  /** Milliseconds of assistant audio still waiting to be played. */
  playbackRemainingMs(): number {
    return this.playCtx ? Math.max(0, (this.nextStart - this.playCtx.currentTime) * 1000) : 0;
  }

  isAssistantSpeaking(): boolean {
    return this.playbackRemainingMs() > 0;
  }

  /** 0..1 loudness of whoever is currently talking, for the animated orb. */
  getLevel(): number {
    const node = this.isAssistantSpeaking() ? this.outAnalyser : this.micAnalyser;
    if (!node) return 0;
    node.getByteTimeDomainData(this.levelBuf);
    let sum = 0;
    for (let i = 0; i < this.levelBuf.length; i++) {
      const v = (this.levelBuf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this.levelBuf.length) * 4);
  }

  setMuted(muted: boolean) {
    this.muted = muted;
    this.stream?.getAudioTracks().forEach((t) => (t.enabled = !muted));
    if (muted && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "audio_end" }));
  }

  /** Lets the caller type a message instead of speaking (kept for accessibility / noisy rooms). */
  sendText(text: string) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "text", text }));
  }

  stop() {
    if (this.closed) return;
    this.closed = true;
    try {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "end" }));
      this.ws?.close();
    } catch {
      /* socket already gone */
    }
    this.flushPlayback();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.micCtx?.close();
    void this.playCtx?.close();
  }
}
