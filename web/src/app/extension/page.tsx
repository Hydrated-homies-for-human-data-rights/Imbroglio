import type { Metadata } from "next"
import Image from "next/image"
import Link from "next/link"
import { BottomBar, Masthead } from "@/components/home/chrome"
import popup from "@/components/home/extension-popup.png"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/extension.css"

export const metadata: Metadata = {
  title: "The extension · Imbroglio",
  description: "Imbroglio is now a Chrome extension: the privacy rating for the site you’re on, right on your toolbar.",
}

// The extension's public page. The Chrome Web Store link stays off the page
// until EXTENSION_STORE_URL is set (a chromewebstore.google.com address);
// until then the button says the link is coming. Set it in Vercel and
// redeploy: the page is built ahead of time.
function storeUrl(): string | null {
  const raw = process.env.EXTENSION_STORE_URL?.trim()
  if (!raw) return null
  try {
    const url = new URL(raw)
    return url.protocol === "https:" && url.hostname === "chromewebstore.google.com" ? url.toString() : null
  } catch {
    return null
  }
}

function Install({ href }: { href: string | null }) {
  if (href)
    return (
      <a className="xt-install" href={href} target="_blank" rel="noopener noreferrer">
        Add to Chrome
      </a>
    )
  return (
    <span className="xt-install is-waiting">
      Add to Chrome<small>link coming soon</small>
    </span>
  )
}

// One thread, drawn twice: once behind the headline and once in dashes over
// it, so it reads as woven through the letters.
const WEAVE = "M-60 380 C 150 12, 330 540, 560 240 S 880 0, 1130 320"

function Headline() {
  return (
    <h1 className="xt-head">
      <span className="sr-only">The extension is live.</span>
      <svg viewBox="0 0 1072 496" aria-hidden="true" focusable="false">
        <path className="thread" d={WEAVE} />
        <text x="0" y="142" textLength="1072" lengthAdjust="spacingAndGlyphs" className="l1">
          The extension
        </text>
        <text x="-4" y="488" textLength="1076" lengthAdjust="spacingAndGlyphs" className="l2">
          is live.
        </text>
        <path className="thread over" d={WEAVE} />
      </svg>
    </h1>
  )
}

function Stamp() {
  return (
    <svg className="xt-stamp" viewBox="0 0 220 220" role="img" aria-label="Free, no account, no ads, no tracking. Version 1.1">
      <defs>
        <path id="xt-ring" d="M110 110 m -82 0 a 82 82 0 1 1 164 0 a 82 82 0 1 1 -164 0" />
      </defs>
      <circle cx="110" cy="110" r="106" className="outer" />
      <circle cx="110" cy="110" r="62" className="inner" />
      <text className="ring">
        <textPath href="#xt-ring">FREE · NO ACCOUNT · NO ADS · NO TRACKING ·</textPath>
      </text>
      <text x="110" y="104" textAnchor="middle" className="ver">
        version
      </text>
      <text x="110" y="134" textAnchor="middle" className="num">
        1.1
      </text>
    </svg>
  )
}

export default function ExtensionPage() {
  const href = storeUrl()
  return (
    <div className="home page xt">
      <Masthead />
      <main className="page-main" id="main">
        <section aria-labelledby="xt-intro">
          <Headline />
          <div className="xt-bar">
            <p id="xt-intro">
              Imbroglio is now a Chrome extension. Every site you visit gets its privacy rating, right on your toolbar.
            </p>
            <Install href={href} />
            <Stamp />
          </div>
        </section>

        <section className="xt-what" aria-labelledby="xt-what-h">
          <div className="xt-popup">
            <Image
              src={popup}
              alt="The Imbroglio popup on spotify.com: rated Extensive, 46 out of 100, with its biggest flags and two alert switches"
              sizes="(max-width: 420px) 100vw, 360px"
            />
            <svg viewBox="0 0 440 620" aria-hidden="true" focusable="false">
              <path d="M10 120 C 120 60, 200 150, 300 90 S 430 40, 432 130" />
              <path d="M432 130 C 436 260, 380 380, 420 520 C 440 590, 360 610, 300 600" />
              <path d="M300 600 C 240 590, 230 540, 270 530 C 310 520, 320 570, 280 585 C 250 596, 210 600, 150 612" />
            </svg>
          </div>
          <div className="xt-lines">
            <h2 id="xt-what-h" className="mono">
              Click the icon, and you get
            </h2>
            <p>A rating for the site.</p>
            <p className="pink">The words behind it.</p>
            <p>A way out, if there is one.</p>
            <p className="serif note">All of it read from the site’s own privacy policy and terms, so you don’t have to.</p>
          </div>
        </section>

        <section className="xt-private" aria-labelledby="xt-private-h">
          <h2 id="xt-private-h">We never find out where you browse.</h2>
          <div className="xt-ticket">
            <div className="yours">
              <span className="mono label">Your half · stays on your computer</span>
              <span className="mono big">spotify.com</span>
              <span className="say">
                To look up a rating, the extension scrambles the site’s name into a code, then tears off just the first
                three letters and sends us those.
              </span>
            </div>
            <div className="ours">
              <span className="mono label">Our half · all we get</span>
              <span className="mono code">0fa</span>
              <span className="say">
                Thousands of sites share those three letters. It isn’t a name, so we can’t tell which one you’re on.
              </span>
            </div>
          </div>
          <p className="xt-more">
            <Link href="/privacy#extension-h">The full details are in our privacy policy</Link>
          </p>
        </section>
      </main>
      <BottomBar />
    </div>
  )
}
