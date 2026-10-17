import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { FinanceEstimateResponse, PropertyOut } from "../api/types";
import { OrchestrationTrace } from "./OrchestrationTrace";

interface Props {
  listingId: string;
  onInterested: (listingId: string) => void;
  onBack: () => void;
}

export function PropertyDetail({ listingId, onInterested, onBack }: Props) {
  const [property, setProperty] = useState<PropertyOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [downPaymentPct, setDownPaymentPct] = useState(20);
  const [ratePct, setRatePct] = useState(3.0);
  const [years, setYears] = useState(25);
  const [finance, setFinance] = useState<FinanceEstimateResponse | null>(null);
  const [financeLoading, setFinanceLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getProperty(listingId)
      .then((p) => !cancelled && setProperty(p))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.message : "Failed to load listing."));
    return () => {
      cancelled = true;
    };
  }, [listingId]);

  async function computeFinance() {
    if (!property?.asking_price_sgd) return;
    setFinanceLoading(true);
    try {
      const downPayment = (property.asking_price_sgd * downPaymentPct) / 100;
      const est = await api.estimateFinance(property.asking_price_sgd, downPayment, ratePct, years);
      setFinance(est);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not estimate financing.");
    } finally {
      setFinanceLoading(false);
    }
  }

  if (error) {
    return (
      <section className="card">
        <p className="error">{error}</p>
        <button className="ghost" onClick={onBack}>
          Back
        </button>
      </section>
    );
  }

  if (!property) {
    return (
      <section className="card">
        <p>Loading…</p>
      </section>
    );
  }

  return (
    <section className="card">
      <button className="ghost" onClick={onBack}>
        ← Back
      </button>
      <h2>{property.address_public ?? property.listing_id}</h2>
      <p className="price">
        {property.asking_price_sgd ? `S$${property.asking_price_sgd.toLocaleString()}` : "price unknown"}
      </p>
      <p className="muted">
        {property.property_type} · {property.bedrooms ?? "?"} bed · {property.bathrooms ?? "?"} bath ·{" "}
        {property.floor_area_sqm ?? "?"} sqm · {property.town}
      </p>
      <p className="muted small">
        status: {property.status} · fetched: {new Date(property.fetched_at).toLocaleString()} ·{" "}
        {property.attribution}
      </p>
      {!property.valuation_eligible && (
        <p className="hint">
          No HDB valuation model applies to this property type — estimate intentionally omitted.
        </p>
      )}
      {!property.has_coordinates && <p className="hint">No verified coordinates for this listing.</p>}
      {property.source_url && (
        <p>
          <a href={property.source_url} target="_blank" rel="noreferrer">
            View original listing source
          </a>
        </p>
      )}

      {property.valuation_eligible && (
        <div className="card inline-card">
          <h3>Affordability estimate</h3>
          <div className="form-grid">
            <label>
              Down payment %
              <input
                type="number"
                value={downPaymentPct}
                onChange={(e) => setDownPaymentPct(Number(e.target.value))}
              />
            </label>
            <label>
              Annual rate %
              <input type="number" step="0.1" value={ratePct} onChange={(e) => setRatePct(Number(e.target.value))} />
            </label>
            <label>
              Tenure (years)
              <input type="number" value={years} onChange={(e) => setYears(Number(e.target.value))} />
            </label>
          </div>
          <button onClick={computeFinance} disabled={financeLoading}>
            {financeLoading ? "Calculating…" : "Estimate monthly payment"}
          </button>

          {finance && (
            <div>
              <p className="price">S${finance.monthly_payment_sgd.toLocaleString()} / month</p>
              <p className="muted small">
                loan principal: S${finance.loan_principal_sgd.toLocaleString()} · down payment: S$
                {finance.down_payment_sgd.toLocaleString()}
              </p>
              <ul className="reasons">
                {finance.scenarios.map((s) => (
                  <li key={s.label}>
                    {s.label}: S${s.monthly_payment_sgd.toLocaleString()} (+S${s.delta_vs_base_sgd.toLocaleString()})
                  </li>
                ))}
              </ul>
              <ul className="warnings">
                {finance.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {finance && <OrchestrationTrace trace={finance.trace} />}

      <div className="row">
        <button onClick={() => onInterested(property.listing_id)}>I'm interested — contact agent</button>
      </div>
    </section>
  );
}
