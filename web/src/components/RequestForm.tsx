"use client"

import Link from "next/link"
import { useActionState } from "react"
import { submitRequest, type RequestState } from "@/app/actions"

// "Request analysis" form from the design's search results page. The success
// box is the design's; the other outcomes (already analyzed, errors) aren't in
// the design yet and are plain text until the UX team designs them.
export default function RequestForm({ initial = "" }: { initial?: string }) {
  const [state, action, pending] = useActionState<RequestState, FormData>(submitRequest, { kind: "idle" })

  if (state.kind === "accepted" && state.status === "already_available") {
    return (
      <p className="mt-4 text-sm">
        We already have {state.domain}: <Link className="underline" href={`/site/${state.domain}`}>see its report</Link>.
      </p>
    )
  }
  if (state.kind === "accepted") {
    return (
      <div className="mt-4 rounded-lg border border-[#b9d8c4] bg-[#f1f8f3] px-4 py-3 text-sm font-medium text-[#35694a]">
        Request received. We’ll add it to the analysis queue.
      </div>
    )
  }
  return (
    <>
      <form action={action} className="mt-3 flex flex-col gap-3 sm:flex-row">
        <label className="flex-1">
          <span className="sr-only">Domain or policy URL</span>
          <input
            name="domain"
            defaultValue={initial}
            placeholder="example.com or https://example.com/privacy"
            className="h-11 w-full rounded-lg border border-[#ccd5de] bg-white px-4 text-sm text-[#243c52] outline-none placeholder:text-[#9aa6b3] focus:border-[#6685a2] focus:ring-4 focus:ring-[#e1e8ee]"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="h-11 rounded-lg bg-[#172635] px-8 text-sm font-semibold text-white transition hover:bg-[#25445e]"
        >
          Request analysis
        </button>
      </form>
      {state.kind === "error" && <p className="mt-2 text-sm">{state.message}</p>}
    </>
  )
}
