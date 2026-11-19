import type { Metadata } from "next"
import { connection } from "next/server"
import { Suspense } from "react"
import { BottomBar, Masthead } from "@/components/home/chrome"
import { showable } from "@/components/home/data"
import Shelves, { type ShelfSite } from "@/components/home/Shelves"
import { getSites, type Tier } from "@/lib/api"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/sites.css"

export const metadata: Metadata = {
  title: "Every site · Imbroglio",
  description: "Every site we have rated, worst first, with its score and the answer that takes the most points off.",
}

// Every rated site, on shelves by rating, worst first. The list comes from
// the API (GET /v1/sites) at request time; the same front-page gate
// (showable) keeps the same sites off this page.

const fallbackReason = (tier: Tier) =>
  tier === "UNCLEAR"
    ? "Too few of the key questions answered"
    : tier === "NOT_DISCLOSED"
      ? "The documents don’t say"
      : "Nothing takes points off"

async function load(): Promise<ShelfSite[] | null> {
  await connection() // read at request time, never baked in at build
  try {
    const { sites } = await getSites()
    return sites
      .filter((s) => s.headline && s.headline !== "INFO" && showable(s.domain))
      .map((s) => ({
        domain: s.domain,
        tier: s.headline as Tier,
        score: s.score ?? null,
        reason: s.reason ?? fallbackReason(s.headline as Tier),
      }))
  } catch {
    return null
  }
}

async function Head() {
  const sites = await load()
  return (
    <>
      <section className="sites-head">
        <div>
          <div className="eyebrow mono">Every site · worst first</div>
          <h1>{sites ? `${sites.length} sites, sorted by what they take.` : "Every site we’ve rated."}</h1>
        </div>
        {!sites && <p className="note">The list is unavailable right now. Try again in a minute.</p>}
      </section>
      {sites && <Shelves sites={sites} />}
    </>
  )
}

export default function SitesPage() {
  return (
    <div className="home page sites">
      <Masthead current="/sites" />
      <main className="page-main">
        <Suspense
          fallback={
            <section className="sites-head">
              <div>
                <div className="eyebrow mono">Every site · worst first</div>
                <h1>Every site we’ve rated.</h1>
              </div>
            </section>
          }
        >
          <Head />
        </Suspense>
      </main>
      <BottomBar />
    </div>
  )
}
