import Link from "next/link"
import { disputeUrl } from "@/lib/links"

// Not in the design yet: plain until the UX team designs it. The disclaimer
// and correction path are promised in the proposal (risk 8) for every page.
export default function Footer() {
  return (
    <footer className="mx-auto max-w-[1180px] px-5 py-8 text-xs text-[#5a6b7e] sm:px-8">
      <p>
        Imbroglio ratings come from automated analysis of each site&apos;s own privacy policy and terms of
        service. Every quote is checked word for word against the stored document. Ratings describe what the
        documents say, not a company&apos;s intentions, and are not legal advice.
      </p>
      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        <Link className="underline" href="/how-we-score">
          How we score
        </Link>
        <Link className="underline" href="/learn">
          What you can do
        </Link>
        <Link className="underline" href="/about">
          About
        </Link>
        <Link className="underline" href={disputeUrl()}>
          Report a problem
        </Link>
      </p>
    </footer>
  )
}
