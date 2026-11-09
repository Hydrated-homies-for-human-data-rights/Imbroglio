"use client"

import { useState } from "react"

// A small share button for a report. Phones (and browsers with a share
// sheet) get the system share sheet; everywhere else the link is copied.
// Not in the design yet: styled like the report's other secondary buttons.
export default function ShareButton({ path, text }: { path: string; text: string }) {
  const [note, setNote] = useState<string | null>(null)

  const flash = (message: string) => {
    setNote(message)
    setTimeout(() => setNote(null), 2000)
  }

  const share = async () => {
    const url = new URL(path, window.location.origin).toString()
    if (navigator.share) {
      try {
        await navigator.share({ title: "Imbroglio", text, url })
        return
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return // closed the sheet
      }
    }
    try {
      await navigator.clipboard.writeText(url)
      flash("Link copied")
    } catch {
      flash("Couldn’t copy the link")
    }
  }

  return (
    <button
      type="button"
      onClick={share}
      className="inline-flex items-center gap-1.5 rounded-lg border border-[#ccd5de] bg-white px-3 py-1.5 text-sm font-medium text-[#344c63] transition hover:border-[#96a7b7] hover:bg-[#f9fafb]"
    >
      <svg viewBox="0 0 20 20" aria-hidden="true" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10 12.5V3M6.5 6.5 10 3l3.5 3.5M4.5 10v5.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V10" />
      </svg>
      <span aria-live="polite">{note ?? "Share"}</span>
    </button>
  )
}
