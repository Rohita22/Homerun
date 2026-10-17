import { useEffect, useState } from "react";
import { api, getLastTrace } from "../api/client";
import type { HealthResponse } from "../api/types";

/**
 * "System evidence panel" (PRD section 12): proves the API is real — architecture, provider
 * health, and the request_id/latency of the most recent call — rather than asking the judge to
 * take it on faith.
 */
export function EvidencePanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [trace, setTrace] = useState(getLastTrace());

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    const interval = setInterval(() => setTrace(getLastTrace()), 800);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="evidence-panel">
      <h4>System evidence</h4>
      {health ? (
        <ul>
          <li>arch: {health.architecture}</li>
          <li>
            listing provider: {health.listing_provider} ({health.listing_provider_healthy ? "healthy" : "down"})
            {health.listing_provider === "authorized" && (
              <>
                {" "}
                <span className="badge badge-ok" style={{ fontSize: "0.7rem" }}>
                  LIVE DATA
                </span>
              </>
            )}
          </li>
          <li>catalog size: {health.listing_catalog_size}</li>
          <li>llm provider: {health.llm_provider}</li>
          <li>
            valuation model: {health.valuation_model_version} (
            {health.valuation_model_is_trained ? "trained" : "baseline fallback"})
          </li>
          <li>database: {health.database}</li>
          <li>build: {health.build_sha}</li>
        </ul>
      ) : (
        <p className="muted small">backend unreachable</p>
      )}
      {trace.requestId && (
        <p className="muted small">
          last: {trace.path} · {trace.elapsedMs?.toFixed(1)}ms
          <br />
          <code>{trace.requestId}</code>
        </p>
      )}
    </aside>
  );
}
