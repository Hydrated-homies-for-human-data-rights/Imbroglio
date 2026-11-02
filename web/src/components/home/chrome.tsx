import Link from "next/link"
import LogoGlyph from "@/components/LogoGlyph"
import type { Tier } from "@/lib/api"
import { TIER_WORD } from "./data"

// The pink bars and the wordmark shared by the front page and the editorial
// pages (how we score, what you can do, about, report a problem). The report,
// search and history screens keep the UX team's Header and Footer.

export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="Imbroglio home">
      <LogoGlyph />
      mbroglio<b>.</b>
    </Link>
  )
}

export function Verdict({ tier, big = false }: { tier: Tier; big?: boolean }) {
  return (
    <span className={`verdict t-${tier}${big ? " big" : ""}`}>
      <i className="mark" aria-hidden="true" />
      {TIER_WORD[tier]}
    </span>
  )
}

const NAV = [
  { href: "/how-we-score", label: "How we score" },
  { href: "/learn", label: "What you can do" },
  { href: "/#recent", label: "Recently rated" },
  { href: "/about", label: "About" },
]

export function Masthead({ current }: { current?: string }) {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <Wordmark />
        <nav aria-label="Primary">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={n.href === current ? "page" : undefined}>
              {n.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  )
}

export function BottomBar() {
  return (
    <footer className="bottombar">
      <div className="bottombar-inner">
        <div>
          <Wordmark />
        </div>
        <div>
          <p>
            Imbroglio ratings come from automated analysis of each site’s own privacy policy and terms of service.
            Every quote is checked word for word against the stored document. Ratings describe what the documents
            say, not a company’s intentions, and are not legal advice.
          </p>
          <div className="links">
            <Link href="/how-we-score">How we score</Link>
            <Link href="/learn">What you can do</Link>
            <Link href="/about">About</Link>
            <Link href="/report">Report a problem</Link>
          </div>
        </div>
      </div>
    </footer>
  )
}
