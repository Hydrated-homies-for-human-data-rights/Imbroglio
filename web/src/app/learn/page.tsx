import { connection } from "next/server"
import { Suspense } from "react"
import Header from "@/components/Header"
import { getLearn } from "@/lib/api"

// Not in the design yet: plain until the UX team designs it. Each topic's id
// is its rubric check_id, which scorecard findings link to (/learn#<check_id>).
async function Topics() {
  await connection() // read at request time, never baked in at build
  let learn
  try {
    learn = await getLearn()
  } catch {
    return <p>This page is unavailable right now.</p>
  }
  return (
    <>
      <h2 className="mt-6 text-base font-bold">About a finding</h2>
      {learn.topics.map((t) => (
        <section key={t.check_id} id={t.check_id} className="mt-4 scroll-mt-4">
          <h3 className="font-bold">{t.title}</h3>
          <p className="text-xs">
            {t.category} · {t.question}
          </p>
          <p className="mt-1">{t.why}</p>
          <ul className="mt-1 list-disc pl-5">
            {t.steps.map((s) => (
              <li key={s.text}>
                {s.text}{" "}
                {s.link && (
                  <a className="underline" href={s.link} target="_blank" rel="noopener noreferrer">
                    link
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
      <h2 className="mt-8 text-base font-bold">Protecting yourself in general</h2>
      {learn.guides.map((g) => (
        <section key={g.id} id={g.id} className="mt-4 scroll-mt-4">
          <h3 className="font-bold">{g.title}</h3>
          <p className="mt-1">{g.body}</p>
        </section>
      ))}
    </>
  )
}

export default function LearnPage() {
  return (
    <>
      <Header view="report" />
      <main className="mx-auto max-w-[1180px] px-5 py-10 sm:px-8 text-sm">
        <h1 className="text-xl font-bold">What can you do?</h1>
        <Suspense fallback={<p>Loading…</p>}>
          <Topics />
        </Suspense>
      </main>
    </>
  )
}
