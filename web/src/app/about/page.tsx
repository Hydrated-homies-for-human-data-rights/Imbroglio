import type { Metadata } from "next"
import Link from "next/link"
import { Chapter } from "@/components/home/Page"
import { BottomBar, Masthead } from "@/components/home/chrome"
import Knot from "@/components/home/Knot"
import Thread, { type Stop } from "@/components/home/Thread"
import { FIGURES } from "@/components/home/data"
import { Reach } from "@/components/home/reach"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/about.css"

export const metadata: Metadata = {
  title: "About · Imbroglio",
  description: "Who makes Imbroglio and where it started.",
}

// The story told along one thread. It leaves the knot beside the headline,
// runs under the lede into the left rail, down past every chapter (each one's
// pin lights as the tip passes) and out along the search line at the end.
// Drawn once on load, by the clock, not by the scroll.
const ROUTE: Stop[] = [
  { id: "knot", side: "right" },
  { id: "rail-top", side: "center" },
  { id: "rail-bottom", side: "center" },
  { id: "close-l", side: "center" },
  { id: "close-r", side: "center" },
]

// Everything here comes from the project proposal and team agreement; the
// figures are the same ones the front page shows (components/home/data.ts).
const TEAM = [
  { name: "Gage Gunn", role: "Technical lead. Extraction, hosting, the API." },
  { name: "Sam Holton", role: "Project manager. Documentation, the rubric, the scorer." },
  { name: "Jaiden Searle", role: "Discovery and fetching, the change monitor, the web app." },
  { name: "Alex Kimoni", role: "The policy text classifier and the browser extension." },
]

const RULES: [string, string][] = [
  ["Report, don’t judge.", "We describe practices, never motives."],
  ["No quote, no finding.", "Every quote is checked in code against the stored text before it can count."],
  ["The model extracts and the code scores.", "No model ever gives a rating."],
  ["Not disclosed is its own answer.", "Silence is reported, never read as good or bad."],
  ["The overall rating is the worst category,", "never an average."],
  ["Everything is versioned:", "the rubric, the scorer and the document a rating was made from."],
  ["No accounts.", "Nothing on this site asks who you are."],
]

export default function AboutPage() {
  return (
    <div className="home page about">
      <Thread route={ROUTE} drive="time" />
      <Masthead current="/about" />
      <main className="page-main">
        <section className="hero" aria-labelledby="about-h1">
          <div className="page-head">
            <div className="eyebrow mono">About · Imbroglio</div>
            <h1 id="about-h1">Nobody reads privacy policies.</h1>
            <p className="lede">
              They are long, dense, and written to be agreed to rather than understood. Imbroglio reads them so you
              can see, sentence by sentence, what you are agreeing to.
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
              <h2 id="start-h">
                <span className="eyebrow mono">01 · Where it started</span>
                A capstone, and a question nobody could answer
              </h2>
              <div className="chapter-body">
                <p>
                  Imbroglio began in the fall of 2026 as a senior capstone at Metropolitan State University of
                  Denver. The first team assignment asked for a big idea, and we used the one we actually wanted to
                  build: for almost any website or app, there is no practical answer to the question “what am I
                  actually agreeing to?”
                </p>
                <p>
                  The projects that already tried fall into two camps. Volunteer-curated ratings are careful and
                  trusted, but in more than a decade have graded only a few hundred services, and most of the sites
                  people use every day have no grade at all. The newer AI browser extensions can read any document,
                  but none of them publish a method or an accuracy figure, so there is no way to know whether to
                  believe them. The research that solved both problems was never turned into something people could
                  use.
                </p>
                <p>We wanted the coverage of the automated tools with the trust of the curated ones. That meant one rule above all others:</p>
                <p className="vow">
                  No finding without the exact sentence that supports it, checked in code against the document itself.
                </p>
              </div>
            </Reach>

            <Reach className="chapter">
              <h2 id="what-h">
                <span className="eyebrow mono">02 · What we built</span>
                A nutrition label for the fine print
              </h2>
              <div className="chapter-body">
                <p>
                  Imbroglio fetches a site’s privacy policy and terms of service, keeps every version, and asks the
                  same fixed questions of each one. A model answers and must quote the document; our code throws out
                  any quote it cannot find word for word in the stored text. Plain, published rules then turn the
                  verified answers into a rating per category. No model ever decides a rating.
                </p>
                <p>
                  The result is served free, on this site and in a browser extension, and every rating opens to the
                  findings and the quotes behind it. Where a document is silent we say so, instead of filling the
                  gap. We report what the documents say and let you decide.
                </p>
                <p className="note mono">
                  as of {FIGURES.measured} · {FIGURES.sites} sites rated · {FIGURES.quotes.toLocaleString("en-US")}{" "}
                  quotes cited · {FIGURES.found}% found word for word · <Link href="/how-we-score">how we score →</Link>
                </p>
              </div>
            </Reach>

            <Chapter id="team" eyebrow="03 · The team" title="Four people, one semester" wide>
              <p style={{ maxWidth: "66ch" }}>
                Computer science students at MSU Denver, building Imbroglio as the CS 4360 Senior Experience project.
                Every member writes code.
              </p>
              <ul className="people">
                {TEAM.map((p) => (
                  <Reach as="li" key={p.name}>
                    <span className="name">{p.name}</span>
                    <span className="role">{p.role}</span>
                  </Reach>
                ))}
              </ul>
            </Chapter>

            <Reach className="chapter">
              <h2 id="principles-h">
                <span className="eyebrow mono">04 · How we work</span>
                The rules we don’t break
              </h2>
              <div className="chapter-body wide">
                <ol className="rules">
                  {RULES.map(([lead, rest], i) => (
                    <li key={lead}>
                      <span className="n mono">{String(i + 1).padStart(2, "0")}</span>
                      <span>
                        <b>{lead}</b> {rest}
                      </span>
                    </li>
                  ))}
                </ol>
                <p style={{ marginTop: 22, maxWidth: "66ch" }}>
                  If we got something wrong, <Link href="/report">tell us</Link>. A person rereads the finding against
                  the document, and if the quote doesn’t support it, we withdraw it.
                </p>
              </div>
            </Reach>

            <section className="close" aria-labelledby="close-h">
              <h2 id="close-h" className="serif">
                Pull another thread.
              </h2>
              <form action="/search" className="search" role="search">
                <label className="sr-only" htmlFor="q-about">
                  Search a site or service
                </label>
                <input id="q-about" name="q" placeholder="Search a site or service" autoComplete="off" />
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
