import type { Metadata } from "next"
import { Suspense } from "react"
import { BottomBar, Masthead } from "@/components/home/chrome"
import SearchBest from "@/components/home/SearchBest"
import { search } from "@/lib/api"
import "@/components/home/home.css"
import "@/components/home/pages.css"
import "@/components/home/search.css"

// Results change with every query, so they are kept out of search engines;
// the reports they link to are indexed instead.
export const metadata: Metadata = {
  title: "Search · Imbroglio",
  description: "Find a site’s privacy rating by its name or address.",
  robots: { index: false, follow: true },
}

type Params = PageProps<"/search">["searchParams"]

// one query, capped: anything longer than a domain can be is not a search
async function query(searchParams: Params) {
  const raw = (await searchParams).q
  return (Array.isArray(raw) ? raw[0] : raw ?? "").trim().slice(0, 253)
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="none">
      <p className="mono eyebrow">Search</p>
      <h1>{children}</h1>
    </div>
  )
}

function Box({ q = "" }: { q?: string }) {
  return (
    <form action="/search" className="search find-box" role="search">
      <label className="sr-only" htmlFor="q-find">
        Search a site or service
      </label>
      <input id="q-find" name="q" defaultValue={q} placeholder="Search a site or service" autoComplete="off" />
      <button type="submit" aria-label="Search">
        ↵
      </button>
    </form>
  )
}

async function Results({ searchParams }: { searchParams: Params }) {
  const q = await query(searchParams)
  if (!q) return <Note>Type a service or website above.</Note>
  const data = await search(q).catch(() => null)
  if (!data) return <Note>Search is unavailable right now. Try again in a minute.</Note>
  return <SearchBest query={q} results={data.results} canRequest={data.can_request} />
}

async function Head({ searchParams }: { searchParams: Params }) {
  return <Masthead search={<Box q={await query(searchParams)} />} />
}

export default function SearchPage({ searchParams }: PageProps<"/search">) {
  return (
    <div className="home page find">
      <Suspense fallback={<Masthead search={<Box />} />}>
        <Head searchParams={searchParams} />
      </Suspense>
      <main className="page-main" id="main">
        <Suspense fallback={<Note>Searching…</Note>}>
          <Results searchParams={searchParams} />
        </Suspense>
      </main>
      <BottomBar />
    </div>
  )
}
