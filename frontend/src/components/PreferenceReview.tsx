import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { BuyerProfile, PropertyType } from "../api/types";

interface Props {
  sessionId: string;
  profile: BuyerProfile;
  onSaved: (profile: BuyerProfile) => void;
}

const PROPERTY_TYPES: PropertyType[] = ["HDB", "CONDO", "EC", "LANDED"];
const HARD_FIELDS = ["max_price_sgd", "min_bedrooms", "property_type", "preferred_towns", "min_floor_area_sqm"];

export function PreferenceReview({ sessionId, profile, onSaved }: Props) {
  const [form, setForm] = useState<BuyerProfile>(profile);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleHard(field: string) {
    setForm((f) => ({
      ...f,
      hard_constraints: f.hard_constraints.includes(field)
        ? f.hard_constraints.filter((h) => h !== field)
        : [...f.hard_constraints, field],
    }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = await api.putPreferences(sessionId, {
        transaction_type: form.transaction_type,
        property_type: form.property_type,
        property_types: form.property_types ?? [],
        max_price_sgd: form.max_price_sgd,
        min_price_sgd: form.min_price_sgd,
        min_bedrooms: form.min_bedrooms,
        min_bathrooms: form.min_bathrooms,
        min_floor_area_sqm: form.min_floor_area_sqm,
        preferred_towns: form.preferred_towns,
        hard_constraints: form.hard_constraints,
        soft_weights: form.soft_weights,
        notes: form.notes,
      });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save preferences.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card">
      <h2>Review your preferences</h2>
      <p className="muted">
        Deal breakers (checked below) are enforced exactly — a listing that doesn't meet one is
        excluded, never silently relaxed.
      </p>

      <div className="form-grid">
        <label>
          Transaction
          <select
            value={form.transaction_type}
            onChange={(e) => setForm((f) => ({ ...f, transaction_type: e.target.value as "buy" | "rent" }))}
          >
            <option value="buy">Buy</option>
            <option value="rent">Rent</option>
          </select>
        </label>

        <label>
          Property type
          <select
            value={form.property_type ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, property_type: (e.target.value || null) as PropertyType | null }))
            }
          >
            <option value="">Any</option>
            {PROPERTY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label>
          Max price (SGD)
          <input
            type="number"
            value={form.max_price_sgd ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, max_price_sgd: e.target.value ? Number(e.target.value) : null }))
            }
          />
        </label>

        <label>
          Min bedrooms
          <input
            type="number"
            value={form.min_bedrooms ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, min_bedrooms: e.target.value ? Number(e.target.value) : null }))
            }
          />
        </label>

        <label className="span-2">
          Preferred towns (comma separated)
          <input
            type="text"
            value={form.preferred_towns.join(", ")}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                preferred_towns: e.target.value
                  .split(",")
                  .map((t) => t.trim())
                  .filter(Boolean),
              }))
            }
          />
        </label>
      </div>

      <fieldset>
        <legend>Hard constraints (deal breakers)</legend>
        {HARD_FIELDS.map((field) => (
          <label key={field} className="checkbox">
            <input
              type="checkbox"
              checked={form.hard_constraints.includes(field)}
              onChange={() => toggleHard(field)}
            />
            {field}
          </label>
        ))}
      </fieldset>

      {error && <p className="error">{error}</p>}
      <div className="row">
        <button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save & search"}
        </button>
      </div>
    </section>
  );
}
