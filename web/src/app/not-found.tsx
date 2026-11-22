import type { Metadata } from "next"
import Link from "next/link"
import { BottomBar, Masthead } from "@/components/home/chrome"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/about.css"
import "@/components/home/notfound.css"

export const metadata: Metadata = {
  title: "Page not found · Imbroglio",
}

// Any address with no page. (A site report or history for something that
// isn't a web address, or a site we have nothing on, gets
// site/[domain]/not-found.tsx instead.) Laid out like the About
// page's opening, with a search line, since most people who land here were
// after a site's report. The one picture is a thread that comes loose.
export default function NotFound() {
  return (
    <div className="home page about notfound">
      <Masthead />
      <main className="page-main" id="main">
        <section className="hero" aria-labelledby="nf-h1">
          <div className="page-head">
            <div className="eyebrow mono">404 · Page not found</div>
            <h1 id="nf-h1">We lost the thread.</h1>
            <p className="lede">
              There’s no page at this address. The link may have a typo, or the page may have moved. If you were
              looking for a site’s privacy report, search for it here.
            </p>
            <form action="/search" className="search wide" role="search">
              <label className="sr-only" htmlFor="q-404">
                Search a site or service
              </label>
              <input id="q-404" name="q" placeholder="Search a site or service" autoComplete="off" />
              <button type="submit" aria-label="Search">
                ↵
              </button>
            </form>
            <ul className="nf-links">
              <li>
                <Link href="/sites">Every site we’ve rated</Link>
              </li>
              <li>
                <Link href="/how-we-score">How we score</Link>
              </li>
              <li>
                <Link href="/">Back to the front page</Link>
              </li>
            </ul>
          </div>
          <svg className="loose" viewBox="0 0 360 300" role="img" aria-label="A pink thread that comes loose at one end">
            <path
              d="M10 40 C 90 10, 140 120, 80 150 S 40 250, 150 230 S 260 120, 220 90 S 170 70, 200 150 C 220 200, 280 220, 300 190"
              fill="none"
              stroke="var(--pink)"
              strokeWidth="3"
              strokeLinecap="round"
            />
            <path
              d="M300 190 l 18 -10 M300 190 l 20 2 M300 190 l 14 14"
              fill="none"
              stroke="var(--pink)"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <circle cx="10" cy="40" r="5" fill="var(--pin)" />
            <text x="236" y="250" className="serif">
              ends here
            </text>
          </svg>
        </section>
      </main>
      <BottomBar />
    </div>
  )
}
