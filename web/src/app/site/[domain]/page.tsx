import { Suspense } from "react"
import Header from "@/components/Header"
import Report from "@/components/Report"
import RequestForm from "@/components/RequestForm"
import { ApiError, getSite } from "@/lib/api"
import { shortDate } from "@/lib/format"

// States other than a finished report aren't in the design yet, so they're
// plain text until the UX team designs them.
function Plain({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 text-sm">{children}</main>
}

async function SiteContent({ params }: { params: PageProps<"/site/[domain]">["params"] }) {
  const domain = decodeURIComponent((await params).domain)
  let site
  try {
    site = await getSite(domain)
  } catch (e) {
    if (e instanceof ApiError && e.status === 400) return <Plain>“{domain}” isn’t a valid website address.</Plain>
    return <Plain>The analysis service is unavailable right now. Try again in a minute.</Plain>
  }
  if (site.scorecard) return <Report site={site} />

  if (site.state === "queued" || site.state === "analyzing") {
    const ahead = site.pending_request?.queue_ahead ?? 0
    return (
      <Plain>
        <p>
          {site.domain} is being analyzed{site.state === "queued" && ahead > 0 ? ` (${ahead} ahead in the queue)` : ""}.
          Most sites take under a minute. Reload this page to check.
        </p>
      </Plain>
    )
  }
  if (site.state === "no_policy_found") {
    return (
      <Plain>
        <p>
          We couldn’t find a privacy policy or terms of service for {site.domain}.
          {site.recheck_after ? ` We’ll look again after ${shortDate(site.recheck_after)}.` : ""}
        </p>
        <p className="mt-2">If you know where its policy is, paste the link:</p>
        <RequestForm />
      </Plain>
    )
  }
  if (site.state === "ready") {
    return (
      <Plain>
        <p>We found {site.documents.length === 2 ? "both documents" : "a document"} for {site.domain}; the report is being prepared.</p>
      </Plain>
    )
  }
  return (
    <Plain>
      <p>We haven’t analyzed {site.domain} yet.</p>
      <RequestForm initial={site.domain} />
    </Plain>
  )
}

export default function SitePage({ params }: PageProps<"/site/[domain]">) {
  return (
    <>
      <Header view="report" />
      <Suspense fallback={<Plain>Loading…</Plain>}>
        <SiteContent params={params} />
      </Suspense>
    </>
  )
}
