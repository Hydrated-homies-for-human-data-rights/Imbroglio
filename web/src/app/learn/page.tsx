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
              // "guide-" keeps these ids apart from the chapters' (the rights
              // guide and the rights chapter were both #rights)
              <li key={g.id} id={`guide-${g.id}`}>
                <h3>{g.title}</h3>
                <p>
                  {g.body}
                  {g.id === "rights" && (
                    <>
                      {" "}
                      <a href="#rights">See which laws apply where.</a>
                    </>
                  )}
                </p>
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
          deleted, and opt out of its sale. A short email to the address in the privacy policy, naming the right
          you are using, is enough to start. Many companies honor deletion requests from everyone, even where no
          law requires it, so ask anyway.
        </p>
        <p>
          Where a report says a right is offered only in some places, that is what the document says, not what
          the company will do. <Link href="/how-we-score">How we score</Link> explains the difference.
        </p>

        <h3>In the United States</h3>
        <p>
          Your rights depend on your state. As of November 2026, 19 states have a comprehensive consumer privacy
          law in effect: California, Colorado, Connecticut, Delaware, Indiana, Iowa, Kentucky, Maryland,
          Minnesota, Montana, Nebraska, New Hampshire, New Jersey, Oregon, Rhode Island, Tennessee, Texas, Utah and
          Virginia. Florida has a narrower law that covers only very large companies. Louisiana’s and
          Oklahoma’s laws start on January 1, 2027, Alabama’s on May 1, 2027, and Vermont’s on January 1, 2028.
          The IAPP keeps the current list in its{" "}
          <a href="https://iapp.org/resources/article/us-state-privacy-legislation-tracker/" target="_blank" rel="noopener noreferrer">
            state privacy law tracker
          </a>
          .
        </p>
        <p>Most of these laws give you the same core rights:</p>
        <ul>
          <li>Access: find out what a company holds about you, and get a copy.</li>
          <li>Deletion: have the company delete it.</li>
          <li>Correction: have mistakes fixed.</li>
          <li>Opting out of the sale of your data and of targeted advertising.</li>
          <li>Appeal: ask the company to reconsider if it turns your request down.</li>
        </ul>
        <p>
          The details vary. A few states leave out a right, and most of these laws only cover companies above a
          certain size. If a company ignores your request or refuses it without a good reason, you can complain to
          your state attorney general. In California you can also{" "}
          <a href="https://privacy.ca.gov/tips/submit-complaint/" target="_blank" rel="noopener noreferrer">
            complain to the California Privacy Protection Agency
          </a>
          .
        </p>

        <h3>In the EU and the UK</h3>
        <p>
          The GDPR, and the UK GDPR, give you these rights and more, including the right to object to how your
          data is used. A company generally has one month to answer. If it doesn’t help, complain to your
          country’s{" "}
          <a href="https://www.edpb.europa.eu/about-edpb/about-edpb/members_en" target="_blank" rel="noopener noreferrer">
            data protection authority
          </a>
          , or in the UK to the{" "}
          <a href="https://ico.org.uk/make-a-complaint/" target="_blank" rel="noopener noreferrer">
            Information Commissioner’s Office (ICO)
          </a>
          .
        </p>

        <h3>In Canada</h3>
        <p>
          PIPEDA, the federal law for private businesses, lets you see the personal information a business holds
          about you and have mistakes corrected. Raise a problem with the business first. If that doesn’t work,
          you can complain to the{" "}
          <a href="https://www.priv.gc.ca/en/report-a-concern/" target="_blank" rel="noopener noreferrer">
            Office of the Privacy Commissioner of Canada
          </a>
          . Quebec’s Law 25 gives Quebec residents more rights, enforced by Quebec’s Commission d’accès à
          l’information. Alberta and British Columbia have their own laws for businesses too.
        </p>

        <h3>When a policy says nothing</h3>
        <p>
          A report marks a practice Not disclosed when the documents don’t mention it. That doesn’t mean the
          company doesn’t do it, only that it hasn’t said. You can ask. Write to the privacy contact in the policy,
          name the practice, and ask a direct question. For example:
        </p>
        <p className="quote">
          Hello. Your privacy policy doesn’t say whether you use my personal data to train AI models. Do you? If
          you do, how can I opt out? Please answer in writing. Thank you.
        </p>
        <p>
          Keep a copy of what you send and any reply. If you live somewhere with a right of access, you can also
          ask for a copy of the data the company holds about you, which often answers the question.
        </p>
      </Chapter>
    </Page>
  )
}
