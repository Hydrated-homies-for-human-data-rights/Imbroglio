import Link from "next/link"
import type { Tier } from "@/lib/api"
import { TIER_WORD } from "./data"

// The pink bars and the wordmark shared by the front page and the editorial
// pages (how we score, what you can do, about, report a problem). The report,
// search and history screens keep the UX team's Header and Footer.

export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="Imbroglio home">
      <svg viewBox="380 160 270 670" aria-hidden="true">
        <circle cx="544" cy="260" r="92" fill="#c0392b" />
        <path
          fill="currentColor"
          d="M450 398C478 382 530 378 560 402C588 425 585 465 565 505L492 632C478 658 485 690 510 705C527 715 545 715 560 710L583 795C555 815 525 823 497 822C450 821 410 800 393 760C378 723 385 670 405 630L478 492C492 465 485 448 470 440C460 434 446 432 436 433Z"
        />
      </svg>
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
