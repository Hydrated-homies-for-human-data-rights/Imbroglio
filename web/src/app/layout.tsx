import type { Metadata } from "next"
import { Inter } from "next/font/google"
import Footer from "@/components/Footer"
import "./globals.css"

// The design's font stack starts with Inter (Figma Make src/index.css).
// italic too: quotes are italic, and the design turns off synthesized italics
const inter = Inter({ variable: "--font-inter", subsets: ["latin"], style: ["normal", "italic"] })

export const metadata: Metadata = {
  title: "Imbroglio",
  description: "Privacy policies and terms of service, rated with the exact quotes behind every rating.",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-[#f5f7f9] text-[#11253a]">
        {children}
        <Footer />
      </body>
    </html>
  )
}
