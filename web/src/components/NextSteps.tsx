import Link from "next/link"
import type { Site } from "@/lib/api"
import { buildNextSteps, type NextStep } from "@/lib/nextSteps"
import CopyRequest from "./CopyRequest"
import { ratingOf } from "./design"

// "Your next steps on {domain}", under the category breakdown. The steps come
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
        Your next steps on {site.domain}
      </h2>
      <p className="mt-1 text-sm text-[#5a6b7e]">Built from what this report found. Most important first.</p>
      {built.nothingConcerning && (
        <p className="mt-3 text-[15px] leading-6 text-[#364b63]">Nothing in this report took points off.</p>
      )}
      <ol className="mt-3">
        {built.steps.map((step, i) => (
          <StepItem key={step.key} step={step} n={i + 1} domain={site.domain} />
        ))}
      </ol>
    </section>
  )
}

function StepItem({ step, n, domain }: { step: NextStep; n: number; domain: string }) {
  const a = step.action
  return (
    <li className="flex gap-3.5 border-t border-[#e5e9ed] py-4">
      <span
        aria-hidden="true"
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
          step.general ? "bg-[#e9edf2] text-[#183149]" : "bg-[#183149] text-white"
        }`}
      >
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="font-semibold text-[#102338]">{step.title}</h3>
        <p className={`mt-1 max-w-3xl text-[15px] leading-6 ${step.general ? "text-[#5a6b7e]" : "text-[#364b63]"}`}>
          {step.body.join(" ")}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
          {a.kind === "copy" ? (
            <CopyRequest request={a.request} />
          ) : a.onSite ? (
            <span className="py-2.5 text-[#5a6b7e]">
              On {domain}:{" "}
              <a
                href={a.href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-[#315f91] underline decoration-[#cbd3db] underline-offset-4 hover:text-[#173b5c]"
              >
                {a.text}
              </a>
            </span>
          ) : (
            <Link
              href={a.href}
              className="inline-flex min-h-11 items-center font-medium text-[#315f91] underline decoration-[#cbd3db] underline-offset-4 hover:text-[#173b5c]"
            >
              {a.text}
            </Link>
          )}
          <span className="order-last w-full text-xs text-[#68778a]">
            {step.from.length > 0
              ? `From: ${step.from.map((f) => `${f.name} (${ratingOf[f.tier]})`).join(" and ")}`
              : "Works on every site"}
          </span>
        </div>
      </div>
    </li>
  )
}
