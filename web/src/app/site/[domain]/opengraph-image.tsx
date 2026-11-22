import { cacheLife } from "next/cache"
import { ImageResponse } from "next/og"
import { getSite, type Site } from "@/lib/api"
import { cleanDomain } from "@/lib/format"
import { FAINT, INK, MUTED, OG_SIZE, OgFrame, TIER_COLOR, TIER_WORD, TierShape, ogFonts } from "@/lib/og"

// The link preview for a report: what a chat app shows when someone shares
// imbroglio.io/site/<domain>. The site, its rating and score, and the biggest
// things that took points off. Same data as the report page.

export const alt = "The site's Imbroglio privacy rating"
export const size = OG_SIZE
export const contentType = "image/png"

// A preview is fetched by every chat app a link is pasted into, so the data
// behind it is cached for a few minutes per site instead of read on every
// hit, and the image itself may be kept by the CDN as long. A failed read
// throws, so it isn't cached; the image then says "not rated yet" once.
async function siteFor(domain: string): Promise<Site> {
  "use cache"
  cacheLife({ stale: 300, revalidate: 900, expire: 86_400 })
  return getSite(domain)
}
const CACHE_CONTROL = "public, max-age=300, s-maxage=900, stale-while-revalidate=86400"

export default async function Image({ params }: { params: Promise<{ domain: string }> }) {
  // Only ever a cleaned domain on the image: arbitrary text from the link
  // would otherwise be drawn as if we said it.
  let domain: string | null = null
  try {
    domain = cleanDomain(decodeURIComponent((await params).domain))
  } catch {}
  if (!domain) return new Response(null, { status: 404 })
  const site: Site | null = await siteFor(domain).catch(() => null)
  const card = site?.scorecard ?? null

  const body = card ? (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", fontSize: 24, fontWeight: 700, letterSpacing: 3, color: MUTED }}>PRIVACY REPORT</div>
      <div style={{ display: "flex", marginTop: 8, fontSize: domain.length > 24 ? 56 : 76, fontWeight: 800, letterSpacing: -2.5, wordBreak: "break-all", color: INK }}>
        {domain}
      </div>
      <div style={{ display: "flex", alignItems: "center", marginTop: 26, color: TIER_COLOR[card.headline] }}>
        <TierShape tier={card.headline} size={56} />
        <div style={{ display: "flex", marginLeft: 22, fontSize: 64, fontWeight: 800, letterSpacing: -1.5 }}>
          {TIER_WORD[card.headline]}
        </div>
        {card.score && (
          <div style={{ display: "flex", alignItems: "center", marginLeft: 22 }}>
            <span style={{ fontSize: 56, fontWeight: 700, color: FAINT }}>·</span>
            <div style={{ display: "flex", alignItems: "baseline", marginLeft: 22 }}>
              <span style={{ fontSize: 96, fontWeight: 800, letterSpacing: -3 }}>{card.score.value}</span>
              <span style={{ marginLeft: 4, fontSize: 40, fontWeight: 700, opacity: 0.75 }}>/100</span>
            </div>
          </div>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", marginTop: 22, fontSize: 30, fontWeight: 500, color: MUTED }}>
        {card.score && card.score.deductions.length > 0
          ? card.score.deductions.slice(0, 2).map((d) => (
              <div key={d.check_id} style={{ display: "flex", marginTop: 6 }}>
                <span style={{ width: 84, fontWeight: 700, color: "#a6461d" }}>−{d.points}</span>
                <span>{d.plain ?? d.meaning}</span>
              </div>
            ))
          : (
              <div style={{ display: "flex" }}>
                {card.headline === "UNCLEAR"
                  ? "Too few of the key questions were answered to give a score."
                  : card.headline === "LIMITED"
                    ? "No red flags in its privacy policy or terms."
                    : "Rated from its own privacy policy and terms."}
              </div>
            )}
      </div>
    </div>
  ) : (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", fontSize: 24, fontWeight: 700, letterSpacing: 3, color: MUTED }}>PRIVACY REPORT</div>
      <div style={{ display: "flex", marginTop: 8, fontSize: domain.length > 24 ? 56 : 76, fontWeight: 800, letterSpacing: -2.5, wordBreak: "break-all" }}>{domain}</div>
      <div style={{ display: "flex", marginTop: 26, fontSize: 36, fontWeight: 500, color: MUTED }}>
        Not rated yet. Ask for it on imbroglio.io.
      </div>
    </div>
  )

  return new ImageResponse(
    <OgFrame footer="Every rating quotes the site’s own policy, checked word for word · imbroglio.io">{body}</OgFrame>,
    { ...size, fonts: await ogFonts(), headers: { "Cache-Control": CACHE_CONTROL } },
  )
}
