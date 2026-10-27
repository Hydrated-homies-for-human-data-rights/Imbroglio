import { connection } from "next/server"
import { Suspense } from "react"
import Header from "@/components/Header"
import { RatingMark, ratingOf } from "@/components/design"
import { getRubric } from "@/lib/api"
import { REPO_URL, disputeUrl } from "@/lib/links"

// "How we score" (requirement F5): the rubric, the scoring rules and our
// measured accuracy. Not in the design yet: plain until the UX team designs it.

// Measured figures, with when they were measured. Update these with each new
// measurement; docs/evaluation.md has the details behind each one.
const MEASUREMENTS: { figure: string; what: string; when: string }[] = [
  { figure: "99.7%", what: "of 627 quotes the AI cited were found word for word in the policy. The rest were never shown.", when: "Oct 6, 2026" },
  { figure: "19 of 20", what: "sites in our test sample had their privacy policy found and extracted correctly.", when: "Sep 2026" },
  { figure: "79%", what: "of 86 reachable sites from a random sample of 100 had their privacy policy found.", when: "Oct 2026" },
  { figure: "0.765", what: "macro F1 for our baseline policy text classifier on the OPP-115 benchmark (target 0.70). Not yet used in live ratings.", when: "Oct 2026" },
]
const NOT_YET = [
  "Run-to-run consistency: whether analyzing the same document three times gives the same answers.",
  "Agreement with ToS;DR's human reviewers on individual findings.",
]

async function Rubric() {
  await connection() // read at request time, never baked in at build
  let rubric
  try {
    rubric = await getRubric()
  } catch {
    return <p className="mt-6">The rubric is unavailable right now. It is also in our source code.</p>
  }
  return (
    <>
      <h2 className="mt-8 text-base font-bold">What the ratings mean</h2>
      <ul className="mt-2 grid gap-2">
        {rubric.tiers.map((t) => (
          <li key={t.tier} className="flex items-start gap-3">
            <span className="mt-0.5 flex w-5 justify-center">
              <RatingMark rating={ratingOf[t.tier]} />
            </span>
            <span>
              <strong>{ratingOf[t.tier]}:</strong> {t.meaning}
            </span>
          </li>
        ))}
      </ul>

      <h2 className="mt-8 text-base font-bold">The rules</h2>
      <ol className="mt-2 list-decimal pl-5">
        {rubric.rules.map((r) => (
          <li key={r} className="mt-1">
            {r}
          </li>
        ))}
      </ol>

      <h2 className="mt-8 text-base font-bold">Every question we ask</h2>
      <p className="mt-1">
        Rubric {rubric.rubric_version}, scorer {rubric.scorer_version}. Each answer leads to the rating shown next to it.
      </p>
      {rubric.categories.map((c) => (
        <section key={c.key} className="mt-5">
          <h3 className="font-bold">{c.name}</h3>
          {c.checks.map((k) => (
            <div key={k.check_id} className="mt-2">
              <p>{k.question}</p>
              <ul className="mt-1 pl-5">
                {k.statuses.map((s) => (
                  <li key={s.status} className="flex items-start gap-2">
                    <span className="mt-1 flex w-5 shrink-0 justify-center">
                      <RatingMark rating={ratingOf[s.tier]} />
                    </span>
                    <span>
                      {s.meaning} <span className="text-[#5a6b7e]">({ratingOf[s.tier]})</span>
                    </span>
                  </li>
                ))}
                <li className="flex items-start gap-2">
                  <span className="mt-1 flex w-5 shrink-0 justify-center">
                    <RatingMark rating="Not disclosed" />
                  </span>
                  <span>
                    The documents don&apos;t address this <span className="text-[#5a6b7e]">(Not disclosed)</span>
                  </span>
                </li>
              </ul>
            </div>
          ))}
        </section>
      ))}
    </>
  )
}

export default function HowWeScore() {
  return (
    <>
      <Header view="report" />
      <main className="mx-auto max-w-[860px] px-5 py-10 text-sm leading-6 sm:px-8">
        <h1 className="text-2xl font-bold">How we score</h1>
        <p className="mt-2">
          We read each site&apos;s privacy policy and terms of service and ask the same fixed questions of every one.
          An AI model answers each question and must quote the document. Our code then checks every quote word for
          word against the stored text, throws out any it can&apos;t find, and turns the answers into ratings with
          fixed rules. The AI never decides a rating.
        </p>

        <h2 className="mt-8 text-base font-bold">How accurate it is</h2>
        <ul className="mt-2 grid gap-2">
          {MEASUREMENTS.map((m) => (
            <li key={m.figure}>
              <strong>{m.figure}</strong> {m.what} <span className="text-[#5a6b7e]">Measured {m.when}.</span>
            </li>
          ))}
        </ul>
        <p className="mt-3">Not measured yet, and we&apos;ll publish them here when they are:</p>
        <ul className="mt-1 list-disc pl-5">
          {NOT_YET.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>

        <Suspense fallback={<p className="mt-6">Loading the rubric…</p>}>
          <Rubric />
        </Suspense>

        <h2 className="mt-8 text-base font-bold">If we got something wrong</h2>
        <p className="mt-1">
          <a className="underline" href={disputeUrl()} target="_blank" rel="noopener noreferrer">
            Report a problem
          </a>{" "}
          with any rating or finding. A team member rereads it against the stored document, and if the quote
          doesn&apos;t support the finding, we withdraw it. Everything here is open source:{" "}
          <a className="underline" href={REPO_URL} target="_blank" rel="noopener noreferrer">
            read the code
          </a>
          .
        </p>
      </main>
    </>
  )
}
