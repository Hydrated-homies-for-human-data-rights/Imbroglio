import { readFile } from "node:fs/promises"
import { join } from "node:path"
import type { ReactNode } from "react"
import type { Tier } from "@/lib/api"

// Shared pieces of the link preview images (opengraph-image.tsx): the card
// a chat app or social site shows when someone pastes an imbroglio.io link.
// Drawn by next/og, which takes inline styles only and needs its fonts as
// files: Inter, the report pages' face, from assets/fonts (OFL).

export const OG_SIZE = { width: 1200, height: 630 }

const font = (file: string) => readFile(join(process.cwd(), "assets/fonts", file))

export async function ogFonts() {
  const [medium, bold, extraBold] = await Promise.all([
    font("inter-latin-500-normal.woff"),
    font("inter-latin-700-normal.woff"),
    font("inter-latin-800-normal.woff"),
  ])
  return [
    { name: "Inter", data: medium, weight: 500 as const, style: "normal" as const },
    { name: "Inter", data: bold, weight: 700 as const, style: "normal" as const },
    { name: "Inter", data: extraBold, weight: 800 as const, style: "normal" as const },
  ]
}

// The website's colors (components/design.tsx, components/home/home.css).
export const INK = "#0f253a"
export const MUTED = "#5a6b7e"
export const FAINT = "#8995a3"
export const PAPER = "#f5f7f9"
export const PINK = "#f79ac0"
export const TIER_COLOR: Record<Tier, string> = {
  SEVERE: "#b73329",
  EXTENSIVE: "#c76017",
  MODERATE: "#546579",
  LIMITED: "#39704e",
  NOT_DISCLOSED: "#8b95a4",
  UNCLEAR: "#6b7280",
  INFO: "#6b7280",
}
export const TIER_WORD: Record<Tier, string> = {
  SEVERE: "Severe",
  EXTENSIVE: "Extensive",
  MODERATE: "Moderate",
  LIMITED: "Limited",
  NOT_DISCLOSED: "Not disclosed",
  UNCLEAR: "Unclear",
  INFO: "Info",
}

// Each rating's shape, as on the site, so the card never relies on color alone.
export function TierShape({ tier, size }: { tier: Tier; size: number }) {
  const c = TIER_COLOR[tier]
  const shape =
    tier === "SEVERE" ? (
      <rect x="3" y="3" width="18" height="18" rx="2" fill={c} />
    ) : tier === "EXTENSIVE" ? (
      <path d="M12 2.5 22.5 21h-21z" fill={c} />
    ) : tier === "LIMITED" ? (
      <circle cx="12" cy="12" r="9" fill="none" stroke={c} strokeWidth="2.6" />
    ) : tier === "NOT_DISCLOSED" ? (
      <rect x="3" y="3" width="18" height="18" fill="none" stroke={c} strokeWidth="2" strokeDasharray="4 3" />
    ) : (
      <circle cx="12" cy="12" r="9.5" fill={c} />
    )
  return (
    <svg width={size} height={size} viewBox="0 0 24 24">
      {shape}
    </svg>
  )
}

// The frame every card shares: the pink bar with the wordmark, the content,
// and a footer line.
export function OgFrame({ children, footer }: { children: ReactNode; footer: string }) {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: PAPER, fontFamily: "Inter", color: INK }}>
      <div style={{ height: 96, background: PINK, display: "flex", alignItems: "center", padding: "0 64px" }}>
        <div style={{ display: "flex", fontSize: 44, fontWeight: 800, letterSpacing: -1.5, color: "#000" }}>
          imbroglio<span style={{ color: "#c0392b" }}>.</span>
        </div>
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: "48px 64px 0", overflow: "hidden" }}>{children}</div>
      <div style={{ display: "flex", padding: "0 64px 40px", fontSize: 24, fontWeight: 500, color: MUTED }}>{footer}</div>
    </div>
  )
}
