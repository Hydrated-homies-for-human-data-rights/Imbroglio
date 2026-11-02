"use client"

import { useActionState, useState } from "react"
import { submitProblem, type ReportState } from "@/app/actions"

const KINDS: { value: string; label: string }[] = [
  { value: "rating", label: "A rating is wrong" },
  { value: "quote", label: "A quote is wrong, or doesn’t support the finding" },
  { value: "wrong_document", label: "You read the wrong document" },
  { value: "missing", label: "A site is missing, or its policy wasn’t found" },
  { value: "other", label: "Something else" },
]

// The form itself. Validation happens in the server action and again at the
// API; this only shows what came back. The fields are controlled so that
// what was typed survives an error (React resets a form after an action).
// The `website` field is a honeypot: it is hidden from people, and a
// submission that fills it is dropped.
export default function ReportForm({ site = "", page = "" }: { site?: string; page?: string }) {
  const [state, action, pending] = useActionState<ReportState, FormData>(submitProblem, { kind: "idle" })
  const [domain, setDomain] = useState(site)
  const [kind, setKind] = useState("")
  const [message, setMessage] = useState("")
  const [contact, setContact] = useState("")

  if (state.kind === "received") {
    return (
      <div className="received" role="status">
        <p>
          <strong>Received.</strong> This is report {state.id}. A team member rereads it against the stored
          document; if the quote doesn’t support the finding, we withdraw it rather than defend it.
        </p>
      </div>
    )
  }

  const bad = state.kind === "error" ? state.field : undefined
  return (
    <form action={action} className="form" noValidate>
      <label>
        <span className="lbl mono">Website</span>
        <input
          name="domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="example.com"
          autoComplete="off"
          maxLength={253}
          aria-invalid={bad === "domain" || undefined}
        />
        <span className="hint">Leave it empty if the problem isn’t about one site.</span>
      </label>

      <label>
        <span className="lbl mono">What kind of problem</span>
        <select name="kind" value={kind} onChange={(e) => setKind(e.target.value)} required aria-invalid={bad === "kind" || undefined}>
          <option value="" disabled>
            Choose one
          </option>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        <span className="lbl mono">What’s wrong</span>
        <textarea
          name="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
          minLength={10}
          maxLength={4000}
          placeholder="Which finding or quote, and what the document actually says if you know."
          aria-invalid={bad === "message" || undefined}
        />
        <span className="hint">Up to 4,000 characters. Plain text; links are fine.</span>
      </label>

      <label>
        <span className="lbl mono">Where to reach you (optional)</span>
        <input
          name="contact"
          type="email"
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
          maxLength={200}
        />
        <span className="hint">Only used to tell you what we found. Never shown anywhere.</span>
      </label>

      <input type="hidden" name="page" value={page} />
      <div className="hp" aria-hidden="true">
        <label>
          Leave this field empty
          <input name="website" tabIndex={-1} autoComplete="off" defaultValue="" />
        </label>
      </div>

      {state.kind === "error" && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      <button type="submit" className="submit" disabled={pending}>
        {pending ? "Sending…" : "Send the report"}
      </button>
    </form>
  )
}
