// Visual building blocks copied from the UX team's Figma Make design
// (Website UX Design, src/App.tsx). Markup and classes are kept identical;
// only the data types are adapted to the API. Don't restyle here: design
// changes come from the Figma file.

import type { Tier } from "@/lib/api"

export type Rating = "Severe" | "Extensive" | "Moderate" | "Not disclosed" | "Limited"

export const ratingOf: Record<Tier, Rating> = {
  SEVERE: "Severe",
  EXTENSIVE: "Extensive",
  MODERATE: "Moderate",
  LIMITED: "Limited",
  NOT_DISCLOSED: "Not disclosed",
}

export const ratingStyles: Record<Rating, string> = {
  Severe: "text-[#b73329]",
  Extensive: "text-[#c76017]",
  Moderate: "text-[#546579]",
  "Not disclosed": "text-[#8b95a4]",
  Limited: "text-[#39704e]",
}

export function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5" fill="none">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 16 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function Chevron({ open = false }: { open?: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      className={`h-5 w-5 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
      fill="none"
    >
      <path
        d="m7.5 4.5 5.5 5.5-5.5 5.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function RatingMark({ rating }: { rating: Rating }) {
  if (rating === "Severe") {
    return <span className="h-4 w-4 rounded-[2px] bg-[#c34135]" />
  }
  if (rating === "Extensive") {
    return (
      <span className="h-0 w-0 border-x-[9px] border-b-[17px] border-x-transparent border-b-[#d36b20]" />
    )
  }
  if (rating === "Not disclosed") {
    return <span className="h-4 w-4 rounded-[3px] border-2 border-dashed border-[#99a4b2]" />
  }
  if (rating === "Limited") {
    return <span className="h-[18px] w-[18px] rounded-full border-2 border-[#4d8b65]" />
  }
  return <span className="h-4 w-4 rounded-full bg-[#697b8f]" />
}

export function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-5 w-5 text-[#2e8155]" fill="none">
      <path
        d="m3.5 10.2 4 4L16.8 5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-6 w-6" fill="none">
      <path
        d="M4 12h15M14 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function WarningIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="h-5 w-5" fill="none">
      <path d="M10 2.5 18 17H2L10 2.5Z" fill="currentColor" />
      <path d="M10 7v4.5M10 14.2v.2" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function DetailCard({
  tone,
  title,
  quotes,
  source,
  tag,
}: {
  tone: "orange" | "green"
  title: string
  quotes: string[]
  source: string
  tag: string
}) {
  const green = tone === "green"

  return (
    <article className="relative overflow-hidden rounded-xl border border-[#dfe4ea] bg-white px-5 py-5 shadow-[0_1px_2px_rgba(15,31,47,0.02)] sm:px-6">
      <div
        className={`absolute inset-y-0 left-0 w-1.5 ${green ? "bg-[#4c8a65]" : "bg-[#dc721f]"}`}
      />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h4 className="font-semibold text-[#102338]">{title}</h4>
          {quotes.map((quote) => (
            <p key={quote} className="mt-2 text-[15px] italic leading-6 text-[#364b63]">
              “{quote}”
            </p>
          ))}
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[#68778a]">
            <span>{source}</span>
            <span aria-hidden="true">·</span>
            <span className="text-[#28784c]">quote verified</span>
            <CheckIcon />
          </div>
        </div>
        <span
          className={`shrink-0 rounded-full border px-4 py-1.5 text-xs font-medium ${
            green
              ? "border-[#a9cfb7] bg-[#eef8f1] text-[#39714f]"
              : "border-[#ccd9e7] bg-[#f1f6fb] text-[#4a6079]"
          }`}
        >
          {tag}
        </span>
      </div>
    </article>
  )
}
