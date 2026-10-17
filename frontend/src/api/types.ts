/**
 * TypeScript mirrors of the backend's Pydantic schemas (backend/app/schemas/*.py).
 * Kept hand-written and minimal rather than codegen'd, since the backend is small and stable;
 * if it grows, point an OpenAPI codegen step at /openapi.json instead of hand-maintaining this.
 */

export type TransactionType = "buy" | "rent";
export type PropertyType = "HDB" | "CONDO" | "LANDED" | "EC";
export type HandoffChannel = "original_listing" | "authorized_direct_lead";

export interface BuyerProfile {
  session_id: string;
  transaction_type: TransactionType;
  property_type: PropertyType | null;
  property_types: PropertyType[];
  max_price_sgd: number | null;
  min_price_sgd: number | null;
  min_bedrooms: number | null;
  min_bathrooms: number | null;
  min_floor_area_sqm: number | null;
  preferred_towns: string[];
  hard_constraints: string[];
  soft_weights: Record<string, number>;
  notes: string | null;
}

export interface AgentTrace {
  agent_name: string;
  status: string;
  elapsed_ms: number;
  model_version: string | null;
  warnings: string[];
  evidence_refs: string[];
  detail: string | null;
}

export interface ChatResponse {
  session_id: string;
  buyer_profile_patch: Partial<BuyerProfile>;
  buyer_profile: BuyerProfile;
  followup_question: string | null;
  warnings: string[];
  used_llm: boolean;
  disclosure: string;
  trace: AgentTrace[];
}

export interface ValuationOut {
  status: string;
  point_estimate_sgd: number | null;
  interval_low_sgd: number | null;
  interval_high_sgd: number | null;
  coverage_note: string | null;
  model_version: string | null;
  reason: string | null;
}

export interface RecommendationItem {
  listing_id: string;
  rank: number;
  score: number;
  reasons: string[];
  factors: Record<string, number>;
  valuation_status: string | null;
  valuation: ValuationOut | null;
  address_public: string | null;
  asking_price_sgd: number | null;
  town: string | null;
}

export interface RecommendationResponse {
  run_id: string;
  session_id: string;
  source_mode: string;
  requested_count: number;
  returned_count: number;
  items: RecommendationItem[];
  excluded_count: number;
  needs_confirmation_count: number;
  warnings: string[];
  trace: AgentTrace[];
}

export interface PropertyOut {
  listing_id: string;
  provider: string;
  source_url: string | null;
  status: string;
  transaction_type: string;
  property_type: string;
  asking_price_sgd: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  floor_area_sqm: number | null;
  address_public: string | null;
  town: string | null;
  latitude: number | null;
  longitude: number | null;
  tenure: string | null;
  lease_remaining_years: number | null;
  floor_level: string | null;
  attributes: Record<string, unknown>;
  images_allowed: boolean;
  attribution: string | null;
  rights_status: string;
  fetched_at: string;
  has_coordinates: boolean;
  valuation_eligible: boolean;
}

export interface CompareResponse {
  listings: PropertyOut[];
  differences: Record<string, unknown[]>;
  caveats: string[];
}

export interface FeedbackResponse {
  updated_weights: Record<string, number>;
  new_run_id: string;
  items: RecommendationItem[];
  trace: AgentTrace[];
}

export interface FinanceScenario {
  label: string;
  annual_rate_pct: number;
  monthly_payment_sgd: number;
  delta_vs_base_sgd: number;
}

export interface FinanceEstimateResponse {
  monthly_payment_sgd: number;
  loan_principal_sgd: number;
  down_payment_sgd: number;
  annual_rate_pct: number;
  tenure_years: number;
  scenarios: FinanceScenario[];
  assumptions: string[];
  trace: AgentTrace[];
}

export interface ContactChoice {
  channel: HandoffChannel;
  requires_consent: boolean;
}

export interface HandoffPreviewResponse {
  listing_id: string;
  association_status: string;
  handoff_state: string;
  safe_contact_choices: ContactChoice[];
  shared_field_preview: string[];
}

export interface HandoffResponse {
  handoff_id: string;
  status: string;
  destination_type: string;
  contact_route: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  build_sha: string;
  architecture: string;
  listing_provider: string;
  listing_provider_healthy: boolean;
  listing_catalog_size: number;
  llm_provider: string;
  database: string;
  valuation_model_version: string;
  valuation_model_is_trained: boolean;
  listings_last_refreshed_at?: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string;
  details: Record<string, unknown>;
}
