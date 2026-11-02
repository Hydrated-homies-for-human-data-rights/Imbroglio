import type { Metadata } from "next"
import { Suspense } from "react"
import Page, { Chapter } from "@/components/home/Page"
import ReportForm from "@/components/home/ReportForm"

export const metadata: Metadata = {
  title: "Report a problem · Imbroglio",
  description: "Tell us a rating, finding or quote on imbroglio.io is wrong. A team member rereads it against the stored document.",
}

// The published correction path (proposal risk 8). Every report is stored
// for the team to reread against the stored document: see the API's
// POST /v1/reports and the `reports` CLI command.
type Params = Promise<Record<string, string | string[] | undefined>>

// The site comes from the query string, which is only known per request, so
// it is read inside Suspense and the rest of the page is prerendered.
async function PrefilledForm({ searchParams }: { searchParams: Params }) {
  const sp = await searchParams
  const site = typeof sp.site === "string" ? sp.site.slice(0, 253) : ""
  return <ReportForm site={site} page={site ? `/site/${site}` : ""} />
}

export default function ReportPage({ searchParams }: { searchParams: Params }) {
  return (
    <Page
      current="/report"
      eyebrow="If we got something wrong"
      title="Report a problem."
      lede="A rating, a finding, a quote, a site we read wrong. A team member rereads it against the stored document, and if the quote doesn’t support the finding, we withdraw it."
    >
      <Chapter title="What happened" wide>
        <Suspense fallback={<ReportForm />}>
          <PrefilledForm searchParams={searchParams} />
        </Suspense>
      </Chapter>
      <Chapter title="What we do with it">
        <p>
          Reports are read by a person. We compare the finding with the sentence it quotes in the stored copy of
          the document, the same copy the rating was made from. A finding whose quote doesn’t hold is withdrawn
          and the rating is recomputed from the findings that remain.
        </p>
        <p>
          We keep what you write and, if you give it, your email address, so we can tell you what we found.
          Nothing from this form is shown on the site.
        </p>
      </Chapter>
    </Page>
  )
}
