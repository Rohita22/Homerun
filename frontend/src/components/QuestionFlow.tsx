import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { BuyerProfile, PropertyType } from "../api/types";

interface Props {
  onComplete: (sessionId: string, profile: BuyerProfile) => void;
  onBack: () => void;
}

interface Option {
  label: string;
  value: string;
}

interface Question {
  key: "budget" | "bedrooms" | "propertyType" | "town";
  title: string;
  multi: boolean;
  options: Option[];
}

const TOWNS = [
  "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH", "BUKIT PANJANG", "BUKIT TIMAH",
  "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI", "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
  "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL", "QUEENSTOWN", "SEMBAWANG",
  "SENGKANG", "SERANGOON", "TAMPINES", "TOA PAYOH", "WOODLANDS", "YISHUN",
];

const titleCase = (s: string) => s.toLowerCase().replace(/(^|[ /])([a-z])/g, (_, p, c) => p + c.toUpperCase());

const QUESTIONS: Question[] = [
  {
    key: "budget",
    multi: false,
    title: "What's your maximum budget?",
    options: [
      { label: "Up to S$500k", value: "500000" },
      { label: "Up to S$700k", value: "700000" },
      { label: "Up to S$900k", value: "900000" },
      { label: "Up to S$1.2M", value: "1200000" },
      { label: "Up to S$2M", value: "2000000" },
      { label: "No limit", value: "" },
    ],
  },
  {
    key: "bedrooms",
    multi: true,
    title: "How many bedrooms do you need?",
    options: [
      { label: "1", value: "1" },
      { label: "2", value: "2" },
      { label: "3", value: "3" },
      { label: "4", value: "4" },
      { label: "5 or more", value: "5" },
    ],
  },
  {
    key: "propertyType",
    multi: true,
    title: "What type of property?",
    options: [
      { label: "HDB", value: "HDB" },
      { label: "Condo", value: "CONDO" },
      { label: "Executive Condo (EC)", value: "EC" },
      { label: "Landed", value: "LANDED" },
    ],
  },
  {
    key: "town",
    multi: true,
    title: "Which town do you prefer?",
    options: [
      ...TOWNS.map((t) => ({ label: titleCase(t), value: t })),
      { label: "Anywhere", value: "" },
    ],
  },
];

function newSessionId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function QuestionFlow({ onComplete, onBack }: Props) {
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Partial<Record<Question["key"], string[]>>>({});
  const [customInput, setCustomInput] = useState("");
  const [customTowns, setCustomTowns] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const question = QUESTIONS[index];
  const picked = answers[question.key] ?? [];
  // Towns the buyer typed in are appended to the list (before "Anywhere") and selected.
  const options =
    question.key === "town"
      ? [
          ...question.options.slice(0, -1),
          ...customTowns.map((t) => ({ label: titleCase(t), value: t })),
          ...question.options.slice(-1),
        ]
      : question.options;
  const isLast = index === QUESTIONS.length - 1;
  // "Anywhere" / "No limit" is the empty-string option; it is exclusive with specific picks.
  const hasAnswer = picked.length > 0;

  function choose(value: string) {
    setAnswers((a) => {
      const current = a[question.key] ?? [];
      if (!question.multi) return { ...a, [question.key]: [value] };
      if (value === "") return { ...a, [question.key]: current.includes("") ? [] : [""] };
      const without = current.filter((v) => v !== "");
      return {
        ...a,
        [question.key]: without.includes(value) ? without.filter((v) => v !== value) : [...without, value],
      };
    });
  }

  function addCustomTown() {
    const town = customInput.trim().replace(/\s+/g, " ").toUpperCase();
    if (!town) return;
    if (!TOWNS.includes(town)) setCustomTowns((c) => (c.includes(town) ? c : [...c, town]));
    setAnswers((a) => {
      const current = (a.town ?? []).filter((v) => v !== "");
      return { ...a, town: current.includes(town) ? current : [...current, town] };
    });
    setCustomInput("");
  }

  function isSelected(value: string) {
    return picked.includes(value);
  }

  function back() {
    setError(null);
    if (index === 0) onBack();
    else setIndex(index - 1);
  }

  async function submit() {
    setSaving(true);
    setError(null);
    const budget = answers.budget?.[0];
    const maxPrice = budget ? Number(budget) : null;
    const minBedrooms = Math.min(...(answers.bedrooms ?? []).map(Number));
    const types = (answers.propertyType ?? []) as PropertyType[];
    const towns = [...new Set((answers.town ?? []).filter((t) => t !== ""))];
    const hard = ["property_type", "min_bedrooms"];
    if (maxPrice !== null) hard.push("max_price_sgd");
    if (towns.length) hard.push("preferred_towns");

    const sessionId = newSessionId();
    try {
      const saved = await api.putPreferences(sessionId, {
        transaction_type: "buy",
        property_type: types.length === 1 ? types[0] : null,
        property_types: types.length > 1 ? types : [],
        max_price_sgd: maxPrice,
        min_price_sgd: null,
        min_bedrooms: minBedrooms,
        min_bathrooms: null,
        min_floor_area_sqm: null,
        preferred_towns: towns,
        hard_constraints: hard,
        soft_weights: {},
        notes: null,
      });
      onComplete(sessionId, saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your answers.");
      setSaving(false);
    }
  }

  return (
    <section className="card">
      <p className="muted small">
        Question {index + 1} of {QUESTIONS.length}
      </p>
      <h2>{question.title}</h2>
      {question.multi && <p className="muted small">Select all that apply.</p>}
      <div className="option-grid" role={question.multi ? "group" : "radiogroup"} aria-label={question.title}>
        {options.map((o) => (
          <button
            key={o.label}
            role={question.multi ? "checkbox" : "radio"}
            aria-checked={isSelected(o.value)}
            className={isSelected(o.value) ? "option selected" : "option"}
            onClick={() => choose(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
      {question.key === "town" && (
        <div className="custom-answer">
          <label htmlFor="custom-town">Not listed? Add your own town / area</label>
          <div className="custom-row">
            <input
              id="custom-town"
              type="text"
              value={customInput}
              placeholder="e.g. Orchard"
              onChange={(e) => setCustomInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCustomTown();
                }
              }}
            />
            <button onClick={addCustomTown} disabled={!customInput.trim()}>
              Add
            </button>
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button className="ghost" onClick={back} disabled={saving}>
          Back
        </button>
        {isLast ? (
          <button onClick={submit} disabled={saving || !hasAnswer}>
            {saving ? "Searching…" : "See results"}
          </button>
        ) : (
          <button onClick={() => setIndex(index + 1)} disabled={!hasAnswer}>
            Next
          </button>
        )}
      </div>
    </section>
  );
}
