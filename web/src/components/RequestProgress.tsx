"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import type { AnalysisRequest } from "@/lib/api"

// Follows one analysis request while it is queued or running: polls the
// status route every couple of seconds and shows which step the worker is
// on. The worker's own log lines are technical, so they are folded into
// four steps and the latest line is shown underneath as detail. When the
// job finishes, the page is refreshed (so the report appears in place) or a
// link to it is shown. Not in the UX team's design yet: plain, like the
// other in-between states.

const STEPS = ["Finding the documents", "Storing them", "Reading them with the model", "Rating"] as const

// Which step a progress line belongs to, by how the pipeline words them.
function stepOf(line: string): number {
  if (/^analysis: .*verified findings/.test(line)) return 3
  if (/^analysis:/.test(line)) return 2
  if (/version stored|unchanged|changed/.test(line)) return 1
  return 0
}

const POLL_MS = 2000
const SLOW_POLL_MS = 5000
const SLOW_AFTER_MS = 120_000
const GIVE_UP_MS = 15 * 60_000

type View =
  | { kind: "loading" }
  | { kind: "queued"; ahead: number }
  | { kind: "running"; step: number; line: string | null }
  | { kind: "done"; found: boolean }
  | { kind: "failed"; error: string | null }
  | { kind: "lost" }

function viewOf(r: AnalysisRequest): View {
  if (r.status === "queued") return { kind: "queued", ahead: r.queue_ahead }
  if (r.status === "running") {
    const lines = r.progress ?? []
    const step = lines.reduce((s, l) => Math.max(s, stepOf(l)), 0)
    return { kind: "running", step, line: lines.length ? lines[lines.length - 1] : null }
  }
  if (r.status === "done") {
    const docs = r.result?.documents ?? []
    return { kind: "done", found: docs.some((d) => d.found) }
  }
  return { kind: "failed", error: r.error }
}

export default function RequestProgress({
  id,
  domain,
  refreshOnDone = false,
}: {
  id: number
  domain: string
  refreshOnDone?: boolean
}) {
  const router = useRouter()
  const [view, setView] = useState<View>({ kind: "loading" })

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const started = Date.now()

    async function tick() {
      if (stopped) return
      let next: View
      try {
        const res = await fetch(`/api/v1/requests/${id}`, { cache: "no-store" })
        if (res.status === 404) next = { kind: "lost" }
        else if (!res.ok) next = view.kind === "loading" ? { kind: "loading" } : view
        else next = viewOf((await res.json()) as AnalysisRequest)
      } catch {
        next = view.kind === "loading" ? { kind: "loading" } : view
      }
      if (stopped) return
      setView(next)
      const active = next.kind === "loading" || next.kind === "queued" || next.kind === "running"
      if (next.kind === "done" && refreshOnDone) router.refresh()
      if (!active || Date.now() - started > GIVE_UP_MS) return
      timer = setTimeout(tick, Date.now() - started > SLOW_AFTER_MS ? SLOW_POLL_MS : POLL_MS)
    }
    tick()
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, refreshOnDone])

  const report = (
    <Link className="underline" href={`/site/${encodeURIComponent(domain)}`}>
      See the report
    </Link>
  )

  if (view.kind === "lost") {
    return <p className="mt-4 text-sm">We lost track of this request. {report} to check on {domain}.</p>
  }
  if (view.kind === "failed") {
    return (
      <div className="mt-4 rounded-lg border border-[#e3c4c0] bg-[#fbf2f1] px-4 py-3 text-sm text-[#8a3328]">
        The analysis of {domain} failed{view.error ? `: ${view.error}` : ""}. You can request it again later.
      </div>
    )
  }
  if (view.kind === "done") {
    return (
      <div className="mt-4 rounded-lg border border-[#b9d8c4] bg-[#f1f8f3] px-4 py-3 text-sm text-[#35694a]">
        {view.found ? (
          <>
            Done. {refreshOnDone ? "Loading the report…" : report}
          </>
        ) : (
          <>
            We couldn’t find a privacy policy or terms for {domain}. {report} for what we tried.
          </>
        )}
      </div>
    )
  }

  const step = view.kind === "running" ? view.step : -1
  return (
    <div className="mt-4 rounded-lg border border-[#ccd5de] bg-white px-4 py-3 text-sm" role="status" aria-live="polite">
      <p className="font-medium text-[#243c52]">
        {view.kind === "queued"
          ? view.ahead > 0
            ? `Queued: ${view.ahead} ${view.ahead === 1 ? "site" : "sites"} ahead of ${domain}.`
            : `Queued: ${domain} is next.`
          : view.kind === "running"
            ? `Analyzing ${domain}. Most sites take one to three minutes.`
            : `Checking on ${domain}…`}
      </p>
      <ol className="mt-2 grid gap-1">
        {STEPS.map((label, i) => {
          const state = i < step ? "done" : i === step ? "now" : "todo"
          return (
            <li
              key={label}
              className={`flex items-center gap-2 ${
                state === "done" ? "text-[#35694a]" : state === "now" ? "text-[#243c52]" : "text-[#9aa6b3]"
              }`}
            >
              <span
                aria-hidden="true"
                className={`inline-block h-2 w-2 rounded-full ${
                  state === "done" ? "bg-[#4d8b65]" : state === "now" ? "animate-pulse bg-[#245f9e]" : "bg-[#d4dbe2]"
                }`}
              />
              {label}
              {state === "done" && <span className="sr-only"> (done)</span>}
            </li>
          )
        })}
      </ol>
      {view.kind === "running" && view.line && (
        <p className="mt-2 truncate font-mono text-xs text-[#66778a]" title={view.line}>
          {view.line}
        </p>
      )}
    </div>
  )
}
