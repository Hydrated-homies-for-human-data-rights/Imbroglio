import type { Metadata } from "next"
import Link from "next/link"
import { connection } from "next/server"
import { Suspense } from "react"
import Page, { Chapter } from "@/components/home/Page"
import { Verdict } from "@/components/home/chrome"
import { EXCERPT, FIGURES, FIRST_THREAD, TIER_WORD } from "@/components/home/data"
import { getRubric, type Tier } from "@/lib/api"

export const metadata: Metadata = {
  title: "How we score · Imbroglio",
  description: "Every question we ask of a privacy policy, how quotes are verified, the rules that turn answers into ratings, and how accurate it is.",
}

// "How we score" (requirement F5): the method, the rubric, the scoring rules
// and our measured accuracy. The rubric itself comes from the API at request
// time so this page can never disagree with the scorer; what it means is
// written here, from docs/rubric.md.

// Measured figures, with when they were measured. Update these with each new
// measurement; docs/evaluation.md has the details behind each one.
const MEASUREMENTS: { figure: string; miss?: boolean; what: string; when: string }[] = [
  {
    figure: `${FIGURES.found}%`,
    what: `of the ${FIGURES.quotes.toLocaleString("en-US")} quotes the model cited across ${FIGURES.sites} sites were found word for word in the stored document. The target is 95%.`,
    when: "Nov 2, 2026",
  },
  {
    figure: `${FIGURES.onTopic}%`,
    what: "of those quotes also contained one of the question’s evidence words, so they are about the question asked. Only quotes that pass both checks are shown; the rest are kept for review.",
    when: "Nov 2, 2026",
  },
  {
    figure: "88.4%",
    miss: true,
    what: "of answers came out the same in all three runs when 50 privacy policies were analyzed three times each. The target is 90%. Overall ratings matched in 66% of documents.",
    when: "Oct 30, 2026",
  },
  { figure: "79%", what: "of 86 reachable sites from a random sample of 100 had their privacy policy found.", when: "Oct 2026" },
  { figure: "19 of 20", what: "sites in the feasibility sample had their privacy policy found and extracted correctly.", when: "Sep 2026" },
  {
    figure: "0.765",
    what: "macro F1 for the baseline policy text classifier on the OPP-115 benchmark, against a target of 0.70. Not yet used in live ratings.",
    when: "Oct 2026",
  },
]
const NOT_YET = ["Agreement with ToS;DR’s human reviewers on individual findings."]

// What each rating means, as the scorer defines it (fallback when the API
// cannot be reached; the live list is the same text served by /v1/rubric).
const TIERS: { tier: Tier; meaning: string }[] = [
  { tier: "SEVERE", meaning: "Two or more red flags, or one of the two worst on its own: selling your data for money, or no way to delete it." },
  { tier: "EXTENSIVE", meaning: "One red flag: a practice present and broad, with some limit or choice disclosed." },
  { tier: "MODERATE", meaning: "Two or more medium concerns: practices present with clear limits, or a choice you can exercise." },
  { tier: "LIMITED", meaning: "Nothing of concern was found, and enough of the key questions were answered to say so." },
  { tier: "UNCLEAR", meaning: "Nothing of concern was found, but too few of the key questions were answered to call the site limited. Silence is never read as good." },
  { tier: "NOT_DISCLOSED", meaning: "The documents say nothing about the practice." },
  { tier: "INFO", meaning: "The practice is reported but not rated, such as what categories of data are collected." },
]

const STEPS = [
  { h: "Fetch and keep every version", p: "The privacy policy and the terms of service, from the site itself, following privacy hubs through to the real document. Each version is hashed and stored, so a quiet rewrite is caught and dated." },
  { h: "Ask the same questions of every document", p: "Fourteen fixed questions in seven categories, with a fixed set of allowed answers. A model reads the stored text and answers each one, and for every answer it must quote the document." },
  { h: "Check every quote in code", p: "Each quote is searched for, word for word, in the stored text. Whitespace and curly quotes are forgiven; a changed word, a dropped “not”, or a quote about a different topic is not. A finding with no quote that passes is never shown and never scored." },
  { h: "Turn answers into ratings with public rules", p: "Each allowed answer carries a concern level the rubric fixes in advance. Plain code counts the red flags and applies the rules below. No model decides a rating." },
  { h: "Version everything", p: "Every rating records the rubric version, the scorer version and the exact document version it was made from. Change any of them and the rating is made again, never edited." },
]

function Tiers({ tiers }: { tiers: { tier: Tier; meaning: string }[] }) {
  return (
    <Chapter id="ratings" eyebrow="The scale" title="What the ratings mean">
      <dl className="tiers">
        {tiers.map((t) => (
          <div key={t.tier}>
            <dt>
              <Verdict tier={t.tier} />
            </dt>
            <dd>{t.meaning}</dd>
          </div>
        ))}
      </dl>
    </Chapter>
  )
}

