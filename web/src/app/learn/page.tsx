import type { Metadata } from "next"
import Link from "next/link"
import { connection } from "next/server"
import { Suspense } from "react"
import Page, { Chapter } from "@/components/home/Page"
import { getLearn } from "@/lib/api"

export const metadata: Metadata = {
  title: "What you can do · Imbroglio",
  description: "What to do about each kind of finding, and what the common privacy tools actually do.",
}

// "What you can do": the practical half of a report. Each topic's id is its
// rubric check_id, which scorecard findings and the extension link to as
// /learn#<check_id>. The topics and the general guides come from the API
// (pipeline/imbroglio/advice.yaml); the tools section is written here.

// The tools people reach for, with what each does and what it doesn't. Each
// entry is a place a partner could stand, so the wording stays honest about
// the limits of the tool first. No affiliate links, no named products.
const TOOLS: { name: string; does: string; doesnt: string }[] = [
  {
    name: "A data removal service",
    does: "Finds your records at data brokers and people-search sites and sends the opt-out and deletion requests for you, then keeps sending them as the records come back.",
    doesnt: "Change what a site you use does with the data you give it. It works on the brokers, not on the policy.",
  },
  {
    name: "A VPN",
    does: "Hides your address from the sites you visit and hides which sites you visit from the network you are on, which matters on public Wi-Fi.",
    doesnt: "Stop a site from selling, sharing or training AI on what you do once you log in. It moves your trust from your internet provider to the VPN company, so choose one with an audited no-logs policy.",
  },
  {
    name: "A password manager and two-factor sign-in",
    does: "Gives every account its own password and a second check, so a breach at one site cannot open your others. Most account takeovers come from reused passwords.",
    doesnt: "Reduce what a site collects. It limits the damage when a site’s security is as generic as its policy says.",
  },
  {
    name: "A tracker blocker",
    does: "Blocks the third-party cookies and scripts that follow you between sites and feed ad profiles. Firefox, Safari and Brave block many by default; a content blocker catches more.",
    doesnt: "Affect first-party collection, the data a site gathers from your own account. For that, the site’s settings and your legal rights are the lever.",
  },
]

async function Topics() {
  await connection() // read at request time, never baked in at build
  let learn
  try {
    learn = await getLearn()
  } catch {
    return (
      <Chapter id="findings" eyebrow="About a finding" title="What to do about each one">
        <p className="note">This part is unavailable right now. Try again in a minute.</p>
      </Chapter>
    )
  }
  return (
    <>
      <Chapter id="first" eyebrow="Before anything else" title="Three habits that cover most of it" wide>
        <ol className="steps">
          {learn.guides
            .filter((g) => g.id !== "vpn")
            .map((g) => (
              <li key={g.id} id={g.id}>
                <h3>{g.title}</h3>
                <p>{g.body}</p>
              </li>
            ))}
        </ol>
      </Chapter>

      <Chapter id="findings" eyebrow="About a finding" title="What to do about each one" wide>
        <p className="note" style={{ marginBottom: 12 }}>
          Every finding on a report links to its entry here. The steps are things a person can do today, in
          plain words, and the links go only to official or nonprofit sources.
        </p>
        {learn.topics.map((t) => (
          <article key={t.check_id} id={t.check_id} className="topic">
            <div>
              <div className="eyebrow mono" style={{ marginBottom: 8 }}>
                {t.category}
              </div>
              <h3>{t.title}</h3>
              <p className="why">{t.why}</p>
            </div>
            <ol>
              {t.steps.map((s) => (
                <li key={s.text}>
                  {s.text}
                  {s.link && (
                    <>
                      {" "}
                      <a href={s.link} target="_blank" rel="noopener noreferrer">
                        {new URL(s.link).hostname.replace(/^www\./, "")}
                      </a>
                    </>
                  )}
                </li>
              ))}
            </ol>
          </article>
        ))}
      </Chapter>
    </>
  )
}

export default function LearnPage() {
  return (
    <Page
      current="/learn"
      eyebrow="What you can do"
      title="A rating you can act on."
      lede="Every finding on a report comes with the steps that answer it. Most take minutes, none need an account with us, and the tools below are described by what they actually do."
    >
      <Suspense
        fallback={
          <Chapter id="findings" eyebrow="About a finding" title="What to do about each one">
            <p className="note">Loading…</p>
          </Chapter>
        }
      >
        <Topics />
      </Suspense>

      <Chapter id="tools" eyebrow="The tools" title="What each one does, and what it doesn’t" wide>
        <div className="tools">
          {TOOLS.map((t) => (
            <div key={t.name} className="tool">
              <h3>{t.name}</h3>
              <p>
                <span className="mark-does">Does</span>
                {t.does}
              </p>
              <p>
                <span className="mark-doesnt">Doesn’t</span>
                {t.doesnt}
              </p>
            </div>
          ))}
        </div>
        <p className="note" style={{ marginTop: 28 }}>
          We don’t name products here and no link on this page pays us. If that ever changes, it will say so on
          this line.
        </p>
      </Chapter>

      <Chapter id="rights" eyebrow="The law" title="Rights you may already have">
        <p>
          Depending on where you live, you can ask a company what it holds about you, have it corrected or
          deleted, and opt out of its sale. The EU and UK give these rights under GDPR; California, Colorado,
          Virginia, Texas and a growing number of US states give them by statute. A short email to the address in
          the privacy policy, naming the right you are using, is enough to start. Many companies honor deletion
          requests from everyone, even where no law requires it, so ask anyway.
        </p>
        <p>
          Where a report says a right is offered only in some places, that is what the document says, not what
          the company will do. <Link href="/how-we-score">How we score</Link> explains the difference.
        </p>
      </Chapter>
    </Page>
  )
}
