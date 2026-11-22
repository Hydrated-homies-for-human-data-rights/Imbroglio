import type { Metadata } from "next"
import Link from "next/link"
import { BottomBar, Masthead } from "@/components/home/chrome"
import Knot from "@/components/home/Knot"
import Thread, { type Stop } from "@/components/home/Thread"
import { Reach } from "@/components/home/reach"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/about.css"

export const metadata: Metadata = {
  title: "Privacy · Imbroglio",
  description: "What Imbroglio and its browser extension collect, keep and share. Very little.",
}

// Imbroglio's own privacy policy, also the policy the Chrome Web Store
// listing links to. Every statement here is checked against the code:
//  * extension: extension/background.js (3-character sha256 prefix lookups,
//    up to MAX_CANDIDATES = 3 per name: the name, then its parent domains;
//    candidates() skips IP addresses and names without a dot; 10-minute
//    cache; alert records under an HMAC with a per-install secret) and
//    extension/manifest.json
//  * lookups: web/src/app/api/v1/lookup, pipeline/imbroglio/api.py
//    (_RateLimiter counts in memory, nothing written; requests also have a
//    daily limit)
//  * requests: analysis_requests (migration 0002) has no column for who asked
//  * reports: reports.client (migration 0008), kept for abuse review
// If any of those change, this page changes with them.
// Laid out like the About page, along the same thread.
const ROUTE: Stop[] = [
  { id: "knot", side: "right" },
  { id: "rail-top", side: "center" },
  { id: "rail-bottom", side: "center" },
  { id: "close-l", side: "center" },
  { id: "close-r", side: "center" },
]

const UPDATED = "November 20, 2026"

const SHORT: [string, string][] = [
  ["No accounts.", "Nothing here asks who you are."],
  ["No cookies, no analytics, no ads.", "There are no trackers on this site or in the extension."],
  ["The extension never sends the name of the site you’re on.", "It sends the first three characters of a scrambled version of it, which many sites share."],
  ["We don’t sell or share anything about you,", "and we don’t train AI models on anything you send us."],
]

