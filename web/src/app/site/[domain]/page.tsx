import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { Suspense, cache } from "react"
import Header from "@/components/Header"
import Report from "@/components/Report"
import RequestForm from "@/components/RequestForm"
import RequestProgress from "@/components/RequestProgress"
import { ApiError, getSite, type Site } from "@/lib/api"
import { FALLBACK_MESSAGE, linkCanHelp, nextStep } from "@/lib/failure"
import { cleanDomain, shortDate } from "@/lib/format"

// One fetch per request, shared by the page and its metadata.
const loadSite = cache(getSite)

const TIER_WORD: Record<string, string> = {
  SEVERE: "Severe", EXTENSIVE: "Extensive", MODERATE: "Moderate", LIMITED: "Limited",
  NOT_DISCLOSED: "Not disclosed", UNCLEAR: "Unclear",
}

// The title and description a shared link shows, next to the preview image
// (opengraph-image.tsx): the rating and score, and what took points off.
function describe(site: Site | null, domain: string): { title: string; description: string } {
  const card = site?.scorecard
  if (!card) {
    return {
      title: `${domain} privacy report · Imbroglio`,
      description: `What ${domain}’s privacy policy and terms let it do with your data, with the quotes behind every rating.`,
    }
  }
  const rating = `${TIER_WORD[card.headline] ?? card.headline}${card.score ? `, ${card.score.value}/100` : ""}`
  // "User data ... AI models" reads mid-sentence as "user data ... AI models"
  const flags = card.score?.deductions.slice(0, 2).map((d) => {
    const text = (d.plain ?? d.meaning).replace(/\.$/, "")
    return text.charAt(0).toLowerCase() + text.slice(1)
  }) ?? []
  return {
    title: `${domain}: ${rating} · Imbroglio`,
    description: flags.length
      ? `${domain} is rated ${rating}. Points off: ${flags.join("; ")}. Every finding quotes its own policy.`
      : `${domain} is rated ${rating}. Every finding quotes its own policy, checked word for word.`,
  }
}

// The address in the URL, cleaned the way the API cleans it, so the title,
// preview and page never echo arbitrary text from a link. Anything that
// isn't a domain is a 404.
async function domainOf(params: PageProps<"/site/[domain]">["params"]): Promise<string> {
  let raw: string
  try {
    raw = decodeURIComponent((await params).domain)
  } catch {
    notFound()
  }
  return cleanDomain(raw) ?? notFound()
}

// A site we know nothing about has no page: a real 404 (not-found.tsx here
// offers to analyze it), so search engines never index an empty report.
// Checked in the metadata too, which crawlers get before the page streams.
const isUnknown = (site: Site | null) => site?.state === "unknown"

export async function generateMetadata({ params }: PageProps<"/site/[domain]">): Promise<Metadata> {
  const domain = await domainOf(params)
  const site = await loadSite(domain).catch(() => null)
  if (isUnknown(site)) notFound()
  const { title, description } = describe(site, domain)
  const url = `/site/${encodeURIComponent(domain)}`
  return { title, description, alternates: { canonical: url }, openGraph: { title, description, url } }
}

// States other than a finished report aren't in the design yet, so they're
// plain text until the UX team designs them. The heading is for screen
// readers; the report itself has a visible one.
function Plain({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 text-sm">
      <h1 className="sr-only">{title}</h1>
      {children}
    </main>
  )
}

async function SiteContent({ params }: { params: PageProps<"/site/[domain]">["params"] }) {
  const domain = await domainOf(params)
  const title = `${domain} privacy report`
  let site
  try {
    site = await loadSite(domain)
  } catch (e) {
    // the API refuses it as a website address: there is no such page
    if (e instanceof ApiError && e.status === 400) notFound()
    return <Plain title={title}>The analysis service is unavailable right now. Try again in a minute.</Plain>
  }
  if (site.scorecard) return <Report site={site} />
  if (isUnknown(site)) notFound()

  if (site.state === "queued" || site.state === "analyzing") {
    // The progress box polls the request and refreshes this page when the
    // report is ready, so the reader never has to reload by hand.
    return (
      <Plain title={title}>
        <p>{site.domain} is being analyzed.</p>
        {site.pending_request ? (
          <RequestProgress id={site.pending_request.id} domain={site.domain} />
        ) : (
          <p className="mt-2">Most sites take one to three minutes. Reload this page to check.</p>
        )}
      </Plain>
    )
  }
  if (site.state === "no_policy_found") {
    // Nothing re-queues a site by itself: after recheck_after, a new request
    // crawls it again instead of answering from the last try.
    const failure = site.failure
    return (
      <Plain title={title}>
        <p>
          {site.domain}: {failure?.message ?? FALLBACK_MESSAGE}
        </p>
        <p className="mt-2">
          {nextStep(failure?.reason)}
          {site.recheck_after
            ? ` You can ask us to look again after ${shortDate(site.recheck_after)}.`
            : " It’s been a while since we tried, so you can ask us to look again now."}
        </p>
        {failure && failure.tried.length > 0 && (
          <>
            <p className="mt-4">What we tried:</p>
            <ul className="mt-1 list-disc pl-5 text-[#5a6b7e]">
              {failure.tried.map((line) => (
                <li key={line} className="break-all">
                  {line}
                </li>
              ))}
            </ul>
          </>
        )}
        {!site.recheck_after ? (
          <>
            <p className="mt-4">Ask us to look again, or paste a link to its policy:</p>
            <RequestForm initial={site.domain} />
          </>
        ) : (
          linkCanHelp(failure?.reason) && (
            <>
              <p className="mt-4">If you know where its policy is, paste the link:</p>
              <RequestForm site={site.domain} />
            </>
          )
        )}
      </Plain>
    )
  }
  if (site.state === "ready") {
    // Stored but not rated yet: ratings are added in batches, so don't say a
    // report is on its way.
    const names = site.documents.map((d) => (d.type === "privacy" ? "privacy policy" : "terms of service"))
    return (
      <Plain title={title}>
        <p>
          We have {site.domain}’s {names.join(" and ")}, but {names.length === 1 ? "it hasn’t" : "they haven’t"} been
          rated yet.
        </p>
        <ul className="mt-2 list-disc pl-5">
          {site.documents.map((d) => (
            <li key={d.type}>
              <a className="underline" href={d.url} target="_blank" rel="noopener noreferrer">
                Read the {d.type === "privacy" ? "privacy policy" : "terms of service"}
              </a>
            </li>
          ))}
        </ul>
      </Plain>
    )
  }
  // no state the API reports today lands here; kept for one it adds later
  return (
    <Plain title={title}>
      <p>We haven’t analyzed {site.domain} yet.</p>
      <RequestForm initial={site.domain} />
    </Plain>
  )
}

export default function SitePage({ params }: PageProps<"/site/[domain]">) {
  return (
    <>
      <Header view="report" />
      <Suspense fallback={<Plain title="Privacy report">Loading…</Plain>}>
        <SiteContent params={params} />
      </Suspense>
    </>
  )
}
