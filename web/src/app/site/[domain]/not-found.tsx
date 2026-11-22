"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import Header from "@/components/Header"
import RequestForm from "@/components/RequestForm"
import { cleanDomain } from "@/lib/format"

// A report or history page for a site we have nothing on. It is a 404, so
// search engines never index an empty report, but it still offers to
// analyze the site, as the page did before. The domain is read from the
// address and cleaned the way the API cleans it; anything that isn't a
// domain gets no form. Plain, like the report page's other states.
export default function SiteNotFound() {
  const segment = usePathname().split("/")[2] ?? ""
  let domain: string | null = null
  try {
    domain = cleanDomain(decodeURIComponent(segment))
  } catch {}

  return (
    <>
      <Header view="report" />
      <main id="main" className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 text-sm">
        <h1 className="sr-only">{domain ? `No report for ${domain}` : "Page not found"}</h1>
        {domain ? (
          <>
            <p>We haven’t analyzed {domain} yet.</p>
            <RequestForm initial={domain} />
          </>
        ) : (
          <p>
            That isn’t a website address we can look up. Search for the site above, or{" "}
            <Link className="underline" href="/sites">
              see every site we’ve rated
            </Link>
            .
          </p>
        )}
      </main>
    </>
  )
}
