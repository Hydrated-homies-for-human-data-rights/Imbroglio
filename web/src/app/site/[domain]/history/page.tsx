import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { Suspense, cache } from "react"
import Header from "@/components/Header"
import { getSite } from "@/lib/api"
import { cleanDomain, docName, shortDate } from "@/lib/format"

// One fetch per request, shared by the page and its metadata.
const loadSite = cache(getSite)

// The address in the URL, cleaned the way the API cleans it, so the page
// never echoes arbitrary text from a link. Anything that isn't a domain is
// a 404 (site/[domain]/not-found.tsx).
async function domainOf(params: PageProps<"/site/[domain]/history">["params"]): Promise<string> {
  let raw: string
  try {
    raw = decodeURIComponent((await params).domain)
  } catch {
    notFound()
  }
  return cleanDomain(raw) ?? notFound()
}

export async function generateMetadata({ params }: PageProps<"/site/[domain]/history">): Promise<Metadata> {
  const domain = await domainOf(params)
  // nothing stored: no page (checked here too, which crawlers get first)
  const site = await loadSite(domain).catch(() => null)
  if (site && !site.documents.length) notFound()
  return {
    title: `${domain} change history · Imbroglio`,
    description: `Every version of ${domain}’s privacy policy and terms we have stored, and when we last checked them.`,
    alternates: { canonical: `/site/${encodeURIComponent(domain)}/history` },
  }
}

// The design's change-history timeline needs a per-change API (which rating
// moved, before/after quotes) that doesn't exist yet. Until it does, this page
// keeps the design's header and says plainly what we have.
async function HistoryHeader({ params }: { params: PageProps<"/site/[domain]/history">["params"] }) {
  return <Header view="history" serviceName={await domainOf(params)} />
}

async function History({ params }: { params: PageProps<"/site/[domain]/history">["params"] }) {
  const domain = await domainOf(params)
  const heading = <h1 className="sr-only">Change history for {domain}</h1>
  let site
  try {
    site = await loadSite(domain)
  } catch {
    return (
      <>
        {heading}
        <p>The analysis service is unavailable right now.</p>
      </>
    )
  }
  // nothing stored: there is no history page for it
  if (!site.documents.length) notFound()
  const changes = site.documents.reduce((n, d) => n + d.changes_detected, 0)
  return (
    <>
      {heading}
      <p>
        {changes === 0
          ? `No changes detected in ${domain}'s documents yet.`
          : `${changes} change${changes === 1 ? "" : "s"} detected. A detailed timeline is coming soon.`}
      </p>
      <ul className="mt-2 list-disc pl-5">
        {site.documents.map((d) => (
          <li key={d.type}>
            {/* last checked: the newest read of the document at its address,
                not when the version shown was first stored (fetched_at) */}
            {docName(d.type)}: {d.versions_stored} version{d.versions_stored === 1 ? "" : "s"} stored, last checked{" "}
            {shortDate(d.checked_at ?? d.fetched_at)}
          </li>
        ))}
      </ul>
    </>
  )
}

export default function HistoryPage({ params }: PageProps<"/site/[domain]/history">) {
  return (
    <>
      <Suspense fallback={<Header view="history" />}>
        <HistoryHeader params={params} />
      </Suspense>
      <main id="main" className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8 sm:py-9 text-sm">
        <Suspense fallback={<p>Loading…</p>}>
          <History params={params} />
        </Suspense>
      </main>
    </>
  )
}
