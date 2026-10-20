import Link from "next/link"
import Header from "@/components/Header"

// The design doesn't have a home page yet: plain until the UX team designs one.
export default function Home() {
  return (
    <>
      <Header view="report" />
      <main className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 text-sm">
        <p>Search a service or website above to see its privacy report.</p>
        <p className="mt-2">
          <Link className="underline" href="/learn">
            What can you do?
          </Link>
        </p>
      </main>
    </>
  )
}
