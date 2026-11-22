import type { MetadataRoute } from "next"
import { SITE_URL } from "@/lib/links"

// Everything a reader can open may be crawled. The API routes are for the
// browser extension and the request form, not for search engines. Search
// result pages stay crawlable so engines can read their noindex.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
