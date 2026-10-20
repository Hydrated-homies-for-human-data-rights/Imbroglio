import { Suspense } from "react"
import Header from "@/components/Header"
import SearchResults from "@/components/SearchResults"
import { search } from "@/lib/api"

async function Results({ searchParams }: { searchParams: PageProps<"/search">["searchParams"] }) {
  const raw = (await searchParams).q
  const q = (Array.isArray(raw) ? raw[0] : raw ?? "").trim()
  if (!q) return <main className="mx-auto max-w-[1180px] px-5 py-7 sm:px-8 text-sm">Type a service or website above.</main>
  const data = await search(q).catch(() => null)
  if (!data) return <main className="mx-auto max-w-[1180px] px-5 py-7 sm:px-8 text-sm">Search is unavailable right now.</main>
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
      <Suspense fallback={<main className="mx-auto max-w-[1180px] px-5 py-7 sm:px-8 text-sm">Searching…</main>}>
        <Results searchParams={searchParams} />
      </Suspense>
    </>
  )
}
