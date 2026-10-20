import { Suspense } from "react"
import Header from "@/components/Header"
import { getSite } from "@/lib/api"
import { docName, shortDate } from "@/lib/format"

// The design's change-history timeline needs a per-change API (which rating
// moved, before/after quotes) that doesn't exist yet. Until it does, this page
// keeps the design's header and says plainly what we have.
async function HistoryHeader({ params }: { params: PageProps<"/site/[domain]/history">["params"] }) {
  return <Header view="history" serviceName={decodeURIComponent((await params).domain)} />
}

async function History({ params }: { params: PageProps<"/site/[domain]/history">["params"] }) {
  const domain = decodeURIComponent((await params).domain)
  let site
  try {
    site = await getSite(domain)
  } catch {
    return <p>The analysis service is unavailable right now.</p>
  }
  if (!site.documents.length) return <p>We have no documents stored for {domain}.</p>
  const changes = site.documents.reduce((n, d) => n + d.changes_detected, 0)
  return (
    <>
      <h1 className="sr-only">Change history for {domain}</h1>
      <p>
        {changes === 0
          ? `No changes detected in ${domain}'s documents yet.`
          : `${changes} change${changes === 1 ? "" : "s"} detected. A detailed timeline is coming soon.`}
      </p>
      <ul className="mt-2 list-disc pl-5">
        {site.documents.map((d) => (
          <li key={d.type}>
            {docName(d.type)}: {d.versions_stored} version{d.versions_stored === 1 ? "" : "s"} stored, last checked{" "}
            {shortDate(d.fetched_at)}
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
      <main className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8 sm:py-9 text-sm">
        <Suspense fallback={<p>Loading…</p>}>
          <History params={params} />
        </Suspense>
      </main>
    </>
  )
}
