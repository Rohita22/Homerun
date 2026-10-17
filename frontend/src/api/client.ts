/**
 * Thin typed fetch wrapper around the Homerun backend (backend/app/api/routes/*.py).
 * One function per endpoint so components never construct URLs or parse JSON themselves —
 * this is the only module that knows the API's shape.
 */

import type {
  ChatResponse,
  CompareResponse,
  FeedbackResponse,
  FinanceEstimateResponse,
  HandoffPreviewResponse,
  HandoffResponse,
  HealthResponse,
  PropertyOut,
  RecommendationResponse,
  BuyerProfile,
  ApiErrorBody,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  code: string;
  requestId: string;
  details: Record<string, unknown>;
  status: number;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.code = body.code;
    this.requestId = body.request_id;
    this.details = body.details;
    this.status = status;
  }
}

/** Last request's trace metadata, surfaced in the system evidence panel (PRD section 12). */
export interface RequestTrace {
  requestId: string | null;
  elapsedMs: number | null;
  path: string;
}

let lastTrace: RequestTrace = { requestId: null, elapsedMs: null, path: "" };
export function getLastTrace(): RequestTrace {
  return lastTrace;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  lastTrace = {
    requestId: response.headers.get("X-Request-ID"),
    elapsedMs: response.headers.get("X-Elapsed-Ms") ? Number(response.headers.get("X-Elapsed-Ms")) : null,
    path,
  };

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (payload?.error) {
      throw new ApiError(payload.error as ApiErrorBody, response.status);
    }
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  chat: (sessionId: string | null, message: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),

  putPreferences: (sessionId: string, profile: Omit<BuyerProfile, "session_id">) =>
    request<BuyerProfile>(`/preferences?session_id=${encodeURIComponent(sessionId)}`, {
      method: "PUT",
      body: JSON.stringify(profile),
    }),

  getRecommendations: (sessionId: string, limit = 5) =>
    request<RecommendationResponse>("/recommendations", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, limit }),
    }),

  getProperty: (listingId: string) =>
    request<PropertyOut>(`/properties/${encodeURIComponent(listingId)}`),

  compare: (listingIds: string[]) =>
    request<CompareResponse>("/compare", {
      method: "POST",
      body: JSON.stringify({ listing_ids: listingIds }),
    }),

  sendFeedback: (sessionId: string, chosenId: string, rejectedId: string | null) =>
    request<FeedbackResponse>("/feedback", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        chosen_id: chosenId,
        rejected_id: rejectedId,
        event_type: rejectedId ? "pairwise_choice" : "like",
      }),
    }),

  estimateFinance: (priceSgd: number, downPaymentSgd: number, annualRatePct: number, years: number) =>
    request<FinanceEstimateResponse>("/finance/estimate", {
      method: "POST",
      body: JSON.stringify({
        price_sgd: priceSgd,
        down_payment_sgd: downPaymentSgd,
        annual_rate_pct: annualRatePct,
        years,
      }),
    }),

  previewHandoff: (listingId: string) =>
    request<HandoffPreviewResponse>("/handoffs/preview", {
      method: "POST",
      body: JSON.stringify({ listing_id: listingId }),
    }),

  executeHandoff: (
    listingId: string,
    channel: "original_listing" | "authorized_direct_lead",
    consent: boolean,
    permittedContactFields: string[] = [],
  ) =>
    request<HandoffResponse>("/handoffs", {
      method: "POST",
      body: JSON.stringify({
        listing_id: listingId,
        channel,
        consent,
        permitted_contact_fields: permittedContactFields,
      }),
    }),
};
