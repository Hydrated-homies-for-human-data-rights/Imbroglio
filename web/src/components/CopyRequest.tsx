"use client"

import { useEffect, useRef, useState } from "react"
import { CheckIcon } from "./design"

// Copies a short request the reader can send a company, for when we found
// no page of theirs for it. Nothing leaves the browser. If the clipboard
// can't be used, the request is shown so it can be copied by hand.
async function toClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // older browsers, or a page without clipboard access
    try {
      const area = document.createElement("textarea")
      area.value = text
      area.setAttribute("readonly", "")
      area.style.position = "fixed"
      area.style.opacity = "0"
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand("copy")
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}

export default function CopyRequest({
  request,
  label = "Copy a short request you can send them",
}: {
  request: string
  label?: string
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle")
  const reset = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(reset.current), [])

  const copy = async () => {
    const ok = await toClipboard(request)
    setState(ok ? "copied" : "failed")
    clearTimeout(reset.current)
    if (ok) reset.current = setTimeout(() => setState("idle"), 4000)
  }

  return (
    <>
      <button
        type="button"
        onClick={copy}
        className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-[#ccd5de] bg-white px-4 text-sm font-medium text-[#344c63] transition hover:border-[#96a7b7] hover:bg-[#f9fafb]"
      >
        {state === "copied" ? (
          <>
            <CheckIcon />
            Copied
          </>
        ) : (
          label
        )}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {state === "copied"
          ? "Copied the request. Paste it into an email or their contact form."
          : state === "failed"
            ? "Couldn’t copy. The request is shown below."
            : ""}
      </span>
      {state === "failed" && (
        <p className="order-last mt-2 w-full whitespace-pre-line rounded-lg border border-[#dfe4ea] bg-[#f7fafc] p-3 text-sm text-[#183149] select-all">
          {request}
        </p>
      )}
    </>
  )
}
