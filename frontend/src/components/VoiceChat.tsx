import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BuyerProfile } from "../api/types";
import { VoiceClient, type VoiceEvent, type VoiceState } from "../lib/voiceClient";

interface Props {
  onComplete: (sessionId: string, profile: BuyerProfile) => void;
  onBack: () => void;
  onTypeInstead: () => void;
}

type Status = "connecting" | "live" | "finishing" | "error";
interface Line {
  role: "user" | "assistant";
  text: string;
}

const EMPTY: VoiceState = {
  max_price_sgd: null,
  no_budget_limit: false,
  bedrooms: [],
  property_types: [],
  towns: [],
  anywhere: false,
  answered: { budget: false, bedrooms: false, property_type: false, town: false },
};

const TYPE_LABELS: Record<string, string> = { HDB: "HDB", CONDO: "Condo", EC: "Executive Condo", LANDED: "Landed" };
const titleCase = (s: string) => s.toLowerCase().replace(/(^|[ /])([a-z])/g, (_, p, c) => p + c.toUpperCase());

function money(n: number): string {
  return n >= 1_000_000 ? `S$${+(n / 1_000_000).toFixed(2)}M` : `S$${Math.round(n / 1000)}k`;
}

function summary(s: VoiceState) {
  return [
    {
      label: "Budget",
      done: s.answered.budget,
      value: s.no_budget_limit ? "No limit" : s.max_price_sgd ? `Up to ${money(s.max_price_sgd)}` : "",
    },
    {
      label: "Bedrooms",
      done: s.answered.bedrooms,
      value: s.bedrooms.map((b) => (b >= 5 ? "5+" : String(b))).join(" or "),
    },
    { label: "Property type", done: s.answered.property_type, value: s.property_types.map((t) => TYPE_LABELS[t] ?? t).join(", ") },
    { label: "Town", done: s.answered.town, value: s.anywhere ? "Anywhere" : s.towns.map(titleCase).join(", ") },
  ];
}

export function VoiceChat({ onComplete, onBack, onTypeInstead }: Props) {
  const [status, setStatus] = useState<Status>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [prefs, setPrefs] = useState<VoiceState>(EMPTY);
  const [lines, setLines] = useState<Line[]>([]);
  const [muted, setMuted] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const clientRef = useRef<VoiceClient | null>(null);
  const orbRef = useRef<HTMLDivElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const finish = useCallback(async (client: VoiceClient, profile: Omit<BuyerProfile, "session_id">) => {
    setStatus("finishing");
    // Let the assistant finish its recap before we leave the screen.
    while (client.playbackRemainingMs() > 0) await new Promise((r) => setTimeout(r, 100));
    await new Promise((r) => setTimeout(r, 250));
    client.stop();
    const sessionId = crypto.randomUUID().replace(/-/g, "");
    try {
      const saved = await api.putPreferences(sessionId, profile);
      onCompleteRef.current(sessionId, saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your answers.");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const handle = (e: VoiceEvent) => {
      if (cancelled) return;
      if (e.type === "ready") setStatus("live");
      else if (e.type === "state") setPrefs(e);
      else if (e.type === "transcript") {
        setLines((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === e.role) return [...prev.slice(0, -1), { role: e.role, text: last.text + e.text }];
          return [...prev, { role: e.role, text: e.text }].slice(-8);
        });
      } else if (e.type === "complete") {
        setPrefs(e);
        void finish(client, e.profile);
      } else if (e.type === "error") {
        setError(e.message);
        setStatus("error");
        client.stop();
      }
    };
    const client = new VoiceClient(handle, () => {
      if (cancelled) return;
      setStatus((s) => {
        if (s === "finishing" || s === "error") return s;
        setError("The voice connection was closed.");
        return "error";
      });
    });
    clientRef.current = client;
    client.start().catch((err: Error) => {
      if (cancelled) return;
      setError(err.message);
      setStatus("error");
    });

    let raf = 0;
    const tick = () => {
      const level = client.getLevel();
      orbRef.current?.style.setProperty("--level", level.toFixed(3));
      const isSpeaking = client.isAssistantSpeaking();
      setSpeaking((prev) => (prev === isSpeaking ? prev : isSpeaking));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      client.stop();
    };
  }, [attempt, finish]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  function retry() {
    setStatus("connecting");
    setError(null);
    setPrefs(EMPTY);
    setLines([]);
    setMuted(false);
    setAttempt((a) => a + 1);
  }

  function toggleMute() {
    setMuted((m) => {
      clientRef.current?.setMuted(!m);
      return !m;
    });
  }

  const live = status === "live";
  const orbState = status === "connecting" ? "connecting" : status === "finishing" ? "speaking" : speaking ? "speaking" : muted ? "muted" : "listening";
  const caption =
    status === "connecting" ? "Connecting to Ava…"
    : status === "finishing" ? "Finding your matches…"
    : speaking ? "Ava is talking…"
    : muted ? "Mic is muted"
    : "Listening — go ahead!";

  return (
    <section className="card voice-card">
      <button className="ghost back-btn" onClick={onBack} disabled={status === "finishing"}>
        ← Back
      </button>
      <h2>Tell Ava about your dream home</h2>
      <p className="muted small">Just talk naturally. Ava will ask about anything she needs.</p>

      <div className="voice-stage">
        <div ref={orbRef} className={`voice-orb ${orbState}`} aria-hidden="true">
          <span className="voice-orb-core">🎙️</span>
        </div>
        <p className="voice-caption" role="status" aria-live="polite">{status === "error" ? "Something went wrong" : caption}</p>
      </div>

      {status !== "error" && (
        <>
          <ul className="voice-chips" aria-label="What Ava has picked up">
            {summary(prefs).map((c) => (
              <li key={c.label} className={c.done ? "voice-chip done" : "voice-chip"}>
                <span className="voice-chip-label">{c.done ? "✓" : "○"} {c.label}</span>
                <span className="voice-chip-value">{c.done ? c.value : "—"}</span>
              </li>
            ))}
          </ul>

          <div className="voice-log" ref={logRef} aria-label="Live transcript">
            {lines.map((l, i) => (
              <p key={i} className={`voice-line ${l.role}`}>
                <strong>{l.role === "user" ? "You" : "Ava"}:</strong> {l.text}
              </p>
            ))}
          </div>
        </>
      )}

      {error && <p className="error">{error}</p>}

      <div className="row">
        {status === "error" ? (
          <button onClick={retry}>Try again</button>
        ) : (
          <button className="ghost" onClick={toggleMute} disabled={!live}>
            {muted ? "🔇 Unmute" : "🎤 Mute"}
          </button>
        )}
        <button className="ghost" onClick={onTypeInstead} disabled={status === "finishing"}>
          ⌨️ Type instead
        </button>
      </div>
    </section>
  );
}
