import Link from "next/link"
import { SearchIcon } from "./design"

// Header from the UX team's design. The search box is a plain GET form to
// /search, so it works without JavaScript.
export default function Header({
  view,
  serviceName = "",
  query = "",
}: {
  view: "report" | "results" | "history"
  serviceName?: string
  query?: string
}) {
  return (
    <header className="border-b border-[#dbe1e7] bg-[rgb(247,154,192)]">
      <div className="mx-auto flex min-h-[72px] max-w-[1180px] items-center gap-5 px-5 py-3 sm:px-8">
        <Link
          href="/"
          className="shrink-0 text-[28px] font-bold tracking-[-0.03em] text-black"
          style={{ fontSize: "28px", fontWeight: 700 }}
          aria-label="Imbroglio home"
        >
          imbroglio<span className="text-[#d64d3f]">.</span>
        </Link>

        {view === "history" ? (
          <nav className="flex min-w-0 items-center gap-3 text-sm" aria-label="Breadcrumb">
            <Link
              href={`/site/${encodeURIComponent(serviceName)}`}
              className="truncate font-medium text-black hover:text-[#173c63]"
            >
              {serviceName}
            </Link>
            <span className="text-[#9aa5b1]">›</span>
            <span className="shrink-0 text-black">Change history</span>
          </nav>
        ) : (
          <form action="/search" className="ml-auto flex w-full max-w-[620px] gap-2">
            <label className="relative block flex-1">
              <span className="sr-only">Search services</span>
              {view === "report" && (
                <span className="pointer-events-none absolute inset-y-0 left-4 z-10 flex items-center text-[#8995a3]">
                  <SearchIcon />
                </span>
              )}
              <input
                name="q"
                defaultValue={query}
                placeholder="Search a service or website"
                className={`h-11 w-full rounded-full border border-[#cfd7df] bg-white pr-4 text-sm text-[#142a3f] outline-none transition placeholder:text-[#8995a3] focus:border-[#74879a] focus:ring-4 focus:ring-[#dfe8ef] ${
                  view === "report" ? "pl-11" : "pl-5"
                }`}
              />
            </label>
            <button
              type="submit"
              className="flex h-11 min-w-[76px] items-center justify-center rounded-full bg-[#172635] px-5 text-sm font-semibold text-white transition hover:bg-[#25445e] focus:outline-none focus:ring-4 focus:ring-[#cbd7e1]"
            >
              {view === "results" ? "Go" : "Search"}
            </button>
          </form>
        )}
      </div>
    </header>
  )
}
