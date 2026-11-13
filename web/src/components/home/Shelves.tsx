"use client"

import Link from "next/link"
import { useState } from "react"
import type { Tier } from "@/lib/api"
import { TIER_WORD } from "./data"

// The every-site page's shelves: one per rating, worst first, each listing
// its sites lowest score first. A shelf shows its first dozen until opened;
// a search opens every shelf and filters them all at once. The whole list
// (a few hundred rows) comes from the server in one go, so filtering here
// needs no round trip.

export type ShelfSite = { domain: string; tier: Tier; score: number | null; reason: string }

const ORDER: Tier[] = ["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED", "UNCLEAR", "NOT_DISCLOSED"]
const CAP = 12

const MEANING: Partial<Record<Tier, string>> = {
  SEVERE: "Two or more red flags, or one of the two worst alone: selling your data, or no way to delete it.",
  EXTENSIVE: "One red flag: a practice at its broadest, like training AI on what you post.",
  MODERATE: "Two or more medium concerns, such as sharing for advertising or keeping data open-endedly.",
  LIMITED: "Nothing of concern found, with enough of the key questions answered to say so.",
  UNCLEAR: "Nothing of concern found, but too little answered to call it limited. Silence isn’t read as good.",
  NOT_DISCLOSED: "The documents don’t address the practices we ask about.",
}

const clean = (q: string) =>
  q.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "")

// lowest score first; the unscored sit after the scored, then by name
const order = (a: ShelfSite, b: ShelfSite) =>
  (a.score ?? 101) - (b.score ?? 101) || a.domain.localeCompare(b.domain)

export default function Shelves({ sites }: { sites: ShelfSite[] }) {
  const [q, setQ] = useState("")
  const [open, setOpen] = useState<Partial<Record<Tier, boolean>>>({})
  const needle = clean(q)
  const matched = needle ? sites.filter((s) => s.domain.includes(needle)) : sites

  const shelves = ORDER.map((tier) => ({ tier, items: matched.filter((s) => s.tier === tier).sort(order) })).filter(
    (g) => g.items.length > 0,
  )

  return (
    <>
      <div className="sites-find">
        <input
          className="sites-search"
          type="search"
          placeholder="Find a site"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Find a rated site"
          aria-controls="shelves"
        />
        <p className="mono sites-count" aria-live="polite">
          {needle
            ? `${matched.length} match${matched.length === 1 ? "" : "es"}`
            : "type to filter every shelf at once"}
        </p>
      </div>

      <div id="shelves">
        {shelves.map(({ tier, items }) => {
          const cap = open[tier] || needle ? items.length : CAP
          const unscored = tier === "UNCLEAR" || tier === "NOT_DISCLOSED"
          return (
            <section className="shelf" key={tier} aria-labelledby={`shelf-${tier}`}>
              <div className="shelf-head">
                <h2 id={`shelf-${tier}`}>
                  <span className={`verdict big t-${tier}`}>
                    <i className="mark" aria-hidden="true" />
                    {TIER_WORD[tier]}
                  </span>
                </h2>
                <p className="mono shelf-n">
                  {items.length} site{items.length === 1 ? "" : "s"}
                  {unscored ? " · no score" : ""}
                </p>
                <p className="shelf-meaning">{MEANING[tier]}</p>
              </div>
              <div>
                <ul className="tiles">
                  {items.slice(0, cap).map((s) => (
                    <li key={s.domain}>
                      <Link className="tile" href={`/site/${encodeURIComponent(s.domain)}`}>
                        <span className="d">{s.domain}</span>
                        <span className="s">{s.score ?? ""}</span>
                        <span className="r">{s.reason}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {items.length > cap && (
                  <button className="shelf-more" onClick={() => setOpen({ ...open, [tier]: true })}>
                    Show all {items.length}
                  </button>
                )}
              </div>
            </section>
          )
        })}

        {needle && matched.length === 0 && (
          <div className="sites-none">
            <p className="serif">We haven’t rated “{q.trim()}” yet.</p>
            <p>
              If it’s a website, <Link href={`/search?q=${encodeURIComponent(q.trim())}`}>request it</Link> and
              we’ll read its policy, usually within a minute.
            </p>
          </div>
        )}
      </div>
    </>
  )
}
