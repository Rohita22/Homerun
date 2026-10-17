import type { RecommendationItem, RecommendationResponse } from "../api/types";

interface Props {
  result: RecommendationResponse;
  selectedIds: string[];
  onToggleSelect: (listingId: string) => void;
  onViewDetail: (listingId: string) => void;
  onPreferPairwise: (chosenId: string, rejectedId: string) => void;
  onLike: (listingId: string) => void;
  onCompare: () => void;
}

function formatMoney(value: number | null): string {
  if (value == null) return "unknown";
  return `S$${value.toLocaleString()}`;
}

function ValuationBadge({ item }: { item: RecommendationItem }) {
  if (!item.valuation_status) return null;
  if (item.valuation_status === "supported_hdb" && item.valuation) {
    return (
      <span className="badge badge-ok" title={item.valuation.coverage_note ?? ""}>
        Est. {formatMoney(item.valuation.point_estimate_sgd)} (
        {formatMoney(item.valuation.interval_low_sgd)}–{formatMoney(item.valuation.interval_high_sgd)})
      </span>
    );
  }
  return (
    <span className="badge badge-muted" title={item.valuation?.reason ?? ""}>
      Valuation {item.valuation_status.replaceAll("_", " ")}
    </span>
  );
}

export function ResultsList({
  result,
  selectedIds,
  onToggleSelect,
  onViewDetail,
  onPreferPairwise,
  onLike,
  onCompare,
}: Props) {
  return (
    <section className="card">
      <h2>
        Top {result.returned_count} of {result.requested_count} requested
      </h2>
      <p className="muted small">
        source: {result.source_mode} · run: <code>{result.run_id}</code> · excluded:{" "}
        {result.excluded_count} · needs confirmation: {result.needs_confirmation_count}
      </p>
      {result.warnings.length > 0 && (
        <ul className="warnings">
          {result.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {result.items.length === 0 && (
        <p className="hint">
          No matched inventory for your current hard constraints. Try relaxing one (budget,
          bedrooms, or town) in the preferences step.
        </p>
      )}

      <div className="results-grid">
        {result.items.map((item) => (
          <article key={item.listing_id} className="result-card">
            <header>
              <span className="rank">#{item.rank}</span>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(item.listing_id)}
                  disabled={!selectedIds.includes(item.listing_id) && selectedIds.length >= 3}
                  onChange={() => onToggleSelect(item.listing_id)}
                />
                compare
              </label>
            </header>
            <h3>{item.address_public ?? item.listing_id}</h3>
            <p className="price">{formatMoney(item.asking_price_sgd)}</p>
            <p className="muted small">{item.town}</p>
            <ValuationBadge item={item} />
            <ul className="reasons">
              {item.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            <p className="muted small">score: {item.score.toFixed(3)}</p>
            <div className="row">
              <button className="ghost" onClick={() => onViewDetail(item.listing_id)}>
                View detail
              </button>
              <button className="ghost" onClick={() => onLike(item.listing_id)}>
                👍 Like
              </button>
            </div>
          </article>
        ))}
      </div>

      {selectedIds.length === 2 && (
        <div className="card inline-card">
          <p>Which do you prefer?</p>
          <div className="row">
            <button onClick={() => onPreferPairwise(selectedIds[0], selectedIds[1])}>
              {selectedIds[0]}
            </button>
            <button onClick={() => onPreferPairwise(selectedIds[1], selectedIds[0])}>
              {selectedIds[1]}
            </button>
          </div>
          <p className="muted small">
            This updates your soft preference weights and reranks — hard constraints stay intact.
          </p>
        </div>
      )}

      {selectedIds.length >= 2 && (
        <div className="row">
          <button onClick={onCompare}>Compare {selectedIds.length} selected</button>
        </div>
      )}
    </section>
  );
}
