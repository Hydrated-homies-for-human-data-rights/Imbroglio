import type { Metadata } from "next"
import localFont from "next/font/local"
import Footer from "@/components/Footer"
import "./globals.css"

// The site's fonts are served from the repo (app/fonts, SIL Open Font
// License, from Fontsource) instead of fetched from Google Fonts on every
// build: that fetch failed CI twice. Same faces and CSS variables as before.

// The design's font stack starts with Inter (Figma Make src/index.css).
// italic too: quotes are italic, and the design turns off synthesized italics
const inter = localFont({
  variable: "--font-inter",
  src: [
    { path: "./fonts/inter-latin-wght-normal.woff2", weight: "100 900", style: "normal" },
    { path: "./fonts/inter-latin-wght-italic.woff2", weight: "100 900", style: "italic" },
  ],
})

// The front page's own three faces (see components/home): a serif for the
// document and the headline, a grotesk for the interface, a monospace for
// line numbers, hashes and dates. The report pages keep Inter.
const newsreader = localFont({
  variable: "--font-newsreader",
  src: [
    { path: "./fonts/newsreader-latin-wght-normal.woff2", weight: "200 800", style: "normal" },
    { path: "./fonts/newsreader-latin-wght-italic.woff2", weight: "200 800", style: "italic" },
  ],
})
const instrument = localFont({
  variable: "--font-instrument",
  src: [{ path: "./fonts/instrument-sans-latin-wght-normal.woff2", weight: "400 700", style: "normal" }],
})
const plexMono = localFont({
  variable: "--font-plex-mono",
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
  ],
})

const DESCRIPTION = "Privacy policies and terms of service, rated with the exact quotes behind every rating."

// metadataBase turns the link previews' relative image paths into full
// addresses. SITE_URL overrides it for preview deployments.
export const metadata: Metadata = {
  metadataBase: new URL(process.env.SITE_URL ?? "https://imbroglio.io"),
  title: "Imbroglio",
  description: DESCRIPTION,
  openGraph: { siteName: "Imbroglio", type: "website", title: "Imbroglio", description: DESCRIPTION },
  twitter: { card: "summary_large_image" },
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${newsreader.variable} ${instrument.variable} ${plexMono.variable}`}>
      <body className="min-h-screen bg-[#f5f7f9] text-[#11253a]">
        {children}
        <Footer />
      </body>
    </html>
  )
}
