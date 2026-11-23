import Link from "next/link"
import RequestForm from "@/components/RequestForm"
import type { SearchHit } from "@/lib/api"
import { Verdict } from "./chrome"

// The search page, "best match first": the closest match opens as a small
// report card with every answer that took points off, and the rest follow
// as a list with the one answer that cost each the most. Fed by /v1/search,
// which sends every deduction (the other lists only send the biggest).

const DOCS: Record<string, string> = {
  "privacy,terms": "Privacy policy and terms",
  privacy: "Privacy policy only",
  terms: "Terms only",
}

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })

// Changed after it was last rated: the rating still comes from the old text.
const changedSince = (hit: SearchHit) =>
  !!hit.last_changed && !!hit.analyzed_at && new Date(hit.last_changed) > new Date(hit.analyzed_at)

// What a site's rating says when no answer took points off.
function plainVerdict(hit: SearchHit): string {
  switch (hit.headline) {
    case "LIMITED":
      return "Nothing we check for took points off."
    case "UNCLEAR":
      return "Too little in the policy to rate. Silence never earns a score."
    case "NOT_DISCLOSED":
      return "The documents don’t address the practices we ask about."
    case null:
      return "We have its documents but haven’t rated them yet."
    default:
      return ""
  }
}

function Meta({ hit }: { hit: SearchHit }) {
  const docs = DOCS[[...hit.documents].sort().join(",")] ?? "No documents"
  return (
    <p className="mono meta">
      {docs}
      {hit.analyzed_at && <> · rated {day(hit.analyzed_at)}</>}
      {changedSince(hit) && hit.last_changed && (
        <span className="changed"> · changed {day(hit.last_changed)}, not read again yet</span>
      )}
    </p>
  )
}

function ScoreBar({ score, band }: { score: number; band?: [number, number] | null }) {
  return (
    <div className="scorebar" role="img" aria-label={`Score ${score} on a scale from 0 to 100`}>
      <span className="track" />
      {band && <span className="range" style={{ left: `${band[0]}%`, width: `${band[1] - band[0]}%` }} />}
      <span className="tick" style={{ left: `${score}%` }} />
      <span className="mono end lo">0</span>
      <span className="mono end hi">100</span>
    </div>
  )
}

function Best({ hit }: { hit: SearchHit }) {
  const href = `/site/${encodeURIComponent(hit.domain)}`
  const took = hit.deductions ?? []
  return (
    <article className="best" aria-labelledby="best-h">
      <div className="best-id">
        <h1 id="best-h">{hit.domain}</h1>
        {hit.headline && <Verdict tier={hit.headline} big score={hit.score} />}
        {hit.score != null && <ScoreBar score={hit.score} band={hit.band} />}
        <Meta hit={hit} />
      </div>
      <div className="best-why">
        <h2>{took.length ? "What took points off" : "What we found"}</h2>
        {took.length ? (
          <ul>
            {took.map((d) => (
              <li key={d.check_id}>
                <span className="mono pts">−{d.points}</span>
                <span className="said">{d.text}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="said">{plainVerdict(hit)}</p>
        )}
        <Link className="cta" href={href}>
          {hit.headline ? "Read the full report, with the quotes" : "See where it stands"}
        </Link>
      </div>
    </article>
  )
}

function Row({ hit }: { hit: SearchHit }) {
  return (
    <li>
      <Link href={`/site/${encodeURIComponent(hit.domain)}`}>
        <span className="d">{hit.domain}</span>
        <span className="said">{hit.reason ?? plainVerdict(hit)}</span>
        <span className="v">
          {hit.headline ? <Verdict tier={hit.headline} score={hit.score} /> : <span className="mono">not rated</span>}
        </span>
      </Link>
    </li>
  )
}

export default function SearchBest({
  query,
  results,
  canRequest,
}: {
  query: string
  results: SearchHit[]
  canRequest: string | null
}) {
  const [best, ...rest] = results
  return (
    <>
      {best ? (
        <>
          <p className="mono eyebrow">Closest match for “{query}”</p>
          <Best hit={best} />
        </>
      ) : (
        <div className="none">
          <p className="mono eyebrow">Search</p>
          <h1>Nothing we’ve seen matches “{query}”.</h1>
        </div>
      )}

      {rest.length > 0 && (
        <section className="also" aria-labelledby="also-h">
          <h2 id="also-h">Also matching</h2>
          <ul>
            {rest.map((hit) => (
              <Row key={hit.domain} hit={hit} />
            ))}
          </ul>
        </section>
      )}

      <section className="ask" aria-labelledby="ask-h">
        <div>
          <h2 id="ask-h">{best ? "Not what you meant?" : "Want us to rate it?"}</h2>
          <p>
            Type the site’s address and we’ll read its policy now. It takes about half a minute. If we can’t find the
            policy, paste its link instead. Or <Link href="/sites">browse every site</Link>.
          </p>
        </div>
        <div className="ask-form">
          <RequestForm initial={canRequest ?? ""} />
        </div>
      </section>
    </>
  )
}