async function Rubric() {
  await connection() // read at request time, never baked in at build
  let rubric
  try {
    rubric = await getRubric()
  } catch {
    return (
      <>
        <Tiers tiers={TIERS} />
        <Chapter id="questions" eyebrow="The questions" title="Every question we ask">
          <p className="note">The full list is unavailable right now. Try again in a minute.</p>
        </Chapter>
      </>
    )
  }
  return (
    <>
      <Tiers tiers={rubric.tiers} />

      <Chapter id="rules" eyebrow={`Scorer ${rubric.scorer_version}`} title="The rules, in the order the scorer applies them">
        <ol>
          {rubric.rules.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ol>
        <p>
          In short: a red flag is a practice at its broadest. Two of them, or either of the two worst alone, make
          a site Severe. One makes it Extensive. Two medium concerns make it Moderate. A site is Limited only when
          nothing of concern was found and at least four of the six red-flag questions were actually answered;
          otherwise it is Unclear, so a document that says little is never mistaken for a good one.
        </p>
      </Chapter>

      <Chapter id="questions" eyebrow={`Rubric ${rubric.rubric_version}`} title="Every question we ask" wide>
        <p className="note" style={{ marginBottom: 28 }}>
          Each answer leads to the rating next to it. A question the documents don’t address is Not disclosed.
        </p>
        <div className="checks">
          {rubric.categories.map((c) => (
            <section key={c.key} id={c.key}>
              <h3 style={{ marginTop: 0 }}>{c.name}</h3>
              {c.checks.map((k) => (
                <div key={k.check_id} className="check" style={{ marginTop: 16 }}>
                  <p className="q">
                    <span className="id meta mono">{k.check_id}</span>
                    {k.question}
                  </p>
                  <ul className="answers">
                    {k.statuses.map((s) => (
                      <li key={s.status}>
                        <Verdict tier={s.tier} />
                        <span>{s.meaning}</span>
                      </li>
                    ))}
                    <li>
                      <Verdict tier="NOT_DISCLOSED" />
                      <span>The documents don’t address this</span>
                    </li>
                  </ul>
                </div>
              ))}
            </section>
          ))}
        </div>
      </Chapter>
    </>
  )
}

export default function HowWeScore() {
  return (
    <Page
      current="/how-we-score"
      eyebrow="How we score"
      title="Every rating is a sentence you can check."
      lede="We ask the same fixed questions of every privacy policy and terms of service. A model answers and must quote the document. Our code throws out any quote it can’t find, and turns the answers that remain into ratings with rules anyone can read."
    >
      <Chapter id="example" eyebrow="One finding, start to finish" title="From a sentence to a rating">
        <p>
          Line {FIRST_THREAD.line} of {EXCERPT.domain}’s stored privacy policy, version {EXCERPT.version}, fetched{" "}
          {EXCERPT.fetched}:
        </p>
        <p className="quote serif">“{FIRST_THREAD.quote}”</p>
        <p>
          The question <span className="mono">trains_ai_on_user_data</span> asks whether users’ data or content is
          used to train AI models. The model answered <span className="mono">yes</span> and cited that sentence.
          The sentence was found word for word in the stored text and contains one of the question’s evidence
          words, so the answer counts. In the rubric, <span className="mono">yes</span> with no opt-out is a high
          concern, and a high concern rates its category <Verdict tier={FIRST_THREAD.tier} />. That category is
          the site’s worst, so the site’s overall rating is {TIER_WORD[FIRST_THREAD.tier]} too. The quote travels
          with the rating everywhere it is shown.
        </p>
      </Chapter>

      <Chapter id="method" eyebrow="The method" title="Five steps, in code" wide>
        <ol className="steps">
          {STEPS.map((s) => (
            <li key={s.h}>
              <h3>{s.h}</h3>
              <p>{s.p}</p>
            </li>
          ))}
        </ol>
      </Chapter>

      <Suspense fallback={<Tiers tiers={TIERS} />}>
        <Rubric />
      </Suspense>

      <Chapter id="accuracy" eyebrow="Measured, not asserted" title="How accurate it is" wide>
        <ul className="figures-list">
          {MEASUREMENTS.map((m) => (
            <li key={m.figure}>
              <span className={`big${m.miss ? " miss" : ""}`}>{m.figure}</span>
              <span>
                {m.what} <span className="note">Measured {m.when}.</span>
              </span>
            </li>
          ))}
        </ul>
        <p style={{ marginTop: 28 }}>
          Two of those fall short of their targets, and both are published with their method rather than rounded
          up. Not measured yet, and here when it is:
        </p>
        <ul>
          {NOT_YET.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </Chapter>

      <Chapter id="limits" eyebrow="What a rating is not" title="Read it for what it is">
        <p>
          A rating describes what the documents say, as we stored them on the date shown. It is not a judgment of
          a company’s intentions, not a measure of what actually happens to your data, and not legal advice. A
          site that discloses a practice plainly can rate worse than one that says nothing, which is why Not
          disclosed is always shown as its own answer and never counted as good.
        </p>
        <p>
          Some sites block automated visitors, and for those we have no document and no rating until someone
          supplies the policy by hand. A changed document is rated again from scratch; the old rating stays in the
          site’s history.
        </p>
      </Chapter>

      <Chapter id="wrong" eyebrow="If we got something wrong" title="Tell us, and we reread it">
        <p>
          <Link href="/report">Report a problem</Link> with any rating or finding. A team member rereads it against
          the stored document, and if the quote doesn’t support the finding, we withdraw it rather than defend it.
        </p>
      </Chapter>
    </Page>
  )
}
