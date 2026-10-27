import "server-only"

// Server-side client for the Imbroglio read API (pipeline/imbroglio/api.py).
// Runs only on the server, so the API base URL and any credentials never
// reach the browser.
//
//   IMBROGLIO_API_URL       e.g. https://api.imbroglio.io (no trailing slash)
//   IMBROGLIO_API_USER      optional basic-auth user while the API is password-protected
//   IMBROGLIO_API_PASSWORD  optional basic-auth password
//   IMBROGLIO_WEB_KEY       must match the API's WEB_CLIENT_KEY (for rate limits)

export type Tier = "LIMITED" | "MODERATE" | "EXTENSIVE" | "SEVERE" | "NOT_DISCLOSED"
export type DocType = "privacy" | "terms"

export type Step = { text: string; link: string | null }
export type WhatYouCanDo = { title: string; why: string; steps: Step[]; learn_anchor: string }

export type Evidence = {
  check_id: string
  question: string
  status: string
  meaning: string
  exposure: number
  quotes: string[]
  explanation: string | null
  document: DocType
  provenance: "machine" | "human" | "agreed"
  model: string
  reused: boolean
  what_you_can_do: WhatYouCanDo | null
}

export type CategoryScore = { key: string; name: string; tier: Tier; findings: Evidence[] }

export type Scorecard = {
  rubric_version: string
  scorer_version: string
  headline: Tier
  headline_categories: string[]
  categories: CategoryScore[]
  analyzed_at: string
  documents: DocType[]
}

export type SiteDocument = {
  type: DocType
  url: string
  fetched_at: string
  versions_stored: number
  changes_detected: number
}

export type Site = {
  domain: string
  state: "unknown" | "queued" | "analyzing" | "ready" | "no_policy_found"
  checked_at: string | null
  documents: SiteDocument[]
  missing: DocType[]
  pending_request: { id: number; status: "queued" | "running"; stage: string | null; queue_ahead: number } | null
  recheck_after: string | null
  scorecard: Scorecard | null
}

export type SearchResult = {
  domain: string
  name: string | null
  documents: DocType[]
  headline: Tier | null
  concerns: string[]
  analyzed_at: string | null
  last_changed: string | null
}

export type SearchResponse = { query: string; results: SearchResult[]; can_request: string | null }

export type LearnTopic = {
  check_id: string
  category: string
  question: string
  title: string
  why: string
  applies_to: string[]
  steps: Step[]
}
export type Learn = { topics: LearnTopic[]; guides: { id: string; title: string; body: string }[] }

export type RubricInfo = {
  rubric_version: string
  scorer_version: string
  rules: string[]
  tiers: { tier: Tier; meaning: string }[]
  categories: {
    key: string
    name: string
    checks: { check_id: string; question: string; statuses: { status: string; meaning: string; tier: Tier }[] }[]
  }[]
}

export type RequestAccepted = {
  request_id: number | null
  domain: string
  status: "queued" | "running" | "already_available" | "no_policy_found"
  created: boolean
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

function base(): string {
  const url = process.env.IMBROGLIO_API_URL
  if (!url) throw new ApiError(500, "IMBROGLIO_API_URL is not set")
  return url.replace(/\/+$/, "")
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json", ...extra }
  const user = process.env.IMBROGLIO_API_USER
  const pass = process.env.IMBROGLIO_API_PASSWORD
  if (user && pass) h.Authorization = "Basic " + Buffer.from(`${user}:${pass}`).toString("base64")
  return h
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(base() + path, { headers: headers(), cache: "no-store" })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.error ?? `API returned ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const getSite = (domain: string) => get<Site>(`/v1/sites/${encodeURIComponent(domain)}`)
export const search = (q: string) => get<SearchResponse>(`/v1/search?q=${encodeURIComponent(q)}&limit=25`)
export const getLearn = () => get<Learn>("/v1/learn")
export const getRubric = () => get<RubricInfo>("/v1/rubric")

// Ask for a site to be analyzed. `clientIp` is passed on with the shared
// IMBROGLIO_WEB_KEY so the API's per-visitor rate limit applies to the
// visitor, not to this server. The API ignores the address without the key.
export async function requestAnalysis(domain: string, clientIp: string | null): Promise<RequestAccepted> {
  const key = process.env.IMBROGLIO_WEB_KEY
  const res = await fetch(base() + "/v1/requests", {
    method: "POST",
    cache: "no-store",
    headers: headers({
      "Content-Type": "application/json",
      ...(clientIp && key ? { "X-Imbroglio-Web-Key": key, "X-Imbroglio-Visitor-IP": clientIp } : {}),
    }),
    body: JSON.stringify({ domain }),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body.error ?? body.detail?.[0]?.msg ?? `API returned ${res.status}`)
  return body as RequestAccepted
}
