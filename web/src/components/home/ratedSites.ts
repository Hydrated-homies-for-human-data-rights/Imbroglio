import "server-only"

import { connection } from "next/server"
import { cache } from "react"
import { getSites, type Tier } from "@/lib/api"
import { showable } from "./data"
import type { ShelfSite } from "./Shelves"

// Every rated site the site lists, from GET /v1/sites at request time. The
// every-site page shows these and the about page counts them, so the two
// never disagree. The same front-page gate (showable) keeps the same sites
// off both. Null when the API can't be reached.

const fallbackReason = (tier: Tier) =>
  tier === "UNCLEAR"
    ? "Too few of the key questions answered"
    : tier === "NOT_DISCLOSED"
      ? "The documents don’t say"
      : "Nothing takes points off"

export const ratedSites = cache(async (): Promise<ShelfSite[] | null> => {
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
})
