"use server"

import { headers } from "next/headers"
import { ApiError, requestAnalysis } from "@/lib/api"

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
