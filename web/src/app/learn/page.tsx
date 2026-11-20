import type { Metadata } from "next"
import Link from "next/link"
import { connection } from "next/server"
import { Suspense } from "react"
import Page from "@/components/home/Page"
import OpenFromHash from "@/components/learn/OpenFromHash"
import RightsTabs from "@/components/learn/RightsTabs"
import { getLearn, type LearnTopic } from "@/lib/api"
import "@/components/home/learn.css"

export const metadata: Metadata = {
  title: "What you can do · Imbroglio",
  description: "What to do about each kind of finding, and what the common privacy tools actually do.",
}

// "What you can do": the practical half of a report. It opens with what a
// reader might want to change, then one section per kind of help, with the
// page's contents pinned beside them on a wide screen.
//
// Each finding topic's id is its rubric check_id, which reports and the
// extension link to as /learn#<check_id>; the topics are closed <details>
// and OpenFromHash (outside their Suspense boundary) opens the one linked
// to. The topics come from the API (pipeline/imbroglio/advice.yaml);
// everything else is written here.
// Reports also link to #gpc, #rights and #findings.

// What a reader might want to do, each pointing at the section that answers it.
const WANTS: { href: string; title: string; line: string }[] = [
  {
    href: "#sells_personal_data",
    title: "Stop sites selling my data",
    line: "One browser setting covers every site. Then the site’s own opt-out link.",
  },
  {
    href: "#trains_ai_on_user_data",
    title: "Keep my content out of AI training",
    line: "Where the setting usually is, and what to send when there isn’t one.",
  },
  {
    href: "#deletion_on_request",
    title: "Get my data deleted",
    line: "How to ask, and what to do if they say no.",
  },
  {
    href: "#access_and_export",
    title: "See what a site holds about me",
    line: "Ask for a copy. It often answers what the policy doesn’t.",
  },
  {
    href: "#opt_out_of_tracking",
    title: "Stop being tracked across sites",
    line: "Cookie banners, tracker blocking, and what each actually stops.",
  },
  {
    href: "#rights",
    title: "Know my rights where I live",
    line: "US states, the EU and UK, and Canada, in one place.",
  },
]

const CONTENTS = [
  { href: "#gpc", label: "Turn on Global Privacy Control" },
  { href: "#findings", label: "About a finding" },
  { href: "#rights", label: "Your rights" },
  { href: "#tools", label: "The tools" },
  { href: "#silence", label: "When a policy says nothing" },
]

// Global Privacy Control, browser by browser (same facts as advice.yaml's
// sells_personal_data and opt_out_of_tracking steps).
const GPC: { browsers: string; how: string; done?: boolean }[] = [
  { browsers: "Brave, DuckDuckGo", how: "Already on. Nothing to do.", done: true },
  {
    browsers: "Firefox",
    how: "On in private windows. For normal windows: Settings › Privacy & Security › “Tell websites not to sell or share my data”.",
  },
  {
    browsers: "Chrome, Edge, Safari",
    how: "Not built in. Add an extension that sends it, such as Privacy Badger from the EFF.",
  },
]

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

const US_STATES = [
  "California", "Colorado", "Connecticut", "Delaware", "Indiana", "Iowa", "Kentucky", "Maryland", "Minnesota",
  "Montana", "Nebraska", "New Hampshire", "New Jersey", "Oregon", "Rhode Island", "Tennessee", "Texas", "Utah",
  "Virginia",
]

const CORE_RIGHTS: [string, string][] = [
  ["Access", "Find out what a company holds about you, and get a copy."],
  ["Deletion", "Have the company delete it."],
  ["Correction", "Have mistakes fixed."],
  ["Opt out", "Of the sale of your data and of targeted ads."],
  ["Appeal", "Ask them to reconsider if they turn you down."],
]

const out = { target: "_blank", rel: "noopener noreferrer" } as const

function Section({
  id,
  n,
  eyebrow,
  title,
  lede,
  children,
}: {
  id: string
  n: string
  eyebrow: string
  title: string
  lede?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section id={id} className="l-section" aria-labelledby={`${id}-h`}>
      <p className="eyebrow mono">
        {n} · {eyebrow}
      </p>
      <h2 id={`${id}-h`}>{title}</h2>
      {lede && <p className="l-lede">{lede}</p>}
      {children}
    </section>
  )
}

