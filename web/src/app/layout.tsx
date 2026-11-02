import type { Metadata } from "next"
import { IBM_Plex_Mono, Instrument_Sans, Inter, Newsreader } from "next/font/google"
import Footer from "@/components/Footer"
import "./globals.css"

// The design's font stack starts with Inter (Figma Make src/index.css).
// italic too: quotes are italic, and the design turns off synthesized italics
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], style: ["normal", "italic"] })

// The front page's own three faces (see components/home): a serif for the
// document and the headline, a grotesk for the interface, a monospace for
// line numbers, hashes and dates. The report pages keep Inter.
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
  weight: ["300", "400", "500"],
})
const instrument = Instrument_Sans({ variable: "--font-instrument", subsets: ["latin"], weight: ["400", "500", "600"] })
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] })

export const metadata: Metadata = {
  title: "Imbroglio",
  description: "Privacy policies and terms of service, rated with the exact quotes behind every rating.",
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
