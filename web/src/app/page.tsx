import Link from "next/link"
import { Suspense } from "react"
import { connection } from "next/server"
import { BottomBar, Masthead, Verdict } from "@/components/home/chrome"
import Knot from "@/components/home/Knot"
import { Reach } from "@/components/home/reach"
import Thread, { type Stop } from "@/components/home/Thread"
import {
  ANALYZED,
  CLAUSES,
  EXCERPT,
  FALLBACK_HEADLINE,
  FIGURES,
  FIRST_THREAD,
  INDEX,
  RECENT,
  RECENT_AS_OF,
  TIER_WORD,
} from "@/components/home/data"
import "@/components/home/home.css"
import { getSite, type Tier } from "@/lib/api"

// The front page: "Pull the thread." One pink line runs from the tangle on
// the opening screen through a real policy, the verdict it earned, how the
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
type IndexData = { rows: IndexRow[]; headline: Tier; analyzed: string; live: boolean }

const STATIC_INDEX: IndexData = { rows: INDEX, headline: FALLBACK_HEADLINE, analyzed: ANALYZED, live: false }

// The live scorecard for the excerpt's site, if the API answers in time.
async function liveIndex(): Promise<IndexData> {
  await connection() // per request, never at build time
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000))
  const site = await Promise.race([getSite(EXCERPT.domain).catch(() => null), timeout])
  const sc = site?.scorecard ?? null
  if (!sc) return STATIC_INDEX
  const rows = INDEX.map((row) => {
    const live = sc.categories.find((c) => c.key === row.key)
    return { ...row, name: live?.name ?? row.name, tier: live?.tier ?? row.tier }
  })
  return { rows, headline: sc.headline, analyzed: sc.analyzed_at.slice(0, 10), live: true }
}

const reportHref = `/site/${EXCERPT.domain}`

// The verdict section's body. Rendered inside Suspense so the page is
// prerendered and only this part waits on the API, with the stored copy as
// the fallback while it loads (or when the API is down).
function IndexBody({ index }: { index: IndexData }) {
  return (
    <>
      <p className="lede">
        <Verdict tier={index.headline} /> overall. Each pin is a line of the stored text.
        {index.live ? "" : " (From our stored copy; the live report has the current ratings.)"}
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
        {EXCERPT.domain} · rubric v0.2 · scorer s2 · analyzed {index.analyzed}
      </p>
    </>
  )
}

async function LiveIndexBody() {
  return <IndexBody index={await liveIndex()} />
}

