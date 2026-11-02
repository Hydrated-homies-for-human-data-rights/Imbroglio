import type { Metadata } from "next"
import Link from "next/link"
import Page, { Chapter } from "@/components/home/Page"
import { FIGURES } from "@/components/home/data"

export const metadata: Metadata = {
  title: "About · Imbroglio",
  description: "Who makes Imbroglio and where it started.",
}

// Everything here comes from the project proposal and team agreement; the
// figures are the same ones the front page shows (components/home/data.ts).
const TEAM = [
  { name: "Gage Gunn", role: "Technical lead. Extraction, hosting, the API." },
  { name: "Sam Holton", role: "Project manager. Documentation, the rubric, the scorer." },
  { name: "Jaiden Searle", role: "Discovery and fetching, the change monitor, the web app." },
  { name: "Alex Kimoni", role: "The policy text classifier and the browser extension." },
]

export default function AboutPage() {
  return (
    <Page
      current="/about"
      eyebrow="About"
      title="Nobody reads privacy policies."
      lede="They are long, dense, and written to be agreed to rather than understood. Imbroglio reads them so you can see, sentence by sentence, what you are agreeing to."
    >
      <Chapter id="start" eyebrow="Where it started" title="A capstone, and a question nobody could answer">
        <p>
          Imbroglio began in the fall of 2026 as a senior capstone at Metropolitan State University of Denver.
          The first team assignment asked for a big idea, and we used the one we actually wanted to build: for
          almost any website or app, there is no practical answer to the question “what am I actually agreeing
          to?”
        </p>
        <p>
          The projects that already tried fall into two camps. Volunteer-curated ratings are careful and
          trusted, but in more than a decade have graded only a few hundred services, and most of the sites
          people use every day have no grade at all. The newer AI browser extensions can read any document, but
          none of them publish a method or an accuracy figure, so there is no way to know whether to believe
          them. The research that solved both problems was never turned into something people could use.
        </p>
        <p>
          We wanted the coverage of the automated tools with the trust of the curated ones. That meant one
          rule above all others: no finding without the exact sentence that supports it, checked in code
          against the document itself.
        </p>
      </Chapter>

      <Chapter id="what" eyebrow="What we built" title="A nutrition label for the fine print">
        <p>
          Imbroglio fetches a site’s privacy policy and terms of service, keeps every version, and asks the same
          fixed questions of each one. A model answers and must quote the document; our code throws out any
          quote it cannot find word for word in the stored text. Plain, published rules then turn the verified
          answers into a rating per category. No model ever decides a rating.
        </p>
        <p>
          The result is served free, on this site and in a browser extension, and every rating opens to the
          findings and the quotes behind it. Where a document is silent we say so, instead of filling the gap.
          We report what the documents say and let you decide.
        </p>
        <p className="note">
          As of {FIGURES.measured}: {FIGURES.sites} sites rated, {FIGURES.quotes.toLocaleString("en-US")} quotes cited,{" "}
          {FIGURES.found} percent of them found word for word. The figures, and how they were measured, are on{" "}
          <Link href="/how-we-score">how we score</Link>.
        </p>
      </Chapter>

      <Chapter id="team" eyebrow="The team" title="Four people, one semester" wide>
        <ul className="people">
          {TEAM.map((p) => (
            <li key={p.name}>
              <span className="name">{p.name}</span>
              <span className="role">{p.role}</span>
            </li>
          ))}
        </ul>
        <p className="note" style={{ marginTop: 28 }}>
          Computer science students at MSU Denver, building Imbroglio as the CS 4360 Senior Experience project.
          Every member writes code.
        </p>
      </Chapter>

      <Chapter id="principles" eyebrow="How we work" title="The rules we don’t break">
        <ul>
          <li>Report, don’t judge. We describe practices, never motives.</li>
          <li>No quote, no finding. Every quote is checked in code against the stored text before it can count.</li>
          <li>The model extracts and the code scores. No model ever gives a rating.</li>
          <li>Not disclosed is its own answer. Silence is reported, never read as good or bad.</li>
          <li>The overall rating is the worst category, never an average.</li>
          <li>Everything is versioned: the rubric, the scorer and the document a rating was made from.</li>
          <li>No accounts. Nothing on this site asks who you are.</li>
        </ul>
        <p>
          If we got something wrong, <Link href="/report">tell us</Link>. A person rereads the finding against the
          document, and if the quote doesn’t support it, we withdraw it.
        </p>
      </Chapter>
    </Page>
  )
}
