"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import type { Evidence, Site, WhatYouCanDo } from "@/lib/api"
import { docName, shortDate } from "@/lib/format"
import { disputeUrl } from "@/lib/links"
import { Chevron, DetailCard, RatingMark, ratingOf, ratingStyles } from "./design"

// Privacy report page from the UX team's design, fed with /v1/sites/{domain}.
const TAGS: Record<Evidence["provenance"], string> = {
  machine: "AI-generated",
  human: "Human-reviewed",
  agreed: "Agreed",
}

export default function Report({ site }: { site: Site }) {
  const card = site.scorecard!
  const headline = ratingOf[card.headline]
  const [expanded, setExpanded] = useState(true)
  const [selected, setSelected] = useState(card.headline_categories[0] ?? card.categories[0]?.name)
  const [showScoring, setShowScoring] = useState(false)
  const router = useRouter()
  const current = card.categories.find((c) => c.name === selected)
  const severe = card.headline === "SEVERE"

  // advice for the selected category, once per topic
  const advice = new Map<string, WhatYouCanDo>()
  for (const f of current?.findings ?? []) {
    if (f.what_you_can_do) advice.set(f.what_you_can_do.learn_anchor, f.what_you_can_do)
  }

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 sm:py-14">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#728093]">
        <span>Privacy report</span>
        <span className="h-1 w-1 rounded-full bg-[#aab3be]" />
        <span>Last analyzed {shortDate(card.analyzed_at)}</span>
      </div>
      <h1 className="break-words text-3xl font-bold tracking-[-0.035em] text-[#0f253a] sm:text-[40px]">
        {site.domain}
      </h1>

      <section className="mt-7 grid gap-5 lg:grid-cols-[350px_1fr]">
        {/* The design shows the SEVERE card; other tiers use the same layout on white. */}
        <div
          className={
            severe
              ? "rounded-2xl border border-[#e0aaa5] bg-[#fff4f2] p-6 shadow-[inset_5px_0_0_#c33f34]"
              : "rounded-2xl border border-[#dde4ea] bg-white p-6"
          }
        >
          <div className="flex items-start gap-4">
            <RatingMark rating={headline} />
            <div>
              <p
                className={`text-xs font-semibold uppercase tracking-[0.12em] ${
                  severe ? "text-[#a63b33]" : "text-[#728093]"
                }`}
              >
                Overall rating
              </p>
              <p
                className={`mt-1 text-2xl font-bold tracking-[-0.02em] ${
                  severe ? "text-[#8f2922]" : ratingStyles[headline]
                }`}
              >
                {headline}
              </p>
              <p className={`mt-1 text-sm ${severe ? "text-[#9f4b44]" : "text-[#5a6b7e]"}`}>
                {card.headline_categories.join(", ")}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center rounded-2xl border border-[#dde4ea] bg-white p-6">
          <div>
            <p className="text-sm font-semibold text-[#183149]">How to read this score</p>
            <p className="mt-1 max-w-xl text-[15px] leading-6 text-[#5a6b7e]">
              The overall rating reflects the weakest privacy category, not an average across the report.
            </p>
          </div>
        </div>
      </section>

      {/* Not in the design yet: plain until the UX team designs it (proposal risk 8). */}
      <p className="mt-4 max-w-3xl text-xs leading-5 text-[#5a6b7e]">
        Automated analysis of this site&apos;s own documents, last run {shortDate(card.analyzed_at)}. Every quote
        below was checked word for word against the stored text. This describes what the documents say and is
        not legal advice.{" "}
        <a className="underline" href={disputeUrl(site.domain)} target="_blank" rel="noopener noreferrer">
          Something wrong? Report a problem
        </a>
      </p>

      <div className="mt-5 flex flex-wrap gap-x-2 gap-y-1 text-sm text-[#607186]">
        {site.documents.map((d, i) => (
          <span key={d.type} className="flex gap-x-2">
            {i > 0 && <span>·</span>}
            <a
              href={d.url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-[#cbd3db] underline-offset-4 hover:text-[#173b5c]"
            >
              {d.type === "privacy" ? "Privacy policy" : "Terms of service"}
            </a>
          </span>
        ))}
      </div>

      <section className="mt-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-[#56687c]">Category breakdown</h2>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm font-medium text-[#315f91] hover:text-[#173c63]"
          >
            {expanded ? "Collapse all" : "Expand all"}
          </button>
        </div>
        <div className="overflow-hidden rounded-xl border border-[#d6dde4] bg-white">
          {card.categories.map((category) => {
            const isSelected = selected === category.name
            const rating = ratingOf[category.tier]
            return (
              <button
                key={category.key}
                onClick={() => {
                  setSelected(category.name)
                  setExpanded(true)
                }}
                className={`grid w-full grid-cols-[24px_1fr_auto_22px] items-center gap-3 border-b border-[#e5e9ed] px-4 py-4 text-left transition last:border-b-0 hover:bg-[#f7f9fb] sm:px-5 ${
                  isSelected ? "bg-[#f7fafc]" : ""
                }`}
              >
                <RatingMark rating={rating} />
                <span className="text-[15px] font-medium text-[#193149]">{category.name}</span>
                <span
                  className={`hidden text-xs font-bold uppercase tracking-[0.07em] sm:block ${ratingStyles[rating]}`}
                >
                  {rating}
                </span>
                <span className="text-[#8d9aa8]">
                  <Chevron open={isSelected && expanded} />
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {expanded && current && (
        <section className="mt-8">
          <div className="mb-4 flex items-center gap-2">
            <button onClick={() => setExpanded(false)} className="text-[#4b6074]" aria-label="Collapse category">
              <Chevron open />
            </button>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.1em] text-[#84909d]">Category details</p>
              <h2 className="text-lg font-bold tracking-[-0.01em] text-[#142b41]">{current.name}</h2>
            </div>
          </div>
          {current.findings.length > 0 ? (
            <div className="grid gap-3">
              {current.findings.map((f, i) => (
                <DetailCard
                  key={`${f.check_id}-${f.document}-${i}`}
                  tone={f.exposure > 0 ? "orange" : "green"}
                  title={f.meaning}
                  quotes={f.quotes}
                  source={docName(f.document)}
                  tag={TAGS[f.provenance]}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-[#dfe4ea] bg-white p-6">
              <p className="text-sm leading-6 text-[#5f7082]">
                This category is rated <strong className={ratingStyles[ratingOf[current.tier]]}>{ratingOf[current.tier]}</strong>
                . The documents don’t address it.
              </p>
            </div>
          )}

          {/* Not in the design yet: plain until the UX team designs it. */}
          {[...advice.values()].map((a) => (
            <details key={a.learn_anchor} className="mt-4 text-sm">
              <summary className="cursor-pointer">What can you do? {a.title}</summary>
              <p className="mt-1">{a.why}</p>
              <ul className="mt-1 list-disc pl-5">
                {a.steps.map((s) => (
                  <li key={s.text}>
                    {s.text}{" "}
                    {s.link && (
                      <a className="underline" href={s.link} target="_blank" rel="noopener noreferrer">
                        link
                      </a>
                    )}
                  </li>
                ))}
              </ul>
              <Link className="underline" href={`/learn#${a.learn_anchor}`}>
                More on this
              </Link>
            </details>
          ))}
        </section>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        <button
          onClick={() => router.push(`/site/${encodeURIComponent(site.domain)}/history`)}
          className="rounded-lg border border-[#ccd5de] bg-white px-5 py-2.5 text-sm font-medium text-[#344c63] transition hover:border-[#96a7b7] hover:bg-[#f9fafb]"
        >
          View change history
        </button>
        <button
          onClick={() => setShowScoring(!showScoring)}
          className="rounded-lg border border-[#ccd5de] bg-white px-5 py-2.5 text-sm font-medium text-[#344c63] transition hover:border-[#96a7b7] hover:bg-[#f9fafb]"
        >
          How we score
        </button>
      </div>

      {showScoring && (
        <aside className="mt-4 max-w-2xl rounded-xl border border-[#dbe2e8] bg-white p-5 text-sm leading-6 text-[#5b6d80]">
          Each category is scored from limited to severe using verified policy language. The overall score always
          reflects the highest-risk category.{" "}
          <Link className="underline" href="/how-we-score">
            See every question, answer and rule
          </Link>
        </aside>
      )}
    </main>
  )
}
