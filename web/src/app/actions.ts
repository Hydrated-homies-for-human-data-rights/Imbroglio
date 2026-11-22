"use server"

import { headers } from "next/headers"
import {
  ApiError,
  POLICY_LINK_ERROR,
  REPORT_KINDS,
  requestAnalysis,
  submitReport as postReport,
  type Failure,
  type ReportKind,
} from "@/lib/api"

export type RequestState =
  | { kind: "idle" }
  | { kind: "accepted"; domain: string; status: string; requestId: string | null; failure: Failure | null }
  | { kind: "error"; message: string }

// "example.com/privacy" or "https://example.com/privacy?x=1" as a link to a
// page, or null when it is just a site ("example.com", "https://example.com/").
function pageLink(raw: string): string | null {
  let url: URL
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`)
  } catch {
    return null
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null
  if (url.pathname.replace(/\/+$/, "") === "" && !url.search) return null
  url.hash = ""
  return url.href
}

// The form takes a domain or a link to a policy. On a site's own page it
// also carries that site (`site`), and the box only takes a link on it.
export async function submitRequest(_prev: RequestState, form: FormData): Promise<RequestState> {
  const raw = String(form.get("domain") ?? "").trim()
  const site = String(form.get("site") ?? "").trim()
  if (!raw) return { kind: "error", message: site ? "Paste a link to the policy." : "Enter a domain or policy URL." }
  const link = pageLink(raw)
  if (site && !link) return { kind: "error", message: `Paste the full link to the policy on ${site}.` }
  const h = await headers()
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? h.get("x-real-ip")
  try {
    const r = await requestAnalysis(site || raw, ip ?? null, link)
    return { kind: "accepted", domain: r.domain, status: r.status, requestId: r.request_id, failure: r.failure ?? null }
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      return { kind: "error", message: "Too many requests right now. Try again later." }
    }
    if (e instanceof ApiError && e.status === 400 && e.message === POLICY_LINK_ERROR) {
      return {
        kind: "error",
        message: `We can only use a link on ${site || "the site"} itself. Paste a link to the policy on that site.`,
      }
    }
    if (e instanceof ApiError && e.status === 400) {
      return { kind: "error", message: "That doesn't look like a website address." }
    }
    return { kind: "error", message: "Couldn't reach the analysis service. Try again later." }
  }
}

// --- report a problem -------------------------------------------------------

// `attempt` counts the tries that came back with an error, so the form can
// redraw its radio buttons after each one (see ReportForm).
export type ReportState =
  | { kind: "idle" }
  | { kind: "received"; id: number }
  | { kind: "error"; message: string; field?: "domain" | "message" | "kind"; attempt: number }

const MAX = { domain: 253, message: 4000, contact: 200, page: 500 }

// Text from the form is kept as typed, minus control characters, and is only
// ever stored and shown as text, never as markup. Lengths are capped here
// and again at the API.
function text(form: FormData, name: string, max: number): string {
  return String(form.get(name) ?? "")
    .replace(/[^\P{Cc}\n\t]/gu, "")
    .trim()
    .slice(0, max)
}

export async function submitProblem(prev: ReportState, form: FormData): Promise<ReportState> {
  const r = await checkAndSend(form)
  if (r.kind !== "error") return r
  const before = prev.kind === "error" && Number.isSafeInteger(prev.attempt) ? prev.attempt : 0
  return { ...r, attempt: before + 1 }
}

type Outcome = { kind: "received"; id: number } | { kind: "error"; message: string; field?: "domain" | "message" | "kind" }

async function checkAndSend(form: FormData): Promise<Outcome> {
  const domain = text(form, "domain", MAX.domain)
  const kind = String(form.get("kind") ?? "")
  const message = text(form, "message", MAX.message)
  const contact = text(form, "contact", MAX.contact)
  const page = text(form, "page", MAX.page)
  const website = String(form.get("website") ?? "") // honeypot

  if (!(REPORT_KINDS as readonly string[]).includes(kind)) {
    return { kind: "error", message: "Choose what kind of problem it is.", field: "kind" }
  }
  if (domain && !/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(domain.replace(/^https?:\/\//i, "").split("/")[0])) {
    return { kind: "error", message: "That doesn't look like a website address.", field: "domain" }
  }
  if (message.length < 10) {
    return { kind: "error", message: "Tell us a little more: at least ten characters.", field: "message" }
  }
  const h = await headers()
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? h.get("x-real-ip")
  try {
    const r = await postReport(
      {
        domain: domain ? domain.replace(/^https?:\/\//i, "").split("/")[0].toLowerCase() : null,
        kind: kind as ReportKind,
        message,
        contact: contact || null,
        page: page || null,
        website,
      },
      ip ?? null,
    )
    return { kind: "received", id: r.id }
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      return { kind: "error", message: "Too many reports from here right now. Try again in an hour." }
    }
    if (e instanceof ApiError && e.status === 400) {
      return { kind: "error", message: e.message }
    }
    return { kind: "error", message: "Couldn't reach the service. Try again in a minute." }
  }
}
