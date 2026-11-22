"use client"

import { useActionState, useState } from "react"
import { submitProblem, type ReportState } from "@/app/actions"
import type { DocType, Tier } from "@/lib/api"
import { Verdict } from "./chrome"

const KINDS: { value: string; label: string; hint: string }[] = [
  { value: "quote", label: "The quote doesn’t say that", hint: "The sentence we cite doesn’t support the finding, or says the opposite." },
  { value: "rating", label: "The rating is wrong", hint: "The finding is right, but the rating it leads to seems off." },
  { value: "wrong_document", label: "You read the wrong page", hint: "What we stored isn’t the site’s privacy policy or terms." },
  { value: "missing", label: "Something is missing", hint: "A practice we didn’t find, a site we have no report for, or a policy we couldn’t reach." },
  { value: "other", label: "Something else", hint: "" },
]

// One of the site's findings, as its report shows it: the plain line, the
// rating it leads to and the quote it rests on.
export type Pickable = {
  key: string // check_id:document
  check_id: string
  document: DocType
  docName: string
  plain: string
  tier: Tier
  quote: string
}

// The form. Validation happens in the server action and again at the API;
// this only shows what came back. The fields are controlled so that what was
// typed survives an error (React resets a form after an action). The
// `website` field is a honeypot: hidden from people, and a submission that
// fills it is dropped.
//
// The radio buttons need one more step. React's reset puts each radio back
// to how it was when it was first drawn (its default), and React doesn't
// redraw it because its `checked` prop hasn't changed, so after an error the
// buttons could show, and resend, the first choice instead of the reader's:
// a retry from ?finding= would file "quote". So each error redraws them
// (`key`, from the action's attempt count): new radios start out checked
// from the state, and that is also the default the reset goes back to.
//
// Opened from a site's report (`/report?site=`), it lists that site's
// findings first, so the reader can point at the one that's wrong. Which one
// travels in the existing `page` field: /site/<domain>?doc=<type>#<check_id>.
export default function ReportForm({
  site = "",
  findings = [],
  initial = "",
}: {
  site?: string
  findings?: Pickable[]
  initial?: string
}) {
  const [state, action, pending] = useActionState<ReportState, FormData>(submitProblem, { kind: "idle" })
  const [domain, setDomain] = useState(site)
  const [picked, setPicked] = useState(findings.some((f) => f.key === initial) ? initial : "")
  const [kind, setKind] = useState(initial ? "quote" : "")
  const [message, setMessage] = useState("")
  const [contact, setContact] = useState("")

  if (state.kind === "received") {
    return (
      <div className="received" role="status">
        <p>
          <strong>Received.</strong> This is report {state.id}. A team member rereads it against the stored
          document; if the quote doesn’t support the finding, we withdraw it rather than defend it and work out the
          rating again.
        </p>
      </div>
    )
  }

  const bad = state.kind === "error" ? state.field : undefined
  const round = state.kind === "error" ? state.attempt : 0
  const target = findings.find((f) => f.key === picked)
  const pointing = site && findings.length > 0
  const page = !site ? "" : target ? `/site/${site}?doc=${target.document}#${target.check_id}` : `/site/${site}`

  const pick = (key: string) => {
    setPicked(key)
    if (key === "none") setKind("missing")
    else if (!kind || kind === "missing" || kind === "wrong_document") setKind("quote")
  }

  const fields = (
    <>
      {pointing ? (
        <input type="hidden" name="domain" value={site} />
      ) : (
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
      )}

      {target && (
        <div className="rp-target">
          <span className="mono">You’re reporting</span>
          <strong>{target.plain}</strong>
          <span className="serif">“{target.quote}”</span>
        </div>
      )}

      <fieldset className="rp-kinds" aria-invalid={bad === "kind" || undefined}>
        <legend className="lbl mono">What kind of problem</legend>
        <div key={round}>
          {KINDS.map((k) => (
            <label key={k.value}>
              <input
                type="radio"
                name="kind"
                value={k.value}
                checked={kind === k.value}
                onChange={() => setKind(k.value)}
              />
              {k.label}
            </label>
          ))}
        </div>
        <span className="hint">{KINDS.find((k) => k.value === kind)?.hint ?? "Choose one."}</span>
      </fieldset>

      <label>
        <span className="lbl mono">{pointing ? "In your words" : "What’s wrong"}</span>
        <textarea
          name="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          required
          minLength={10}
          maxLength={4000}
          placeholder={
            target
              ? "What does the document actually say? A section or nearby sentence helps."
              : "Which finding or quote, and what the document actually says if you know."
          }
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
    </>
  )

  if (!pointing)
    return (
      <form action={action} className="form" noValidate>
        {fields}
      </form>
    )

  return (
    <form action={action} className="rp-grid" noValidate>
      <fieldset className="rp-pick">
        <legend className="lbl mono">1 · Which finding on {site}</legend>
        <div className="rp-list" key={round}>
          {findings.map((f) => (
            <label key={f.key} className="rp-finding">
              <input type="radio" name="finding" value={f.key} checked={picked === f.key} onChange={() => pick(f.key)} />
              <span className="dot" aria-hidden="true" />
              <span className="plain">{f.plain}</span>
              <Verdict tier={f.tier} />
              <span className="q serif">“{f.quote}”</span>
              <span className="meta mono">{f.docName}</span>
            </label>
          ))}
          <label className="rp-finding">
            <input type="radio" name="finding" value="none" checked={picked === "none"} onChange={() => pick("none")} />
            <span className="dot" aria-hidden="true" />
            <span className="plain">It’s not one of these</span>
            <span />
            <span className="q">A practice we missed, the wrong page, or a problem with the site as a whole.</span>
          </label>
        </div>
      </fieldset>
      <div className="rp-side">
        <p className="lbl mono">2 · What’s wrong with it</p>
        <div className="form">{fields}</div>
      </div>
    </form>
  )
}
