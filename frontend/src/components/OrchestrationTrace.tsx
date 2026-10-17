import type { AgentTrace } from "../api/types";

const AGENT_LABELS: Record<string, string> = {
  buyer_intelligence: "1. Buyer Intelligence",
  market_intelligence: "2. Market Intelligence",
  valuation: "3. Valuation",
  affordability: "4. Affordability & Risk",
  matching_decision: "5. Matching & Decision",
};

function statusClass(status: string): string {
  if (status === "ok") return "trace-status-ok";
  if (status === "degraded") return "trace-status-degraded";
  return "trace-status-error";
}

/**
 * Renders the actual multi-agent pipeline trace returned by the backend for a single request —
 * which agents ran, in what order, how long each took, what model version it used, and any
 * warnings — so the orchestration is visible instead of a black-box spinner.
 */
export function OrchestrationTrace({ trace }: { trace: AgentTrace[] }) {
  if (!trace.length) return null;

  const totalMs = trace.reduce((sum, t) => sum + t.elapsed_ms, 0);

  return (
    <section className="card orchestration-trace">
      <h4>Agent orchestration (this request)</h4>
      <ol className="trace-list">
        {trace.map((step, i) => (
          <li key={`${step.agent_name}-${i}`} className="trace-step">
            <div className="trace-step-header">
              <span className={`trace-dot ${statusClass(step.status)}`} />
              <span className="trace-name">{AGENT_LABELS[step.agent_name] ?? step.agent_name}</span>
              <span className="trace-ms">{step.elapsed_ms.toFixed(1)}ms</span>
            </div>
            <div className="trace-meta">
              {step.model_version && <code>{step.model_version}</code>}
              {step.evidence_refs.map((ref, j) => (
                <span key={j} className="muted small">
                  {ref}
                </span>
              ))}
            </div>
            {step.warnings.length > 0 && (
              <ul className="trace-warnings">
                {step.warnings.map((w, j) => (
                  <li key={j}>{w}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      <p className="muted small trace-total">Total agent time: {totalMs.toFixed(1)}ms</p>
    </section>
  );
}
