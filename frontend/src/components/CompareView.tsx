import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CompareResponse } from "../api/types";

interface Props {
  listingIds: string[];
  onBack: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  asking_price_sgd: "Price (SGD)",
  floor_area_sqm: "Floor area (sqm)",
  bedrooms: "Bedrooms",
  bathrooms: "Bathrooms",
  town: "Town",
  lease_remaining_years: "Lease remaining (yrs)",
  tenure: "Tenure",
  floor_level: "Floor level",
  mrt_walk_minutes: "MRT walk (min)",
};

export function CompareView({ listingIds, onBack }: Props) {
  const [data, setData] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .compare(listingIds)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not compare listings."));
  }, [listingIds]);

  return (
    <section className="card">
      <button className="ghost" onClick={onBack}>
        ← Back to results
      </button>
      <h2>Compare</h2>
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <table className="compare-table">
            <thead>
              <tr>
                <th>Field</th>
                {data.listings.map((l) => (
                  <th key={l.listing_id}>{l.address_public ?? l.listing_id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.differences).map(([field, values]) => (
                <tr key={field}>
                  <td>{FIELD_LABELS[field] ?? field}</td>
                  {values.map((v, idx) => (
                    <td key={idx}>{v === null || v === undefined ? "unknown" : String(v)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.caveats.length > 0 && (
            <ul className="warnings">
              {data.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
