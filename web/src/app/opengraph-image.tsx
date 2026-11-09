import { ImageResponse } from "next/og"
import { INK, MUTED, OG_SIZE, OgFrame, TierShape, ogFonts } from "@/lib/og"

// The default link preview, for the home page and any page without its own:
// the opening screen's headline and what Imbroglio does.

export const alt = "Imbroglio: know what you agreed to"
export const size = OG_SIZE
export const contentType = "image/png"

export default async function Image() {
  return new ImageResponse(
    <OgFrame footer="Privacy policies and terms, rated with the exact quotes behind every rating · imbroglio.io">
      <div style={{ display: "flex", maxWidth: 680, fontSize: 92, fontWeight: 800, letterSpacing: -3.5, lineHeight: 1, color: INK }}>
        Know what you agreed to.
      </div>
      <div style={{ display: "flex", marginTop: 22, maxWidth: 1072, fontSize: 30, fontWeight: 500, lineHeight: 1.35, color: MUTED }}>
        Imbroglio reads the privacy policies and terms of the sites you use, and tells you in plain words what they let
        a company do with your data.
      </div>
      <div style={{ display: "flex", alignItems: "center", marginTop: 24 }}>
        {(["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED"] as const).map((t) => (
          <div key={t} style={{ display: "flex", marginRight: 18 }}>
            <TierShape tier={t} size={34} />
          </div>
        ))}
      </div>
    </OgFrame>,
    { ...size, fonts: await ogFonts() },
  )
}