export default function Home() {
  return (
    <div className="home">
      <Thread route={ROUTE} />

      <Masthead />

      <section className="opening" aria-labelledby="h1">
        <Knot />
        <h1 id="h1">Pull the thread.</h1>
        <p className="sub">What a privacy policy actually says, one sentence at a time.</p>
        <div style={{ marginTop: 32, width: "100%", display: "flex", justifyContent: "center" }}>
          <Search label="Search a site or service" />
        </div>
        <p className="scroll-hint mono">scroll to pull ↓</p>
      </section>

      <section className="band first" aria-label="The first finding">
        <Reach className="first-block">
          <div className="eyebrow mono">{FIRST_THREAD.category}</div>
          <div style={{ marginTop: 10 }}>
            <Verdict tier={FIRST_THREAD.tier} big />
          </div>
          <blockquote className="serif">“{FIRST_THREAD.quote}”</blockquote>
          <div className="meta mono">
            {EXCERPT.domain} · privacy policy · line {FIRST_THREAD.line} of {EXCERPT.lines} · quote verified word for word
          </div>
        </Reach>
        <div className="first-line" data-thread="first" />
      </section>

      <section className="band" aria-labelledby="doc-h">
        <div className="eyebrow mono">The document</div>
        <h2 id="doc-h">Keep scrolling. The thread reaches each clause in turn.</h2>
        <p className="lede">
          This is {EXCERPT.domain}’s own policy, as we stored it. Where the thread arrives, the sentence that
          earned a finding lights up and the finding pulls out beside it.
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
              stored version {EXCERPT.version} · fetched {EXCERPT.fetched} · {EXCERPT.lines} lines · sha256 {EXCERPT.sha256}
            </div>
          </div>
          {CLAUSES.map((c) => (
            <ClauseRow key={c.line} clause={c} />
          ))}
          <div className="doc-foot meta mono">
            the document continues · {EXCERPT.questions} questions asked · {EXCERPT.answered} answered with a verified
            quote · <Link href={reportHref}>full report →</Link>
          </div>
        </div>
        <div className="doc-exit" data-thread="doc-exit" aria-hidden="true" />
      </section>

      <section className="band" aria-labelledby="index-h">
        <div className="eyebrow mono">The verdict</div>
        <h2 id="index-h">Seven threads, one policy</h2>
        <Suspense fallback={<IndexBody index={STATIC_INDEX} />}>
          <LiveIndexBody />
        </Suspense>
      </section>

      <section className="band method" aria-labelledby="method-h">
        <div className="eyebrow mono">How the thread is pulled</div>
        <h2 id="method-h">Three knots, no trust required</h2>
        <div className="method-line" data-thread="method" aria-hidden="true" />
        <div className="stations">
          <Reach className="station">
            <div className="n">1</div>
            <h3>Fetch and keep every version</h3>
            <p>
              The policy and the terms, from the site itself. Each version is hashed and stored, so a quiet rewrite is
              caught and dated.
            </p>
            <div className="artifact doc mono">
              {EXCERPT.domain} · privacy policy
              <span className="meta">
                version {EXCERPT.version} · sha256 {EXCERPT.sha256} · {EXCERPT.fetched}
              </span>
            </div>
          </Reach>
          <Reach className="station">
            <div className="n">2</div>
            <h3>Every answer must quote the document</h3>
            <p>
              Fourteen questions. Each answer carries a quote, and each quote is checked word for word against the
              stored text before it can count. An unverified quote is never shown.
            </p>
            <div className="artifact quote serif">
              “{FIRST_THREAD.quote}”
              <span className="meta mono">found at line {FIRST_THREAD.line} · verified word for word ✓</span>
            </div>
          </Reach>
          <Reach className="station">
            <div className="n">3</div>
            <h3>Plain code turns answers into the rating</h3>
            <p>
              The rubric is public. Verified answers roll up by rules anyone can read. No model decides the grade.
            </p>
            <div className="artifact">
              <Verdict tier={FIRST_THREAD.tier} big />
              <div className="meta mono" style={{ marginTop: 6 }}>
                trains_ai_on_user_data = yes → {TIER_WORD[FIRST_THREAD.tier]} ·{" "}
                <Link href="/how-we-score">the rubric</Link>
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
          Across {FIGURES.sites} sites, the model cited {FIGURES.quotes.toLocaleString("en-US")} quotes.{" "}
          {FIGURES.found} percent were found word for word in the stored document, above the 95 percent target, and{" "}
          {FIGURES.onTopic} percent also contained one of the question’s evidence words; only those are shown. Fifty
          policies analyzed three times each gave the same answer in every run {FIGURES.consistency} percent of the
          time, short of the 90 percent target. Both are published with their method.
        </p>
        <p className="meta mono" style={{ fontSize: 11, marginTop: 12 }}>
          quotes {FIGURES.measured} · consistency {FIGURES.consistencyMeasured} ·{" "}
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
          {RECENT.map((s) => (
            <Reach as="li" key={s.domain}>
              <span className="name">
                <Link href={`/site/${s.domain}`}>{s.domain}</Link>
              </span>
              <span className="why">{s.why}</span>
              <Verdict tier={s.tier} />
              <span className="ref mono meta">{RECENT_AS_OF}</span>
            </Reach>
          ))}
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
      </Link>
    </>
  )
}
