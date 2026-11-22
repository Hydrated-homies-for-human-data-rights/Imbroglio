import type { Metadata } from "next"
import { Suspense } from "react"
import { BottomBar, Masthead } from "@/components/home/chrome"
import ReportForm, { type Pickable } from "@/components/home/ReportForm"
import { getSite, type Evidence, type Scorecard, type Tier } from "@/lib/api"
import { cleanDomain, docName } from "@/lib/format"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/report.css"

export const metadata: Metadata = {
  title: "Report a problem · Imbroglio",
  description: "Tell us a rating, finding or quote on imbroglio.io is wrong. A team member rereads it against the stored document.",
}

// The published correction path (proposal risk 8). Every report is stored
// for the team to reread against the stored document: see the API's
// POST /v1/reports and the `reports` CLI command. Opened from a site's
// report, the page lists that site's findings so the reader can point at
// the one that's wrong.
type Params = Promise<Record<string, string | string[] | undefined>>

// The rating an answer leads to, from its concern (rubric v0.3 on).
const TIER_OF: Record<string, Tier> = { severe: "SEVERE", high: "EXTENSIVE", medium: "MODERATE", info: "INFO" }
const ORDER: Tier[] = ["SEVERE", "EXTENSIVE", "MODERATE", "INFO", "LIMITED"]

function pickable(card: Scorecard): Pickable[] {
  const out: Pickable[] = []
  for (const c of card.categories)
    for (const f of c.findings as Evidence[]) {
      if (f.status === "not_disclosed" || !f.quotes.length) continue
      out.push({
        key: `${f.check_id}:${f.document}`,
        check_id: f.check_id,
        document: f.document,
        docName: `${docName(f.document)} · ${c.name}`,
        plain: f.plain ?? f.meaning,
        tier: (f.concern && TIER_OF[f.concern]) || "LIMITED",
        quote: f.quotes[0],
      })
    }
  return out.sort((a, b) => ORDER.indexOf(a.tier) - ORDER.indexOf(b.tier))
}

function Head({ site, pointing }: { site: string; pointing: boolean }) {
  return (
    <div className="page-head">
      <div className="eyebrow mono">If we got something wrong</div>
      <h1>{pointing ? "Point at the sentence." : "Report a problem."}</h1>
      <p className="lede">
        {pointing
          ? `Every finding on ${site} rests on a quote from its stored documents. Pick the one that’s wrong and tell us why. A person rereads it against the stored copy, and if the quote doesn’t hold, the finding is withdrawn and the rating worked out again.`
          : "A rating, a finding, a quote, a site we read wrong. A team member rereads it against the stored document, and if the quote doesn’t support the finding, we withdraw it and work out the rating again."}
      </p>
    </div>
  )
}

// The site comes from the query string, which is only known per request, so
// it is read inside Suspense and the rest of the page is prerendered.
async function Prefilled({ searchParams }: { searchParams: Params }) {
  const sp = await searchParams
  const raw = typeof sp.site === "string" ? sp.site.slice(0, 253) : ""
  // only a well-formed domain is looked up (a read-only API call); anything
  // else just fills in the form, which the server action validates again
  const clean = raw ? cleanDomain(raw) : null
  const site = clean ?? raw.trim()
  const card = clean ? await getSite(clean).then((s) => s.scorecard).catch(() => null) : null
  const findings = card ? pickable(card) : []
  const want = typeof sp.finding === "string" ? sp.finding.slice(0, 80) : ""
  const initial = findings.find((f) => f.key === want || f.check_id === want)?.key ?? ""
  return (
    <>
      <Head site={site} pointing={findings.length > 0} />
      <section className="rp-body">
        <ReportForm site={site} findings={findings} initial={initial} />
      </section>
    </>
  )
}

const NEXT = [
  ["It reaches a person", "Every report is read by someone on the team. Nothing from this form is shown on the site."],
  ["We reread the stored copy", "The exact version of the document the rating was made from, not today’s page."],
  ["The quote holds, or it goes", "A finding whose quote doesn’t support it is withdrawn, and the rating is worked out again from what remains."],
  ["We tell you", "If you left an address, we write back with what we found either way."],
]

export default function ReportPage({ searchParams }: { searchParams: Params }) {
  return (
    <div className="home page rp">
      <Masthead current="/report" />
      <main className="page-main" id="main">
        <Suspense
          fallback={
            <>
              <Head site="" pointing={false} />
              <section className="rp-body">
                <ReportForm />
              </section>
            </>
          }
        >
          <Prefilled searchParams={searchParams} />
        </Suspense>

        <section className="rp-next" aria-labelledby="rp-next-h">
          <h2 id="rp-next-h" className="eyebrow mono">
            What happens next
          </h2>
          <ol>
            {NEXT.map(([h, p]) => (
              <li key={h}>
                <b>{h}</b>
                <span>{p}</span>
              </li>
            ))}
          </ol>
        </section>
      </main>
      <BottomBar />
    </div>
  )
}
