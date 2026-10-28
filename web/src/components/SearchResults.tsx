"use client"

import Link from "next/link"
import { useState } from "react"
import type { SearchResult } from "@/lib/api"
import { ago } from "@/lib/format"
import { Chevron, RatingMark, WarningIcon, ratingOf, ratingStyles, type Rating } from "./design"
import RequestForm from "./RequestForm"

// Search results page from the UX team's design, fed with /v1/search.
const CATEGORIES = [
  "Data selling and sharing",
  "Collection scope",
  "Retention and deletion",
  "User rights",
  "Security",
  "AI and model training",
  "Government requests",
]
const RECENT_DAYS = 30

export default function SearchResults({
  searchTerm,
  results: all,
  canRequest,
}: {
  searchTerm: string
  results: SearchResult[]
  canRequest: string | null
}) {
  const [category, setCategory] = useState("All categories")
  const [tier, setTier] = useState("All tiers")
  const [recentOnly, setRecentOnly] = useState(false)
  const now = new Date()
  const recent = (r: SearchResult) =>
    !!r.last_changed && now.getTime() - new Date(r.last_changed).getTime() < RECENT_DAYS * 86_400_000

  const results = all.filter(
    (result) =>
      (!recentOnly || recent(result)) &&
      (tier === "All tiers" || (result.headline && ratingOf[result.headline] === tier)) &&
      (category === "All categories" || result.concerns.includes(category)),
  )

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-7 sm:px-8 sm:py-9">
      <section aria-label="Search filters" className="flex flex-wrap items-center gap-3">
        <span className="mr-1 text-sm font-medium text-[#5d6e80]">Filter</span>
        <label>
          <span className="sr-only">Category</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-10 min-w-[190px] rounded-lg border border-[#ccd5de] bg-white px-4 text-sm text-[#334a60] outline-none focus:border-[#6685a2] focus:ring-4 focus:ring-[#e1e8ee]"
          >
            <option>All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Rating tier</span>
          <select
            value={tier}
            onChange={(event) => setTier(event.target.value)}
            className="h-10 min-w-[140px] rounded-lg border border-[#ccd5de] bg-white px-4 text-sm text-[#334a60] outline-none focus:border-[#6685a2] focus:ring-4 focus:ring-[#e1e8ee]"
          >
            <option>All tiers</option>
            <option>Severe</option>
            <option>Extensive</option>
            <option>Moderate</option>
            <option>Limited</option>
            <option>Unclear</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setRecentOnly(!recentOnly)}
          aria-pressed={recentOnly}
          className={`h-10 rounded-lg border px-5 text-sm font-medium transition ${
            recentOnly
              ? "border-[#245f9e] bg-[#edf5fc] text-[#245f9e]"
              : "border-[#ccd5de] bg-white text-[#41566b] hover:border-[#8fa0b1]"
          }`}
        >
          Recently changed
        </button>
      </section>

      <section className="mt-6 grid gap-3" aria-label={`Results for ${searchTerm}`}>
        {all.length === 0 ? (
          <p className="text-sm">No sites match “{searchTerm}”.</p>
        ) : results.length > 0 ? (
          results.map((result) => {
            const rating: Rating | null = result.headline ? ratingOf[result.headline] : null
            const analyzed = ago(result.analyzed_at, now)
            const changed = recent(result) ? ago(result.last_changed, now) : null
            return (
              <Link
                key={result.domain}
                href={`/site/${encodeURIComponent(result.domain)}`}
                className="group grid w-full grid-cols-[1fr_auto] items-center gap-4 rounded-xl border border-[#d4dbe2] bg-white px-5 py-4 text-left transition hover:border-[#9baaba] hover:shadow-[0_5px_18px_rgba(23,43,61,0.06)] sm:px-6"
              >
                <span className="min-w-0">
                  <span className="block text-lg font-bold tracking-[-0.01em] text-[#122a40]">
                    {result.domain}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-2 text-sm text-[#66778a]">
                    <span>{analyzed ? `Analyzed ${analyzed}` : "Not analyzed yet"}</span>
                    {changed && (
                      <span className="inline-flex items-center gap-1.5 text-[#a16b0f]">
                        <WarningIcon />
                        changed {changed}
                      </span>
                    )}
                  </span>
                </span>
                <span className="flex items-center gap-3 sm:gap-6">
                  {rating && <RatingMark rating={rating} />}
                  <span
                    className={`hidden text-xs font-bold uppercase tracking-[0.07em] sm:block ${
                      ratingStyles[rating ?? "Not disclosed"]
                    }`}
                  >
                    {rating ?? "Not rated"}
                  </span>
                  <span className="text-[#8d9aa8] transition group-hover:translate-x-1 group-hover:text-[#455d73]">
                    <Chevron />
                  </span>
                </span>
              </Link>
            )
          })
        ) : (
          <div className="rounded-xl border border-dashed border-[#c8d1da] bg-white px-6 py-10 text-center">
            <p className="font-semibold text-[#2d455c]">No services match these filters</p>
            <p className="mt-1 text-sm text-[#718092]">Try a different category or rating tier.</p>
          </div>
        )}
      </section>

      <section className="mt-10 border-t border-[#dfe4e9] pt-6">
        <h2 className="text-base font-bold text-[#122a40]">Not finding a service?</h2>
        <p className="mt-1 text-sm text-[#66778a]">
          Submit a domain, or paste a policy URL directly if we could not locate one.
        </p>
        <RequestForm initial={canRequest ?? ""} />
      </section>
    </main>
  )
}