function TopicItem({ t }: { t: LearnTopic }) {
  return (
    <details id={t.check_id} className="l-topic">
      <summary>
        <span className="l-topic-title">{t.title}</span>
        <span className="l-topic-count">
          {t.steps.length} {t.steps.length === 1 ? "step" : "steps"}
        </span>
      </summary>
      <div className="l-topic-body">
        <p className="why serif">{t.why}</p>
        <ol>
          {t.steps.map((s) => (
            <li key={s.text}>
              {s.text}
              {s.link && (
                <>
                  {" "}
                  <a href={s.link} {...out}>
                    {new URL(s.link).hostname.replace(/^www\./, "")}
                  </a>
                </>
              )}
            </li>
          ))}
        </ol>
      </div>
    </details>
  )
}

async function Topics() {
  await connection() // read at request time, never baked in at build
  let learn
  try {
    learn = await getLearn()
  } catch {
    return <p className="note">This part is unavailable right now. Try again in a minute.</p>
  }
  // grouped by category, in the order the topics come
  const groups = new Map<string, LearnTopic[]>()
  for (const t of learn.topics) groups.set(t.category, [...(groups.get(t.category) ?? []), t])
  return (
    <div className="l-groups">
      {[...groups].map(([category, topics]) => (
        <div key={category}>
          <h3 className="eyebrow mono">{category}</h3>
          <div className="l-card">
            {topics.map((t) => (
              <TopicItem key={t.check_id} t={t} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

const US = (
  <>
    <div className="l-rights">
      {CORE_RIGHTS.map(([name, what]) => (
        <div key={name} className="l-card">
          <strong>{name}</strong>
          <p>{what}</p>
        </div>
      ))}
    </div>
    <p>
      Your rights depend on your state. As of November 2026, 19 states have a comprehensive privacy law in
      effect:
    </p>
    <ul className="l-chips" aria-label="States with a privacy law in effect">
      {US_STATES.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
    <p>
      Coming: Louisiana and Oklahoma (January 1, 2027), Alabama (May 1, 2027) and Vermont (January 1, 2028).
      Florida’s law covers only very large companies. Most of these laws only cover companies above a certain size,
      and a few leave out a right. The IAPP keeps the current list in its{" "}
      <a href="https://iapp.org/resources/article/us-state-privacy-legislation-tracker/" {...out}>
        state privacy law tracker
      </a>
      .
    </p>
    <p>
      If a company ignores your request or refuses it without a good reason, complain to your state attorney
      general. In California you can also{" "}
      <a href="https://privacy.ca.gov/tips/submit-complaint/" {...out}>
        complain to the California Privacy Protection Agency
      </a>
      .
    </p>
  </>
)

const EU = (
  <>
    <p>
      The GDPR, and the UK GDPR, let you see, correct and delete your data, take a copy with you, and object to
      how it is used. A company generally has one month to answer.
    </p>
    <p>
      If it doesn’t help, complain to your country’s{" "}
      <a href="https://www.edpb.europa.eu/about-edpb/about-edpb/members_en" {...out}>
        data protection authority
      </a>
      , or in the UK to the{" "}
      <a href="https://ico.org.uk/make-a-complaint/" {...out}>
        Information Commissioner’s Office (ICO)
      </a>
      .
    </p>
  </>
)

const CANADA = (
  <>
    <p>
      PIPEDA, the federal law for private businesses, lets you see the personal information a business holds
      about you and have mistakes corrected. Raise a problem with the business first. If that doesn’t work,
      complain to the{" "}
      <a href="https://www.priv.gc.ca/en/report-a-concern/" {...out}>
        Office of the Privacy Commissioner of Canada
      </a>
      .
    </p>
    <p>
      Quebec’s Law 25 gives Quebec residents more rights, enforced by Quebec’s Commission d’accès à
      l’information. Alberta and British Columbia have their own laws for businesses too.
    </p>
  </>
)

export default function LearnPage() {
  return (
    <Page
      current="/learn"
      eyebrow="What you can do"
      title="A rating you can act on."
      lede="Pick what you want to change. Each answer is a few short steps, and none need an account with us."
    >
      <div className="learn">
        <section aria-labelledby="wants-h" className="l-wants">
          <h2 id="wants-h">What do you want to do?</h2>
          <div className="l-want-grid">
            {WANTS.map((w) => (
              <a key={w.href} href={w.href} className="l-want">
                <strong>{w.title}</strong>
                <span>{w.line}</span>
                <span className="go" aria-hidden="true">
                  See how →
                </span>
              </a>
            ))}
          </div>
        </section>

        <div className="l-layout">
          <nav aria-label="On this page" className="l-contents">
            <span className="eyebrow mono">On this page</span>
            {CONTENTS.map((c) => (
              <a key={c.href} href={c.href}>
                {c.label}
              </a>
            ))}
          </nav>

          <div className="l-main">
            <Section
              id="gpc"
              n="01"
              eyebrow="One setting, every site"
              title="Turn on Global Privacy Control"
              lede="It tells every site you visit not to sell or share your data. In California, Colorado, Connecticut and several other states, businesses must treat it as an opt-out."
            >
              <div className="l-card l-gpc">
                {GPC.map((g) => (
                  <div key={g.browsers}>
                    <strong>{g.browsers}</strong>
                    <span className={g.done ? "done" : undefined}>{g.how}</span>
                  </div>
                ))}
              </div>
              <p className="l-small">
                To check it worked, visit{" "}
                <a href="https://globalprivacycontrol.org" {...out}>
                  globalprivacycontrol.org
                </a>
                , which shows whether your browser is sending the signal.
              </p>
            </Section>

            <Section
              id="findings"
              n="02"
              eyebrow="About a finding"
              title="What to do about each one"
              lede="Every finding on a report links straight to its entry here, opened. The links go only to official or nonprofit sources."
            >
              <Suspense fallback={<p className="note">Loading…</p>}>
                <Topics />
              </Suspense>
              <OpenFromHash />
            </Section>

            <Section
              id="rights"
              n="03"
              eyebrow="The law"
              title="Rights you may already have"
              lede={
                <>
                  A short email to the address in the privacy policy, naming the right you are using, is enough to
                  start. Many companies honor deletion requests from everyone, even where no law requires it, so ask
                  anyway. Where a report says a right is offered only in some places, that is what the document says,
                  not what the company will do; <Link href="/how-we-score">how we score</Link> explains the
                  difference.
                </>
              }
            >
              <RightsTabs
                tabs={[
                  { label: "United States", panel: US },
                  { label: "EU and UK", panel: EU },
                  { label: "Canada", panel: CANADA },
                ]}
              />
            </Section>

            <Section id="tools" n="04" eyebrow="The tools" title="What each one does, and what it doesn’t">
              <div className="l-tools">
                {TOOLS.map((t) => (
                  <div key={t.name} className="l-card">
                    <h3>{t.name}</h3>
                    <p>
                      <span className="does">Does</span> {t.does}
                    </p>
                    <p>
                      <span className="doesnt">Doesn’t</span> {t.doesnt}
                    </p>
                  </div>
                ))}
              </div>
              <p className="l-small">
                We don’t name products here and no link on this page pays us. If that ever changes, it will say so on
                this line.
              </p>
            </Section>

            <Section
              id="silence"
              n="05"
              eyebrow="Not disclosed"
              title="When a policy says nothing"
              lede="A report marks a practice Not disclosed when the documents don’t mention it. That doesn’t mean the company doesn’t do it, only that it hasn’t said. You can ask: write to the privacy contact in the policy, name the practice, and ask a direct question."
            >
              <p className="quote">
                Hello. Your privacy policy doesn’t say whether you use my personal data to train AI models. Do you? If
                you do, how can I opt out? Please answer in writing. Thank you.
              </p>
              <p className="l-small">
                Keep a copy of what you send and any reply. If you live somewhere with a right of access, you can also
                ask for a copy of the data the company holds about you, which often answers the question.
              </p>
            </Section>
          </div>
        </div>
      </div>
    </Page>
  )
}
