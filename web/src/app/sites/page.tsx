import type { Metadata } from "next"
import { Suspense } from "react"
import { BottomBar, Masthead } from "@/components/home/chrome"
import { ratedSites } from "@/components/home/ratedSites"
import Shelves from "@/components/home/Shelves"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/sites.css"

export const metadata: Metadata = {
  title: "Every site · Imbroglio",
  description: "Every site we have rated, worst first, with its score and the answer that takes the most points off.",
}

// Every rated site, on shelves by rating, worst first. The list comes from
// the API (GET /v1/sites) at request time (components/home/ratedSites.ts,
// which the about page counts from too).

async function Head() {
  const sites = await ratedSites()
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
      <main className="page-main" id="main">
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
