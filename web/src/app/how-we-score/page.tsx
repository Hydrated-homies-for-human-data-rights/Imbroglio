import type { Metadata } from "next"
import Link from "next/link"
import { connection } from "next/server"
import { Suspense, cache } from "react"
import { BottomBar, Masthead, Verdict } from "@/components/home/chrome"
import { TIER_WORD } from "@/components/home/data"
import { Reach } from "@/components/home/reach"
import Thread, { type Stop } from "@/components/home/Thread"
import TryRules, { type Preset } from "@/components/score/TryRules"
import { getRubric, getSite, type RubricInfo } from "@/lib/api"
import { signed } from "@/lib/format"
import { answersOf } from "@/lib/tryRules"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/score.css"

export const metadata: Metadata = {
  title: "How we score · Imbroglio",
  description:
    "One sentence followed from a privacy policy to a rating, the scorer's rules to try for yourself, and how accurate it is.",
}

// "How we score" (requirement F5). One real sentence followed down the
// thread through the five steps, then the scorer's rules to try: every
// question and answer comes from the API at request time (GET /v1/rubric),
// so this page can never disagree with the scorer.

const ROUTE: Stop[] = [
  { id: "sheet", side: "bottom" },
  { id: "rail-top", side: "center" },
  { id: "rail-bottom", side: "center" },
]

// The worked example: tiktok.com's U.S. privacy policy as stored, version 996.
// The quote is the verified evidence for its rubric v0.3 AI training answer.
const EX = {
  domain: "tiktok.com",
  title: "U.S. Privacy Policy",
  updated: "July 15, 2026",
  version: 996,
  fetched: "2026-10-28",
  lines: 90,
  chars: "27,176",
  sha: "6f2a…c41e",
  line: 37,
  before: "To review, support, improve, and develop the Services, and ",
  quote:
    "train, test, and improve technology, such as machine learning models and algorithms, including by analyzing how people are using the Services; conducting research; soliciting feedback; monitoring your activity and usage across the devices you use to access the Services; and scanning, analyzing, and reviewing user content, messages, AI interactions, and associated metadata.",
  check: "trains_ai_on_user_data",
  status: "private_content",
  meaning: "Users’ private content or AI conversations are used to train AI models",
  evidence: ["train", "machine learning"],
}

// Measured figures, with when they were measured. Update these with each new
// measurement; docs/evaluation.md has the details behind each one.
// `rubric` is the rubric the figure was measured on, when it depends on one.
const MEASUREMENTS: {
  figure: string
  value: number
  target?: number
  targetLabel?: string
  what: string
  when: string
  rubric?: string
}[] = [
  {
    figure: "99.4%",
    value: 99.4,
    target: 95,
    targetLabel: "target 95%",
    what: "of the 8,407 quotes the model cited across 559 sites were found word for word in the stored document.",
    when: "Nov 2, 2026",
    rubric: "v0.2",
  },
  {
    figure: "78.7%",
    value: 78.7,
    what: "of those quotes also contained one of the question’s evidence words, so they are about the question asked. Only quotes that pass both checks are shown; the rest are kept for review.",
    when: "Nov 2, 2026",
    rubric: "v0.2",
  },
  {
    figure: "88.4%",
    value: 88.4,
    target: 90,
    targetLabel: "target 90%",
    what: "of answers came out the same in all three runs when 50 privacy policies were analyzed three times each. Overall ratings matched in 66% of documents.",
    when: "Oct 30, 2026",
    rubric: "v0.2",
  },
  { figure: "79%", value: 79, what: "of 86 reachable sites from a random sample of 100 had their privacy policy found.", when: "Oct 2026" },
  { figure: "19 of 20", value: 95, what: "sites in the feasibility sample had their privacy policy found and extracted correctly.", when: "Sep 2026" },
  {
    figure: "0.765",
    value: 76.5,
    target: 70,
    targetLabel: "target 0.70",
    what: "macro F1 for the baseline policy text classifier on the OPP-115 benchmark. Not yet used in live ratings.",
    when: "Oct 2026",
  },
]

// one fetch of each per request, however many sections use it
const rubricNow = cache(async () => {
  await connection() // read at request time, never baked in at build
  return getRubric().catch(() => null)
})
const exampleNow = cache(async () => {
  await connection()
  return getSite(EX.domain).catch(() => null)
})

const findCheck = (rubric: RubricInfo, id: string) =>
  rubric.categories.flatMap((c) => c.checks).find((k) => k.check_id === id)

