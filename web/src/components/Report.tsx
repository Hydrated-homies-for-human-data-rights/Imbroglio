"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import type { CategoryScore, Evidence, Site, WhatYouCanDo } from "@/lib/api"
import { docName, shortDate } from "@/lib/format"
import { disputeUrl } from "@/lib/links"
import { Chevron, DetailCard, RatingMark, ratingOf, ratingStyles } from "./design"
import ShareButton from "./ShareButton"

// Privacy report page from the UX team's design, fed with /v1/sites/{domain}.
const TAGS: Record<Evidence["provenance"], string> = {
  machine: "AI-generated",
  human: "Human-reviewed",
  agreed: "Agreed",
}

export default function Report({ site }: { site: Site }) {
  const card = site.scorecard!
  const headline = ratingOf[card.headline]
  // Which categories are open. Each one opens right under its own row, so
  // the quotes appear where the reader clicked. The worst one starts open to
  // show that a row opens.
  const first = card.categories.find((c) => c.name === card.headline_categories[0]) ?? card.categories[0]
  const [open, setOpen] = useState<Set<string>>(() => new Set(first ? [first.key] : []))
  const allOpen = open.size === card.categories.length
  const toggle = (key: string) =>
    setOpen((was) => {
      const next = new Set(was)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const [showScoring, setShowScoring] = useState(false)
  const router = useRouter()
  const severe = card.headline === "SEVERE"
  const score = card.score ?? null
  const shareText = `${site.domain} is rated ${headline}${score ? `, ${score.value}/100,` : ""} on Imbroglio, with the quotes from its own policy behind it.`

  // A link straight to a category (the extension's "read the quotes on the
  // full report" sends #<category key>) opens that category: on arrival,
  // and again if the hash changes while the page is open. The address bar
  // is the external system here, so the state is set from its callbacks.
  useEffect(() => {
    const open = () => {
      const key = window.location.hash.slice(1)
      const target = key && card.categories.find((c) => c.key === key)
      if (target) {
        setOpen((was) => new Set(was).add(target.key))
        document.getElementById(key)?.scrollIntoView({ block: "start", behavior: "smooth" })
      }
    }
    const soon = setTimeout(open, 0)
    window.addEventListener("hashchange", open)
    return () => {
      clearTimeout(soon)
      window.removeEventListener("hashchange", open)
    }
  }, [card.categories])

  return (
    <main className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 sm:py-14">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#728093]">
        <span>Privacy report</span>
        <span className="h-1 w-1 rounded-full bg-[#aab3be]" />
        <span>Last analyzed {shortDate(card.analyzed_at)}</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h1 className="min-w-0 break-words text-3xl font-bold tracking-[-0.035em] text-[#0f253a] sm:text-[40px]">
          {site.domain}
        </h1>
        <ShareButton path={`/site/${encodeURIComponent(site.domain)}`} text={shareText} />
      </div>

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
                {score && (
                  <>
                    <span className="font-medium text-[#9aa6b3]"> · </span>
                    {/* the score in the rating's own color, larger than the word */}
                    <span className="text-[40px] leading-none tracking-[-0.03em] tabular-nums">{score.value}</span>
                    <span className="text-lg font-semibold opacity-75">/100</span>
                  </>
                )}
              </p>
              <p className={`mt-1 text-sm ${severe ? "text-[#9f4b44]" : "text-[#5a6b7e]"}`}>
                {card.headline === "UNCLEAR"
                  ? "Too few of the key questions were answered to rate this site."
                  : card.headline_categories.join(", ")}
              </p>
            </div>
          </div>
        </div>
        {/* Not in the design yet: plain until the UX team designs it. */}
        <div className="flex items-center rounded-2xl border border-[#dde4ea] bg-white p-6">
          {score ? (
            <div className="w-full">
              <p className="text-sm font-semibold text-[#183149]">How this score adds up</p>
              <ol className="mt-2 grid max-w-xl gap-1 text-[15px] leading-6 text-[#5a6b7e]">
                <li className="grid grid-cols-[3.5rem_1fr] gap-2">
                  <span className="text-right font-semibold tabular-nums text-[#183149]">{score.starts_at}</span>
                  <span>to start</span>
                </li>
                {score.deductions.map((d) => (
                  <li key={d.check_id} className="grid grid-cols-[3.5rem_1fr] gap-2">
                    <span className="text-right font-semibold tabular-nums text-[#a6461d]">−{d.points}</span>
                    <a href={`#${d.category}`} className="underline decoration-[#cbd3db] underline-offset-4 hover:text-[#173b5c]">
                      {d.meaning}
                    </a>
                  </li>
                ))}
                <li className="grid grid-cols-[3.5rem_1fr] gap-2 border-t border-[#e5e9ed] pt-1">
                  <span className="text-right font-bold tabular-nums text-[#183149]">{score.value}</span>
                  <span className="text-[#183149]">
                    out of 100
                    {score.value !== score.unadjusted &&
                      ` (${score.unadjusted} kept at ${score.value}: a ${headline.toLowerCase()} site scores ${score.band[0]} to ${score.band[1]})`}
                  </span>
                </li>
              </ol>
            </div>
          ) : (
            <div>
              <p className="text-sm font-semibold text-[#183149]">How to read this score</p>
              <p className="mt-1 max-w-xl text-[15px] leading-6 text-[#5a6b7e]">
                {card.headline === "UNCLEAR"
                  ? "We only give a score out of 100 when enough of the key questions are answered, so a policy that says little never scores well."
                  : "The documents don’t say enough about any category to give a score out of 100."}
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Not in the design yet: plain until the UX team designs it (proposal risk 8). */}
      <p className="mt-4 max-w-3xl text-xs leading-5 text-[#5a6b7e]">
        Automated analysis of this site&apos;s own documents, last run {shortDate(card.analyzed_at)}. Every quote
        below was checked word for word against the stored text. This describes what the documents say and is
        not legal advice.{" "}
        <Link className="underline" href={disputeUrl(site.domain)}>
          Something wrong? Report a problem
        </Link>
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
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-[#56687c]">Category breakdown</h2>
            {/* Not in the design yet: plain until the UX team designs it. */}
            <p className="mt-1 text-sm text-[#5a6b7e]">Open a category to see the quotes behind its rating.</p>
          </div>
          <button
            onClick={() => setOpen(allOpen ? new Set() : new Set(card.categories.map((c) => c.key)))}
            className="shrink-0 text-sm font-medium text-[#315f91] hover:text-[#173c63]"
          >
            {allOpen ? "Collapse all" : "Expand all"}
          </button>
        </div>
        <div className="overflow-hidden rounded-xl border border-[#d6dde4] bg-white">
          {card.categories.map((category) => {
            const isOpen = open.has(category.key)
            const rating = ratingOf[category.tier]
            return (
              <div key={category.key} id={category.key} className="scroll-mt-6 border-b border-[#e5e9ed] last:border-b-0">
                <button
                  onClick={() => toggle(category.key)}
                  aria-expanded={isOpen}
                  aria-controls={`${category.key}-details`}
                  className={`grid w-full grid-cols-[24px_1fr_auto_22px] items-center gap-3 px-4 py-4 text-left transition hover:bg-[#f7f9fb] sm:px-5 ${
                    isOpen ? "bg-[#f7fafc]" : ""
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
                    <Chevron open={isOpen} />
                  </span>
                </button>
                {isOpen && (
                  <div id={`${category.key}-details`} className="bg-[#f7fafc] px-4 pb-5 pt-1 sm:pl-[56px] sm:pr-5">
                    <CategoryDetails site={site} category={category} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

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
          Each category is rated from limited to severe using verified policy language. The score starts at 100 and
          loses points for each concern the documents raise, and it always stays within its overall rating’s
          range, so the number and the word agree.{" "}
          <Link className="underline" href="/how-we-score">
            See every question, answer and rule
          </Link>
        </aside>
      )}
    </main>
  )
}

// What opens under a category's row: the verified answers with their quotes,
// the site's own page for it, and what you can do.
function CategoryDetails({ site, category }: { site: Site; category: CategoryScore }) {
  // advice for this category, once per topic
  const advice = new Map<string, WhatYouCanDo>()
  for (const f of category.findings) {
    if (f.what_you_can_do) advice.set(f.what_you_can_do.learn_anchor, f.what_you_can_do)
  }
  // the site's own page for this category, when one was found on its site
  const ownPage = (site.links ?? []).find((l) => l.category === category.key)

  return (
    <>
      {category.findings.length > 0 ? (
        <div className="grid gap-3">
          {category.findings.map((f, i) => (
            <DetailCard
              key={`${f.check_id}-${f.document}-${i}`}
              tone={f.concern === "info" ? "grey" : f.exposure > 0 ? "orange" : "green"}
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
            This category is rated{" "}
            <strong className={ratingStyles[ratingOf[category.tier]]}>{ratingOf[category.tier]}</strong>. The documents
            don’t address it.
          </p>
        </div>
      )}

      {/* The site's own page for this, found on its homepage or policy.
          Not in the design yet: plain until the UX team designs it. */}
      {ownPage && (
        <p className="mt-5 rounded-xl border border-[#cfe0d3] bg-[#f1f8f3] px-5 py-4 text-sm text-[#2f5a3d]">
          On {site.domain}:{" "}
          <a className="font-semibold underline" href={ownPage.url} target="_blank" rel="noopener noreferrer">
            {ownPage.text}
          </a>
          <span className="text-[#5f7a66]">
            {" "}
            {ownPage.source === "known"
              ? "(its own settings page, checked by the Imbroglio team)"
              : `(its own page, linked from its ${ownPage.source === "homepage" ? "homepage" : docName(ownPage.source).toLowerCase()})`}
          </span>
        </p>
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
    </>
  )
}
