import Link from "next/link"
import type { Site } from "@/lib/api"
import { buildNextSteps, type NextStep } from "@/lib/nextSteps"
import CopyRequest from "./CopyRequest"
import { ratingOf } from "./design"

// "What you can do on {domain}", under the category breakdown. Options,
// not orders: no numbers, and each one starts "If you want". The steps come
// from lib/nextSteps.ts; this only lays them out.
export default function NextSteps({ site, className = "" }: { site: Site; className?: string }) {
  const built = buildNextSteps(site)
  if (!built) return null

  return (
    <section
      aria-labelledby="next-steps"
      className={`rounded-2xl border-2 border-[#183149] bg-white px-5 pb-2 pt-5 sm:px-6 ${className}`}
    >
      <h2 id="next-steps" className="text-[19px] font-bold tracking-[-0.01em] text-[#0f253a]">
        What you can do on {site.domain}
      </h2>
      <p className="mt-1 text-sm text-[#5a6b7e]">
        Options that match what this report found. Use the ones that matter to you.
      </p>
      {built.nothingConcerning && (
        <p className="mt-3 text-[15px] leading-6 text-[#364b63]">Nothing in this report took points off.</p>
      )}
      <ul className="mt-3">
        {built.steps.map((step) => (
          <StepItem key={step.key} step={step} domain={site.domain} />
        ))}
      </ul>
    </section>
  )
}

const LINK =
  "font-medium text-[#315f91] underline decoration-[#cbd3db] underline-offset-4 hover:text-[#173b5c] hover:decoration-current"

function StepItem({ step, domain }: { step: NextStep; domain: string }) {
  const a = step.action
  return (
    <li className="border-t border-[#e5e9ed] py-[18px]">
      <p
        className={`text-[11px] font-bold uppercase tracking-[0.08em] ${
          step.general ? "text-[#667182]" : "text-[#55606f]"
        }`}
      >
        {step.from ? `${step.from.name} · ${ratingOf[step.from.tier]}` : "On every site"}
      </p>
      <h3 className="mt-1 font-semibold text-[#102338]">{step.title}</h3>
      {step.body.length > 0 && (
        <p className="mt-1 max-w-3xl text-[15px] leading-6 text-[#364b63]">{step.body.join(" ")}</p>
      )}
      {a && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {a.kind === "copy" ? (
            <>
              <CopyRequest request={a.request} label={a.label} />
              <span className="text-[13px] text-[#5a6b7e]">We didn’t find a page for this on {domain}.</span>
            </>
          ) : (
            <span className="text-[#5a6b7e]">
              On {domain}:{" "}
              <a href={a.href} target="_blank" rel="noopener noreferrer" className={LINK}>
                {a.text}
              </a>
            </span>
          )}
        </div>
      )}
      <Link href={step.guide.href} className={`mt-2 inline-flex min-h-11 items-center text-sm sm:min-h-0 ${LINK}`}>
        {step.guide.text} <span aria-hidden="true">&nbsp;→</span>
      </Link>
    </li>
  )
}