// Stop 2: the question's fixed answers, the chosen one marked.
async function AskedAnswers() {
  const rubric = await rubricNow()
  const check = rubric && findCheck(rubric, EX.check)
  if (!check) return <ChosenOnly />
  return (
    <div className="ex-card">
      <div className="ex-q">
        <span className="mono">{check.check_id}</span>
        <p>{check.question}</p>
      </div>
      <ul className="ex-answers">
        {check.statuses.map((s) => (
          <li key={s.status} className={s.status === EX.status ? "on" : undefined}>
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
  )
}
function ChosenOnly() {
  return (
    <div className="ex-card">
      <div className="ex-q">
        <span className="mono">{EX.check}</span>
        <p>Does the company use users’ data or content to train AI or machine-learning models, and which data?</p>
      </div>
      <ul className="ex-answers">
        <li className="on">
          <Verdict tier="EXTENSIVE" />
          <span>{EX.meaning}</span>
        </li>
      </ul>
    </div>
  )
}

// Stop 5: the site's rating as published today.
async function SiteNow() {
  const site = await exampleNow()
  const card = site?.scorecard
  if (!card) return <SiteFallback />
  const ded = card.score?.deductions ?? []
  return (
    <>
      <div className="ex-card ex-site">
        <span className="ex-domain">{EX.domain}</span>
        <Verdict tier={card.headline} score={card.score?.value} />
        <Link href={`/site/${EX.domain}`}>See the report</Link>
      </div>
      {card.score && ded.length > 0 && (
        <div className="ex-math">
          <p>Its score starts at {card.score.starts_at} and loses points for each concern:</p>
          <ul>
            {ded.map((d) => (
              <li key={d.check_id}>
                <span className="mono">−{d.points}</span>
                {d.plain ?? d.meaning}
              </li>
            ))}
          </ul>
          <p>
            {card.score.unadjusted === card.score.value
              ? `That leaves ${card.score.value}.`
              : `That leaves ${signed(card.score.unadjusted)}, kept inside ${TIER_WORD[card.headline]}’s range of ${card.score.band[0]} to ${card.score.band[1]}: ${card.score.value}.`}
          </p>
        </div>
      )}
    </>
  )
}
function SiteFallback() {
  return (
    <div className="ex-card ex-site">
      <span className="ex-domain">{EX.domain}</span>
      <Verdict tier="EXTENSIVE" />
      <Link href={`/site/${EX.domain}`}>See the report</Link>
    </div>
  )
}

// "Try the rules", and the scorer's exact wording under a fold.
async function Rules() {
  const rubric = await rubricNow()
  if (!rubric?.scoring) return <RulesFallback rubric={rubric} />
  const presets: Preset[] = [{ label: "A policy that says nothing", answers: {} }]
  const site = await exampleNow()
  const fromSite = site?.scorecard ? answersOf(rubric, site.scorecard) : null
  if (fromSite) presets.unshift({ label: `${EX.domain}, as rated`, answers: fromSite })
  const protective: Record<string, string> = {}
  for (const c of rubric.categories)
    for (const k of c.checks) {
      const s = k.statuses.find((x) => x.tier === "LIMITED")
      if (s) protective[k.check_id] = s.status
    }
  presets.push({ label: "Every answer protective", answers: protective })
  return (
    <>
      <TryRules rubric={rubric} presets={presets} />
      <ExactRules rubric={rubric} />
    </>
  )
}

function ExactRules({ rubric }: { rubric: RubricInfo }) {
  return (
    <details className="exact" id="rules">
      <summary>
        The scorer’s rules, word for word{" "}
        <span className="mono">
          scorer {rubric.scorer_version} · rubric {rubric.rubric_version}
        </span>
      </summary>
      <ol>
        {rubric.rules.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ol>
      <dl className="exact-tiers">
        {rubric.tiers.map((t) => (
          <div key={t.tier}>
            <dt>
              <Verdict tier={t.tier} />
            </dt>
            <dd>{t.meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

function RulesFallback({ rubric }: { rubric?: RubricInfo | null }) {
  return (
    <div className="try-off">
      <p>
        Try the rules is unavailable right now. In short: a site starts at 100 and loses 65 points for each severe
        concern, 42 for each high one and 12 for each medium one. Any severe concern or two high ones make it Severe,
        one high concern Extensive, any medium one Moderate. It is Limited only when nothing takes points off and
        enough of the key questions were answered; otherwise it is Unclear, with no score.
      </p>
      {rubric && <ExactRules rubric={rubric} />}
    </div>
  )
}

export default function HowWeScore() {
  return (
    <div className="home page score">
      <Thread route={ROUTE} />
      <Masthead current="/how-we-score" />
      <main className="page-main" id="main">
        <section className="hero" aria-labelledby="hws-h1">
          <div className="page-head">
            <div className="eyebrow mono">How we score</div>
            <h1 id="hws-h1">Every rating is a sentence you can check.</h1>
            <p className="lede">
              We ask the same fourteen questions of every privacy policy and terms of service. A model answers and
              must quote the document. Our code throws out any quote it can’t find, and turns the rest into ratings
              with rules anyone can read, and try.
            </p>
          </div>
          <figure className="sheet">
            <figcaption className="mono">
              <span>
                {EX.domain} · {EX.title}
              </span>
              <span>
                v{EX.version} · stored {EX.fetched}
              </span>
            </figcaption>
            <div className="sheet-lines">
              <span className="ln mono">{EX.line - 1}</span>
              <span className="blank" style={{ width: "82%" }} />
              <span className="ln mono hot">{EX.line}</span>
              <span className="serif">
                {EX.before}
                <mark>{EX.quote}</mark>
              </span>
              <span className="ln mono">{EX.line + 1}</span>
              <span className="blank" style={{ width: "64%" }} />
            </div>
            <i data-thread="sheet" className="sheet-anchor" aria-hidden="true" />
          </figure>
        </section>

        <div className="body">
          <div className="rail" aria-hidden="true">
            <i data-thread="rail-top" style={{ position: "absolute", left: "50%", top: 0 }} />
            <i data-thread="rail-bottom" style={{ position: "absolute", left: "50%", bottom: 0 }} />
          </div>
          <div>
            <p className="eyebrow mono follow">One sentence, start to finish</p>
            <ol className="stops">
              <Reach as="li" className="stop">
                <p className="n mono">01 · Fetched and kept</p>
                <h2>We store the exact text, and every version after it.</h2>
                <p className="say">
                  The document comes from the site itself. Each version is fingerprinted, so a quiet rewrite is caught,
                  dated and rated again from scratch, and the old rating stays in the site’s history.
                </p>
                <dl className="ex-card ex-record mono">
                  <div>
                    <dt>Site</dt>
                    <dd>{EX.domain}</dd>
                  </div>
                  <div>
                    <dt>Document</dt>
                    <dd>
                      {EX.title} (updated {EX.updated})
                    </dd>
                  </div>
                  <div>
                    <dt>Version</dt>
                    <dd>
                      {EX.version}, fetched {EX.fetched}
                    </dd>
                  </div>
                  <div>
                    <dt>Size</dt>
                    <dd>
                      {EX.lines} lines · {EX.chars} characters
                    </dd>
                  </div>
                  <div>
                    <dt>Fingerprint</dt>
                    <dd>sha256 {EX.sha}</dd>
                  </div>
                </dl>
              </Reach>

              <Reach as="li" className="stop">
                <p className="n mono">02 · Asked</p>
                <h2>A model picks one answer from a fixed list, and has to quote.</h2>
                <p className="say">
                  Fourteen questions, the same for every site. The model can’t invent an answer: it chooses one of these
                  and cites the sentence that supports it.
                </p>
                <Suspense fallback={<ChosenOnly />}>
                  <AskedAnswers />
                </Suspense>
              </Reach>

              <Reach as="li" className="stop">
                <p className="n mono">03 · Checked in code</p>
                <h2>The quote has to be there, word for word, and on topic.</h2>
                <p className="say">
                  Whitespace and curly quotes are forgiven. A changed word, a dropped “not”, or a sentence about
                  something else is not.
                </p>
                <ul className="ex-card ex-checks">
                  <li>
                    <span className="ok" aria-label="Passed">
                      ✓
                    </span>
                    <span>
                      Found word for word in version {EX.version}, line {EX.line}.
                    </span>
                  </li>
                  <li>
                    <span className="ok" aria-label="Passed">
                      ✓
                    </span>
                    <span>
                      About the question: it contains the question’s evidence words{" "}
                      {EX.evidence.map((w, i) => (
                        <span key={w}>
                          {i > 0 && " and "}“<mark>{w}</mark>”
                        </span>
                      ))}
                      .
                    </span>
                  </li>
                  <li className="fail">
                    <span className="no" aria-label="Would fail">
                      ✕
                    </span>
                    <span>
                      What would fail: “we do not train models on your content” cited for a yes, or a sentence about
                      cookies cited for this question. Thrown out, never shown, never scored.
                    </span>
                  </li>
                </ul>
              </Reach>

              <Reach as="li" className="stop">
                <p className="n mono">04 · Rated by the rules</p>
                <h2>Plain code turns the answer into a rating.</h2>
                <p className="say">
                  Each answer’s rating is fixed in the rubric ahead of time. A category takes its most concerning answer.
                  No model decides a rating.
                </p>
                <div className="ex-flow">
                  <div className="ex-card">
                    <span>Private content or AI conversations used for training</span>
                    <span className="concern">
                      <Verdict tier="EXTENSIVE" /> high concern
                    </span>
                  </div>
                  <span className="arrow" aria-hidden="true">
                    →
                  </span>
                  <div className="ex-card">
                    <span>AI and model training</span>
                    <Verdict tier="EXTENSIVE" />
                  </div>
                </div>
              </Reach>

              <Reach as="li" className="stop">
                <p className="n mono">05 · The site</p>
                <h2>The site’s rating counts every concern.</h2>
                <p className="say">
                  One high concern makes a site Extensive. The overall rating is never below its worst category and
                  never an average, and the quote travels with it wherever it is shown.
                </p>
                <Suspense fallback={<SiteFallback />}>
                  <SiteNow />
                </Suspense>
              </Reach>
            </ol>
          </div>
        </div>

        <section className="part" id="try" aria-labelledby="try-h">
          <p className="eyebrow mono">The scale</p>
          <h2 id="try-h">From 100, minus what the documents allow. Try it.</h2>
          <p className="part-lede">
            A site starts at 100 and loses 65 points for each severe concern, 42 for each high one and 12 for each
            medium one. The rating sets the range the score stays in, and a site that says too little gets no score at
            all. These are the scorer’s real rules: pick the answer a policy gives to each question and watch what it
            would be rated.
          </p>
          <Suspense fallback={<RulesFallback />}>
            <Rules />
          </Suspense>
        </section>

        <section className="part" id="accuracy" aria-labelledby="acc-h">
          <p className="eyebrow mono">Measured, not asserted</p>
          <h2 id="acc-h">How accurate it is, including where it falls short.</h2>
          <ul className="ledger">
            {MEASUREMENTS.map((m) => {
              const miss = m.target != null && m.value < m.target
              return (
                <li key={m.figure}>
                  <span className={`fig${miss ? " miss" : ""}`}>{m.figure}</span>
                  <span className="what">
                    {m.what}{" "}
                    <span className="when">
                      Measured {m.when}
                      {m.rubric && ` on rubric ${m.rubric}`}.
                    </span>
                  </span>
                  <span className="meter">
                    <span className="bar" aria-hidden="true">
                      <i className={miss ? "miss" : undefined} style={{ width: `${m.value}%` }} />
                      {m.target != null && (
                        <b style={{ left: `${m.target}%` }}>
                          <em className="mono">{m.targetLabel}</em>
                        </b>
                      )}
                    </span>
                    <span className={`res${miss ? " miss" : m.target != null ? " met" : ""}`}>
                      {m.target == null ? "No target set" : miss ? `Short of its ${m.targetLabel}` : `Meets its ${m.targetLabel}`}
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="part-note">
            A figure that falls short is published with its method, not rounded up. Not measured yet: agreement with
            ToS;DR’s human reviewers on individual findings.
          </p>
        </section>

        <section className="part closing" aria-label="What a rating is and isn’t">
          <div>
            <p className="eyebrow mono">What a rating is not</p>
            <p>
              A rating describes what the documents say, as we stored them on the date shown. It is not a judgment of a
              company’s intentions, not a measure of what actually happens to your data, and not legal advice. A site
              that discloses a practice plainly can rate worse than one that says nothing, which is why Not disclosed is
              always its own answer and never counted as good. Sites that block automated visitors have no document and
              no rating until someone supplies the policy by hand.
            </p>
          </div>
          <div>
            <p className="eyebrow mono">If we got something wrong</p>
            <p>
              <Link href="/report">Report a problem</Link> with any rating or finding. A team member rereads it against
              the stored document, and if the quote doesn’t support the finding, we withdraw it rather than defend it
              and work out the rating again.
            </p>
          </div>
        </section>
      </main>
      <BottomBar />
    </div>
  )
}
