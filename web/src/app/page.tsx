import Link from "next/link"
import { Suspense, cache } from "react"
import { connection } from "next/server"
import { BottomBar, Masthead, Verdict } from "@/components/home/chrome"
import Knot from "@/components/home/Knot"
import { Reach } from "@/components/home/reach"
import Thread, { type Stop } from "@/components/home/Thread"
import {
  ANALYZED,
  CATEGORY_ABOUT,
  CLAUSES,
  EXCERPT,
  FALLBACK_HEADLINE,
  FIGURES,
  FIRST_THREAD,
  INDEX,
  RECENT,
  RECENT_AS_OF,
  showable,
  TIER_SHORT,
  TIER_WORD,
} from "@/components/home/data"
import "@/components/home/home.css"
import { getRecent, getSite, type Tier } from "@/lib/api"

// The front page: "Know what you agreed to." The opening screen says what
// Imbroglio is and shows one real finding. One pink line runs from the tangle
// on the opening screen through a real policy, the verdict it earned, how the
// verdict was reached, the sites rated most recently, and back to a search
// box. Scrolling draws the line (components/home/Thread.tsx). Everything on
// the page is real: the excerpt is tiktok.com's stored policy and the
// verdicts are the live ones, with components/home/data.ts as the fallback.

// Where the thread goes, in order, through elements marked data-thread.
// It leaves the knot on the right so it never crosses the headline, drops to
// the first finding's line, runs along it to the left gutter, and goes on to
// the document. Vertical runs sit in the gutter either side of every band,
// clear of the text; the one through the document is its own rail, and the
// thread leaves it below the sheet rather than straight down into the next
// heading.
const ROUTE: Stop[] = [
  { id: "knot", side: "right" },
  { id: "first", side: "left" },
  { id: "doc-top", side: "center" },
  { id: "doc-bottom", side: "center" },
  { id: "doc-exit", side: "left" },
  { id: "index-top", side: "center" },
  { id: "index-bottom", side: "center" },
  { id: "method", side: "left" },
  { id: "method", side: "right" },
  { id: "recent-top", side: "center" },
  { id: "recent-bottom", side: "center" },
  { id: "close-l", side: "center" },
  { id: "close-r", side: "center" },
]

function Search({ wide = false, label }: { wide?: boolean; label: string }) {
  return (
    <form action="/search" className={`search${wide ? " wide" : ""}`} role="search">
      <label className="sr-only" htmlFor={wide ? "q-close" : "q"}>
        {label}
      </label>
      <input id={wide ? "q-close" : "q"} name="q" placeholder="Search a site or service" autoComplete="off" />
      <button type="submit" aria-label="Search">
        ↵
      </button>
      {wide && (
        <>
          <i data-thread="close-l" style={{ position: "absolute", left: 0, bottom: 0 }} />
          <i data-thread="close-r" style={{ position: "absolute", right: 0, bottom: 0 }} />
        </>
      )}
    </form>
  )
}

type IndexRow = (typeof INDEX)[number]
type IndexData = { rows: IndexRow[]; headline: Tier; score: number | null; analyzed: string; live: boolean }

const STATIC_INDEX: IndexData = {
  rows: INDEX,
  headline: FALLBACK_HEADLINE,
  score: null,
  analyzed: ANALYZED,
  live: false,
}

// The excerpt site's live report, if the API answers in time: one fetch per
// request, shared by the opening card's score and the ratings list.
const liveSite = cache(async () => {
  await connection() // per request, never at build time
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000))
  return Promise.race([getSite(EXCERPT.domain).catch(() => null), timeout])
})

// The live scorecard for the excerpt's site.
async function liveIndex(): Promise<IndexData> {
  const site = await liveSite()
  const sc = site?.scorecard ?? null
  if (!sc) return STATIC_INDEX
  const rows = INDEX.map((row) => {
    const live = sc.categories.find((c) => c.key === row.key)
    return { ...row, name: live?.name ?? row.name, tier: live?.tier ?? row.tier }
  })
  return { rows, headline: sc.headline, score: sc.score?.value ?? null, analyzed: sc.analyzed_at.slice(0, 10), live: true }
}

