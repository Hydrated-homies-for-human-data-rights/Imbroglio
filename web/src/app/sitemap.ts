import type { MetadataRoute } from "next"
import { cacheLife } from "next/cache"
import { showable } from "@/components/home/data"
import { getSites } from "@/lib/api"
import { SITE_URL } from "@/lib/links"

// The editorial pages and every rated site's report, from the same list the
// every-site page shows (GET /v1/sites) behind the same front-page gate. The
// list is cached for an hour, so crawlers never wait on the API.
const PAGES = ["/", "/how-we-score", "/learn", "/sites", "/research", "/extension", "/about", "/privacy"]

async function ratedReports(): Promise<{ domain: string; analyzed: string | null }[]> {
  "use cache"
  cacheLife("hours")
  try {
    const { sites } = await getSites()
    return sites
      .filter((s) => s.headline && s.headline !== "INFO" && showable(s.domain))
      .map((s) => ({ domain: s.domain, analyzed: s.analyzed_at }))
  } catch {
    // no API (a build without credentials, or an outage): the pages alone
    return []
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const reports = await ratedReports()
  return [
    ...PAGES.map((path) => ({ url: `${SITE_URL}${path === "/" ? "" : path}` })),
    ...reports.map((r) => ({
      url: `${SITE_URL}/site/${encodeURIComponent(r.domain)}`,
      ...(r.analyzed ? { lastModified: r.analyzed } : {}),
    })),
  ]
}
