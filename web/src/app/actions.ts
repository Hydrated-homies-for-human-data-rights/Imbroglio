"use server"

import { headers } from "next/headers"
import { ApiError, REPORT_KINDS, requestAnalysis, submitReport as postReport, type ReportKind } from "@/lib/api"

export type RequestState =
  | { kind: "idle" }
  | { kind: "accepted"; domain: string; status: string }
  | { kind: "error"; message: string }

export async function submitRequest(_prev: RequestState, form: FormData): Promise<RequestState> {
  const raw = String(form.get("domain") ?? "").trim()
  if (!raw) return { kind: "error", message: "Enter a domain or policy URL." }
  const h = await headers()
  const ip = h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? h.get("x-real-ip")
  try {
    const r = await requestAnalysis(raw, ip ?? null)
    return { kind: "accepted", domain: r.domain, status: r.status }
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      return { kind: "error", message: "Too many requests right now. Try again later." }
    }
    if (e instanceof ApiError && e.status === 400) {
      return { kind: "error", message: "That doesn't look like a website address." }
    }
    return { kind: "error", message: "Couldn't reach the analysis service. Try again later." }
  }
}

// --- report a problem -------------------------------------------------------

export type ReportState =
  | { kind: "idle" }
  | { kind: "received"; id: number }
  | { kind: "error"; message: string; field?: "domain" | "message" | "kind" }

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

export async function submitProblem(_prev: ReportState, form: FormData): Promise<ReportState> {
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