const reportHref = `/site/${EXCERPT.domain}`

// The verdict section's body. Rendered inside Suspense so the page is
// prerendered and only this part waits on the API, with the stored copy as
// the fallback while it loads (or when the API is down).
function IndexBody({ index }: { index: IndexData }) {
  return (
    <>
      <p className="lede">
        <Verdict tier={index.headline} score={index.score} /> overall. Each category links to the sentence in the
        policy it’s based on.
        {index.live ? "" : " (From our saved copy; the full report has the current ratings.)"}
      </p>
      <ol className="spine-list">
        <span className="rail" aria-hidden="true">
          <i data-thread="index-top" style={{ position: "absolute", top: 0 }} />
          <i data-thread="index-bottom" style={{ position: "absolute", bottom: 0 }} />
        </span>
        {index.rows.map((row) => (
          <Reach as="li" key={row.key}>
            <span className="name">
              <Link href={`${reportHref}#${row.key}`}>{row.name}</Link>
            </span>
            <span className="why">{row.why}</span>
            <Verdict tier={row.tier} />
            <span className="ref mono meta">
              <Link href={`${reportHref}#${row.key}`}>line {row.line} ↑</Link>
            </span>
          </Reach>
        ))}
      </ol>
      <p className="meta mono after-list">
        {EXCERPT.domain} · analyzed {index.analyzed} · <Link href="/how-we-score">how we score</Link>
      </p>
    </>
  )
}

async function LiveIndexBody() {
  return <IndexBody index={await liveIndex()} />
}

// The site's overall score on the opening card, once the live report answers.
async function HeroScore() {
  const score = (await liveSite())?.scorecard?.score?.value
  return score == null ? null : <span className="finding-score mono">{score}/100 overall</span>
}

type RecentRow = { domain: string; tier: Tier; why: string; score: number | null; when: string }

const STATIC_RECENT: RecentRow[] = RECENT.map((s) => ({ ...s, score: null, when: RECENT_AS_OF }))

// The latest sites through the pipeline, from the API (GET /v1/recent), with
// the hand-kept list as the fallback while it loads or when it is down. The
// same front-page gate (showable) applies to both.
async function liveRecent(): Promise<RecentRow[]> {
  await connection()
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000))
  const got = await Promise.race([getRecent(25).catch(() => null), timeout])
  const rows = (got?.sites ?? [])
    .filter((s) => s.headline && showable(s.domain))
    .slice(0, 9)
    .map((s) => ({
      domain: s.domain,
      tier: s.headline as Tier,
      why:
        (s.reason && s.reason.charAt(0).toLowerCase() + s.reason.slice(1).replace(/\.$/, "")) ??
        (s.headline === "UNCLEAR"
          ? "too few of the key questions answered"
          : s.concerns.length
            ? s.concerns.join(", ").toLowerCase()
            : "no points taken off"),
      score: s.score ?? null,
      when: (s.analyzed_at ?? "").slice(0, 10),
    }))
  return rows.length ? rows : STATIC_RECENT
}

function RecentRows({ rows }: { rows: RecentRow[] }) {
  return (
    <>
      {rows.map((s) => (
        <Reach as="li" key={s.domain}>
          <span className="name">
            <Link href={`/site/${s.domain}`}>{s.domain}</Link>
          </span>
          <span className="why">{s.why}</span>
          <Verdict tier={s.tier} score={s.score} />
          <span className="ref mono meta">{s.when}</span>
        </Reach>
      ))}
    </>
  )
}

async function LiveRecentRows() {
  return <RecentRows rows={await liveRecent()} />
}

