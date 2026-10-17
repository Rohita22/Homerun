import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { HandoffChannel, HandoffPreviewResponse, HandoffResponse } from "../api/types";

interface Props {
  listingId: string;
  onBack: () => void;
}

export function HandoffPanel({ listingId, onBack }: Props) {
  const [preview, setPreview] = useState<HandoffPreviewResponse | null>(null);
  const [channel, setChannel] = useState<HandoffChannel>("original_listing");
  const [consent, setConsent] = useState(false); // explicit UNTICKED opt-in, per PRD section 8
  const [fields, setFields] = useState<string[]>([]);
  const [result, setResult] = useState<HandoffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .previewHandoff(listingId)
      .then((p) => {
        setPreview(p);
        setChannel(p.safe_contact_choices[0]?.channel ?? "original_listing");
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not preview handoff."));
  }, [listingId]);

  function toggleField(field: string) {
    setFields((f) => (f.includes(field) ? f.filter((x) => x !== field) : [...f, field]));
  }

  async function confirm() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.executeHandoff(listingId, channel, consent, fields);
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Handoff failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const needsConsent = preview?.safe_contact_choices.find((c) => c.channel === channel)?.requires_consent;

  return (
    <section className="card">
      <button className="ghost" onClick={onBack}>
        ← Back to results
      </button>
      <h2>Contact the agent for this listing</h2>

      {error && <p className="error">{error}</p>}

      {preview && !result && (
        <>
          <p className="muted small">
            association status: <strong>{preview.association_status}</strong> · handoff state:{" "}
            <strong>{preview.handoff_state}</strong>
          </p>

          <fieldset>
            <legend>Contact route</legend>
            {preview.safe_contact_choices.map((c) => (
              <label key={c.channel} className="checkbox">
                <input
                  type="radio"
                  name="channel"
                  checked={channel === c.channel}
                  onChange={() => setChannel(c.channel)}
                />
                {c.channel === "original_listing" ? "Original listing contact link" : "Authorized direct lead (share my contact details)"}
              </label>
            ))}
          </fieldset>

          {channel === "authorized_direct_lead" && (
            <fieldset>
              <legend>Fields to share with the agent</legend>
              {preview.shared_field_preview.map((f) => (
                <label key={f} className="checkbox">
                  <input type="checkbox" checked={fields.includes(f)} onChange={() => toggleField(f)} />
                  {f}
                </label>
              ))}
            </fieldset>
          )}

          {needsConsent && (
            <label className="checkbox consent">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              I consent to sharing the selected fields with this listing's agent for the purpose of
              being contacted about this property.
            </label>
          )}

          <div className="row">
            <button onClick={confirm} disabled={submitting}>
              {submitting ? "Sending…" : "Confirm"}
            </button>
          </div>
        </>
      )}

      {result && (
        <div className={`card inline-card ${result.status === "success" ? "ok" : "fail"}`}>
          <p>
            <strong>{result.status === "success" ? "Success" : "Failed"}</strong> — {result.destination_type}
          </p>
          {typeof result.contact_route.source_url === "string" && (
            <p>
              <a href={result.contact_route.source_url} target="_blank" rel="noreferrer">
                Open original listing
              </a>
            </p>
          )}
          {typeof result.contact_route.agent_name === "string" && (
            <p>Agent: {result.contact_route.agent_name}</p>
          )}
          {typeof result.contact_route.reason === "string" && <p className="muted">{result.contact_route.reason}</p>}
          <p className="muted small">handoff id: {result.handoff_id}</p>
        </div>
      )}
    </section>
  );
}
