import "server-only"

// Server-side client for the Imbroglio read API (pipeline/imbroglio/api.py).
// Runs only on the server, so the API base URL and any credentials never
// reach the browser.
//
//   IMBROGLIO_API_URL       e.g. https://api.imbroglio.io (no trailing slash)
//   IMBROGLIO_API_USER      optional basic-auth user while the API is password-protected
//   IMBROGLIO_API_PASSWORD  optional basic-auth password
//   IMBROGLIO_WEB_KEY       must match the API's WEB_CLIENT_KEY (for rate limits)

// UNCLEAR (scorer s2) only ever appears as an overall rating: too few of the
// key questions were answered to call a site's practices limited. INFO (s2)
// only ever rates a category or an answer: the practice is reported, not rated.
export type Tier = "LIMITED" | "MODERATE" | "EXTENSIVE" | "SEVERE" | "NOT_DISCLOSED" | "UNCLEAR" | "INFO"
export type DocType = "privacy" | "terms"

export type Step = { text: string; link: string | null }
export type WhatYouCanDo = { title: string; why: string; steps: Step[]; learn_anchor: string }

export type Evidence = {
  check_id: string
  question: string
  status: string
  meaning: string
  // the answer in the reader's words (rubric v1.0 on); show it when present
  plain?: string | null
  exposure: number
  // scorer s2: "info" = reported but not rated, null = protective (or rubric v0.1)
  concern: "severe" | "high" | "medium" | "info" | null
  quotes: string[]
  explanation: string | null
  document: DocType
  provenance: "machine" | "human" | "agreed"
  model: string
  reused: boolean
  what_you_can_do: WhatYouCanDo | null
}

export type CategoryScore = { key: string; name: string; tier: Tier; findings: Evidence[] }

// The overall rating out of 100 (higher is better): 100 minus each
// concern's points, kept inside the rating's range. Null for UNCLEAR and
// NOT_DISCLOSED sites.
export type ScoreDeduction = {
  check_id: string
  category: string
  status: string
  meaning: string
  plain?: string | null
  points: number
}
export type SiteScore = {
  value: number
  starts_at: number
  deductions: ScoreDeduction[]
  band: [number, number]
  unadjusted: number
}

export type Scorecard = {
  rubric_version: string
  scorer_version: string
  headline: Tier
  score?: SiteScore | null
  // "In short": sentences from the rubric's plain lines, biggest concerns first (rubric v0.3 on)
  summary?: string[] | null
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

// The site's own page for a category's advice (its opt-out, settings or
// request page), found on its homepage or policy, or listed by hand for the
// big sites whose settings pages nothing links to ("known"). One per category.
export type SiteLink = {
  category: string
  kind: string
  url: string
  text: string
  source: "homepage" | "privacy" | "terms" | "known"
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
  links?: SiteLink[]
}

export type SearchResult = {
  domain: string
  name: string | null
  documents: DocType[]
  headline: Tier | null
  concerns: string[]
  analyzed_at: string | null
  last_changed: string | null
  // out of 100; null until analyzed, or for UNCLEAR / NOT_DISCLOSED
  score?: number | null
  // the answer that takes the most points off, in plain words when the rubric has them
  reason?: string | null
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

// One analysis request as the worker moves it along (GET /v1/requests/{id}).
// `progress` is the worker's own log lines, newest last; `result` is filled
// in when it is done.
export type AnalysisRequest = {
  id: number
  domain: string
  status: "queued" | "running" | "done" | "failed"
  stage: string | null
  progress: string[]
  result: { documents?: { doc_type: DocType; found: boolean; status: string; analysis: string | null }[] } | null
  error: string | null
  queue_ahead: number
  requested_at: string
  started_at: string | null
  finished_at: string | null
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
export const getRecent = (limit = 10) => get<{ sites: SearchResult[] }>(`/v1/recent?limit=${limit}`)
export const getLearn = () => get<Learn>("/v1/learn")
export const getRubric = () => get<RubricInfo>("/v1/rubric")
export const getRequest = (id: number) => get<AnalysisRequest>(`/v1/requests/${id}`)
// Passed through untouched to the browser extension (see app/api/v1/lookup).
// Like requestAnalysis, it passes on the visitor's address so the API's
// per-visitor lookup limit applies to them, not to this server.
export async function lookup(prefix: string, clientIp: string | null): Promise<unknown> {
  const key = process.env.IMBROGLIO_WEB_KEY
  const res = await fetch(base() + `/v1/lookup/${encodeURIComponent(prefix)}`, {
    cache: "no-store",
    headers: headers(clientIp && key ? { "X-Imbroglio-Web-Key": key, "X-Imbroglio-Visitor-IP": clientIp } : {}),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.error ?? `API returned ${res.status}`)
  }
  return res.json()
}

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

// --- report a problem -------------------------------------------------------

export const REPORT_KINDS = ["rating", "quote", "wrong_document", "missing", "other"] as const
export type ReportKind = (typeof REPORT_KINDS)[number]
export type NewReport = {
  domain: string | null
  kind: ReportKind
  message: string
  contact: string | null
  page: string | null
  website: string // honeypot: real forms leave it empty
}
export type ReportReceived = { id: number; received_at: string }

// Store a problem report. Like requestAnalysis, the visitor's address goes
// with the shared key so the API's per-visitor limit applies to the visitor.
export async function submitReport(report: NewReport, clientIp: string | null): Promise<ReportReceived> {
  const key = process.env.IMBROGLIO_WEB_KEY
  const res = await fetch(base() + "/v1/reports", {
    method: "POST",
    cache: "no-store",
    headers: headers({
      "Content-Type": "application/json",
      ...(clientIp && key ? { "X-Imbroglio-Web-Key": key, "X-Imbroglio-Visitor-IP": clientIp } : {}),
    }),
    body: JSON.stringify(report),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body.error ?? body.detail?.[0]?.msg ?? `API returned ${res.status}`)
  return body as ReportReceived
}
