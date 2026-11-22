import type { Metadata } from "next"
import { Suspense } from "react"
import Header from "@/components/Header"
import SearchResults from "@/components/SearchResults"
import { search } from "@/lib/api"

// Results change with every query, so they are kept out of search engines;
// the reports they link to are indexed instead.
export const metadata: Metadata = {
  title: "Search · Imbroglio",
  description: "Find a site’s privacy rating by its name or address.",
  robots: { index: false, follow: true },
}

// The states other than a list of results: plain text, as before, with the
// page's heading for screen readers.
function Note({ children }: { children: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto max-w-[1180px] px-5 py-7 sm:px-8 text-sm">
      <h1 className="sr-only">Search</h1>
      {children}
    </main>
  )
}

async function Results({ searchParams }: { searchParams: PageProps<"/search">["searchParams"] }) {
  const raw = (await searchParams).q
  // one query, capped: anything longer than a domain can be is not a search
  const q = (Array.isArray(raw) ? raw[0] : raw ?? "").trim().slice(0, 253)
  if (!q) return <Note>Type a service or website above.</Note>
  const data = await search(q).catch(() => null)
  if (!data) return <Note>Search is unavailable right now.</Note>
  return <SearchResults searchTerm={q} results={data.results} canRequest={data.can_request} />
}

async function SearchHeader({ searchParams }: { searchParams: PageProps<"/search">["searchParams"] }) {
  const raw = (await searchParams).q
  return <Header view="results" query={Array.isArray(raw) ? raw[0] : raw ?? ""} />
}

export default function SearchPage({ searchParams }: PageProps<"/search">) {
  return (
    <>
      <Suspense fallback={<Header view="results" />}>
        <SearchHeader searchParams={searchParams} />
      </Suspense>
      <Suspense fallback={<Note>Searching…</Note>}>
        <Results searchParams={searchParams} />
      </Suspense>
    </>
  )
}
