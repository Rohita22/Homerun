import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { AgentTrace, BuyerProfile } from "../api/types";
import { OrchestrationTrace } from "./OrchestrationTrace";

interface Props {
  sessionId: string | null;
  onExtracted: (sessionId: string, profile: BuyerProfile) => void;
}

const EXAMPLE = "Find me a 4-room HDB in Tampines under S$800k, near the MRT. I value commute more than space.";

export function ChatScreen({ sessionId, onExtracted }: Props) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWarnings, setLastWarnings] = useState<string[]>([]);
  const [followup, setFollowup] = useState<string | null>(null);
  const [trace, setTrace] = useState<AgentTrace[]>([]);

  async function send() {
    if (!message.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.chat(sessionId, message);
      setLastWarnings(res.warnings);
      setFollowup(res.followup_question);
      setTrace(res.trace);
      onExtracted(res.session_id, res.buyer_profile);
      setMessage("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h2>Describe your ideal home</h2>
      <p className="muted">
        Your message may be processed by an external LLM provider (or a local deterministic
        fallback) to extract structured search preferences.
      </p>
      <textarea
        rows={4}
        value={message}
        placeholder={EXAMPLE}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
        }}
      />
      <div className="row">
        <button onClick={send} disabled={loading || !message.trim()}>
          {loading ? "Thinking…" : "Send"}
        </button>
        <button className="ghost" onClick={() => setMessage(EXAMPLE)} disabled={loading}>
          Use example
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {followup && <p className="hint">Homerun asks: {followup}</p>}
      {lastWarnings.length > 0 && (
        <ul className="warnings">
          {lastWarnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {sessionId && (
        <p className="muted small">
          Session: <code>{sessionId}</code> — keep chatting or continue to review your
          preferences below.
        </p>
      )}
      <OrchestrationTrace trace={trace} />
    </section>
  );
}