export default function Home() {
  return (
    <div className="home">
      <Thread route={ROUTE} />

      <Masthead />

      <section className="opening" aria-labelledby="h1">
        <Knot />
        <p className="kicker mono">Imbroglio · privacy policies, read for you</p>
        <h1 id="h1">Know what you agreed to.</h1>
        <p className="sub">
          Imbroglio reads the privacy policies and terms of the sites you use, and tells you in plain words what they let
          a company do with your data. Every finding quotes the policy.
        </p>
        <div className="opening-search">
          <Search label="Search a site or service" />
        </div>
        <Link href={`${reportHref}#${FIRST_THREAD.key}`} className="finding-card">
          <span className="finding-head">
            <span>
              <span className="finding-site">{EXCERPT.domain}</span>
              <Suspense fallback={null}>
                <HeroScore />
              </Suspense>
              <span className="finding-cat mono">{FIRST_THREAD.category}</span>
            </span>
            <Verdict tier={FIRST_THREAD.tier} />
          </span>
          <span className="finding-quote serif">“{FIRST_THREAD.quote}”</span>
          <span className="finding-meta mono">
            {FIRST_THREAD.why} · privacy policy, line {FIRST_THREAD.line} · verified word for word · full report →
          </span>
        </Link>
      </section>

      {/* The thread leaves the knot, comes down past the finding and runs along this line to the left gutter. */}
      <section className="band first" aria-hidden="true">
        <div className="first-line" data-thread="first" />
      </section>

      <section className="band" aria-labelledby="doc-h">
        <div className="eyebrow mono">A real policy</div>
        <h2 id="doc-h">Read along with us.</h2>
        <p className="lede">
          This is {EXCERPT.domain}’s actual privacy policy. As you scroll, the sentences behind each rating light up,
          and the rating appears beside them, with what it means.
        </p>
        <div className="doc-grid">
          <div className="doc-sheet" aria-hidden="true" />
          <div className="doc-rail" aria-hidden="true">
            <i data-thread="doc-top" style={{ top: -22 }} />
            <i data-thread="doc-bottom" style={{ bottom: 0 }} />
          </div>
          <div className="doc-head">
            <div className="meta mono" style={{ letterSpacing: "0.25em", textTransform: "uppercase", color: "var(--muted)" }}>
              {EXCERPT.title} · {EXCERPT.domain} · last updated {EXCERPT.updated}
            </div>
            <div className="meta mono">
              version {EXCERPT.version} · saved {EXCERPT.fetched} · {EXCERPT.lines} lines
            </div>
          </div>
          {CLAUSES.map((c) => (
            <ClauseRow key={c.line} clause={c} />
          ))}
          <div className="doc-foot meta mono">
            the policy continues · {EXCERPT.questions} questions asked · {EXCERPT.answered} answered with a quote we
            checked · <Link href={reportHref}>full report →</Link>
          </div>
        </div>
        <div className="doc-exit" data-thread="doc-exit" aria-hidden="true" />
      </section>

      <section className="band" aria-labelledby="index-h">
        <div className="eyebrow mono">The ratings</div>
        <h2 id="index-h">Seven categories, one policy</h2>
        <Suspense fallback={<IndexBody index={STATIC_INDEX} />}>
          <LiveIndexBody />
        </Suspense>
      </section>

      <section className="band method" aria-labelledby="method-h">
        <div className="eyebrow mono">How it works</div>
        <h2 id="method-h">Three steps you can check yourself</h2>
        <div className="method-line" data-thread="method" aria-hidden="true" />
        <div className="stations">
          <Reach className="station">
            <div className="n">1</div>
            <h3>We save the policy, every version</h3>
            <p>
              We copy the privacy policy and terms straight from the site and keep every version, so if a company
              quietly changes them, we notice and note the date.
            </p>
            <div className="artifact doc mono">
              {EXCERPT.domain} · privacy policy
              <span className="meta">
                version {EXCERPT.version} · saved {EXCERPT.fetched}
              </span>
            </div>
          </Reach>
          <Reach className="station">
            <div className="n">2</div>
            <h3>An AI answers questions, quoting the policy</h3>
            <p>
              It answers {EXCERPT.questions} questions about the policy, and every answer has to point to the exact
              sentence it’s based on. Our code checks that sentence is really there, word for word. If it isn’t, the
              answer is thrown out.
            </p>
            <div className="artifact quote serif">
              “{FIRST_THREAD.quote}”
              <span className="meta mono">line {FIRST_THREAD.line} of the policy · checked word for word ✓</span>
            </div>
          </Reach>
          <Reach className="station">
            <div className="n">3</div>
            <h3>Published rules turn the answers into a rating</h3>
            <p>
              Rules anyone can read turn the answers into a rating and a score out of 100. The AI never decides the
              rating.
            </p>
            <div className="artifact">
              <Verdict tier={FIRST_THREAD.tier} big />
              <div className="meta mono" style={{ marginTop: 6 }}>
                {FIRST_THREAD.why.charAt(0).toUpperCase() + FIRST_THREAD.why.slice(1)} → {TIER_WORD[FIRST_THREAD.tier]} ·{" "}
                <Link href="/how-we-score">see every rule</Link>
              </div>
            </div>
          </Reach>
        </div>
      </section>

      <section className="band figures" aria-labelledby="fig-h">
        <div className="eyebrow mono" id="fig-h">
          Figures
        </div>
        <p>
          Across {FIGURES.sites} sites, the AI cited {FIGURES.quotes.toLocaleString("en-US")} quotes.{" "}
          {FIGURES.found} percent were really in the policy, word for word, above our 95 percent target, and{" "}
          {FIGURES.onTopic} percent were also clearly about the question they answered. Only those are shown. When we
          analyzed 50 policies three times each, the answers matched every time {FIGURES.consistency} percent of the
          time, just short of our 90 percent target. Both numbers are published with how we measured them.
        </p>
        <p className="meta mono" style={{ fontSize: 11, marginTop: 12 }}>
          quotes measured {FIGURES.measured} · consistency measured {FIGURES.consistencyMeasured} ·{" "}
          <Link href="/how-we-score">how we score</Link>
        </p>
      </section>

      <section className="band" id="recent" aria-labelledby="recent-h">
        <div className="eyebrow mono">Most recently rated</div>
        <h2 id="recent-h">The latest sites through the pipeline</h2>
        <p className="lede">Every row opens the report with the quotes behind it.</p>
        <ol className="spine-list">
          <span className="rail" aria-hidden="true">
            <i data-thread="recent-top" style={{ position: "absolute", top: 0 }} />
            <i data-thread="recent-bottom" style={{ position: "absolute", bottom: 0 }} />
          </span>
          <Suspense fallback={<RecentRows rows={STATIC_RECENT} />}>
            <LiveRecentRows />
          </Suspense>
        </ol>
        <p className="spine-more">
          <Link href="/search?q=">All {FIGURES.sites} sites, by name or rating →</Link>
        </p>
      </section>

      <section className="band close" aria-labelledby="close-h">
        <h2 id="close-h">Pull another thread.</h2>
        <Search wide label="Search a site or service" />
      </section>

      <BottomBar />
    </div>
  )
}

function ClauseRow({ clause }: { clause: (typeof CLAUSES)[number] }) {
  const quote = clause.text.slice(0, clause.quoteChars)
  const rest = clause.text.slice(clause.quoteChars)
  return (
    <>
      <Reach className="clause">
        <span className="num meta mono">{clause.line}</span>
        <p className="serif">
          <span className="tint">{quote}</span>
          {rest}
        </p>
        <span className="tie" aria-hidden="true" />
      </Reach>
      <Link
        href={`${reportHref}#${clause.key}`}
        className="pin-tag"
        aria-label={`${clause.category}: ${TIER_WORD[clause.tier]}, line ${clause.line}`}
      >
        <span className="cat mono">{clause.category}</span>
        <Verdict tier={clause.tier} />
        <span className="note mono">
          line {clause.line} · {clause.note}
        </span>
        <span className="about">
          <span>{CATEGORY_ABOUT[clause.key]}</span>
          <span>
            <b>{TIER_WORD[clause.tier]}:</b> {TIER_SHORT[clause.tier]}
          </span>
        </span>
      </Link>
    </>
  )
}