export default function PrivacyPage() {
  return (
    <div className="home page about">
      <Thread route={ROUTE} drive="time" />
      <Masthead current="/privacy" />
      <main className="page-main" id="main">
        <section className="hero" aria-labelledby="privacy-h1">
          <div className="page-head">
            <div className="eyebrow mono">Privacy · Imbroglio</div>
            <h1 id="privacy-h1">We hold ourselves to the same questions.</h1>
            <p className="lede">
              Imbroglio rates other sites’ privacy policies, so here is ours, written to answer the questions we ask
              of everyone else. Last updated {UPDATED}.
            </p>
          </div>
          <Knot still />
        </section>

        <div className="body">
          <div className="rail" aria-hidden="true">
            <i data-thread="rail-top" style={{ position: "absolute", left: "50%", top: 0 }} />
            <i data-thread="rail-bottom" style={{ position: "absolute", left: "50%", bottom: 0 }} />
          </div>
          <div>
            <Reach className="chapter">
              <h2 id="short-h">
                <span className="eyebrow mono">01 · The short version</span>
                Very little, on purpose
              </h2>
              <div className="chapter-body wide">
                <ol className="rules">
                  {SHORT.map(([lead, rest], i) => (
                    <li key={lead}>
                      <span className="n mono">{String(i + 1).padStart(2, "0")}</span>
                      <span>
                        <b>{lead}</b> {rest}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </Reach>

            <Reach className="chapter">
              <h2 id="extension-h">
                <span className="eyebrow mono">02 · The browser extension</span>
                It asks about a scrambled name, never the site itself
              </h2>
              <div className="chapter-body">
                <p>
                  To show a rating, the extension needs to know which site the current tab is on. It turns the site’s
                  name (say, example.com) into a SHA-256 hash, a long string of letters and numbers that can’t be
                  turned back into the name, and sends only the first three characters to imbroglio.io. There are
                  only 4,096 possible beginnings, so many sites share each one. Our server answers with every site
                  we have stored that starts the same way, and the extension picks out the right one on your own
                  computer. From a single lookup, we can’t tell which of those sites you were on.
                </p>
                <p>
                  A subdomain can take more than one lookup. We store most sites under their main domain, so for a
                  name like wiki.corp.example.com the extension looks up wiki.corp.example.com, then
                  corp.example.com, then example.com, and stops at the first one we have. That is at most three
                  lookups in a row. Each one is still only three characters, but a series of them for one name and
                  its parents narrows down the possibilities much more than a single lookup does. In a coming update,
                  the extension will look up only the main domain.
                </p>
                <p>
                  It does this for each site you visit so the toolbar icon can show a rating, and remembers each
                  answer for up to ten minutes so it doesn’t ask again. Like any request, each lookup reaches our
                  hosts’ logs with your IP address (see below). Nothing else about the page is read: not its content,
                  not what you type. IP addresses such as 192.168.1.1, and names without a dot such as localhost or a
                  one-word intranet name, are never looked up. An internal name with dots in it, such as
                  wiki.corp.example.com, is looked up like any other site.
                </p>
                <p>
                  What the extension keeps stays in your browser: your two settings (warn me about Extensive sites,
                  tell me when a policy changes) and, for those alerts, when it last warned you about a site and the
                  date of the last policy change it saw there, filed under a code made from the site’s name and a
                  random secret that never leaves your browser, so the records can’t be matched to sites without it.
                  Removing the extension deletes all of it.
                </p>
                <p>
                  If you click a link in the extension or one of its alerts, such as “Read the quotes on the full
                  report” or “Request it on imbroglio.io”, that opens imbroglio.io with the site’s name in the
                  address, the same as visiting the website yourself.
                </p>
              </div>
            </Reach>

            <Reach className="chapter">
              <h2 id="site-h">
                <span className="eyebrow mono">03 · This website</span>
                What a visit leaves behind
              </h2>
              <div className="chapter-body">
                <p>
                  The website sets no cookies and runs no analytics. Like every website, the companies that host it
                  keep standard request logs, which include your IP address, the page you asked for and the time.
                  We read them only to keep the service running and to stop abuse, and the hosts delete them on their
                  own schedules.
                </p>
                <p>
                  To keep any one visitor from overwhelming the service, we count how many lookups, analysis requests
                  and reports each IP address makes in an hour, and analysis requests in a day as well. Those counts
                  live only in the server’s memory and are never saved.
                </p>
                <p>
                  <b>Requesting an analysis.</b> When you ask us to analyze a site, we store the site’s name and the
                  time, not who asked. We then read that site’s public homepage, privacy policy and terms of service.
                </p>
                <p>
                  <b>Reporting a problem.</b> A report stores your message, the site and page it’s about, the contact
                  details you choose to give (only so we can reply), and your IP address, which we keep only to review
                  abuse of the form. None of it is shown on the site. We keep reports while the project is running; to
                  have yours deleted, send another report saying so.
                </p>
              </div>
            </Reach>

            <Reach className="chapter">
              <h2 id="who-h">
                <span className="eyebrow mono">04 · Who else handles it</span>
                Three hosts, and an AI that only reads policies
              </h2>
              <div className="chapter-body">
                <p>
                  The website runs on Vercel, the API that serves ratings runs on Railway, and the database is hosted
                  by Supabase. They process what is described above on our behalf and for no other purpose.
                </p>
                <p>
                  The analysis itself uses Anthropic’s Claude models, which are sent only the public privacy policies
                  and terms of service we fetch, never anything about the people using Imbroglio.
                </p>
                <p>
                  We don’t sell information about you, share it for advertising, or use it to train AI models. We
                  would hand over what little we have to authorities only if the law required it.
                </p>
              </div>
            </Reach>

            <Reach className="chapter">
              <h2 id="changes-h">
                <span className="eyebrow mono">05 · Changes and questions</span>
                If this changes, this page changes first
              </h2>
              <div className="chapter-body">
                <p>
                  If we change what we collect, we’ll update this page and its date before the change takes effect.
                  Imbroglio is open source, so you can also read exactly what the code does.
                </p>
                <p>
                  Questions, corrections or a security problem: <Link href="/report">tell us</Link>. Imbroglio is a
                  senior capstone project at Metropolitan State University of Denver, built by the team on the{" "}
                  <Link href="/about">About</Link> page.
                </p>
              </div>
            </Reach>

            <section className="close" aria-labelledby="close-h">
              <h2 id="close-h" className="serif">
                Now read someone else’s.
              </h2>
              <form action="/search" className="search" role="search">
                <label className="sr-only" htmlFor="q-privacy">
                  Search a site or service
                </label>
                <input id="q-privacy" name="q" placeholder="Search a site or service" autoComplete="off" />
                <button type="submit" aria-label="Search">
                  ↵
                </button>
                <i data-thread="close-l" style={{ position: "absolute", left: 0, bottom: 0 }} />
                <i data-thread="close-r" style={{ position: "absolute", right: 0, bottom: 0 }} />
              </form>
            </section>
          </div>
        </div>
      </main>
      <BottomBar />
    </div>
  )
}
