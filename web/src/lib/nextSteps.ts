import type { CategoryScore, Evidence, Site, SiteLink, Tier } from "@/lib/api"

// "What you can do on {domain}" on a report: a short list of options, most
// important first, built only from what the report already has. Nothing
// here is written about one site. The site-specific parts are the
// categories and their tiers, each category's top finding in the rubric's
// own plain words, and the links stored for the site (Site.links). Kept
// free of React so it is easy to read and to check by hand.

export type NextStepAction =
  // the site's own page for it
  | { kind: "link"; href: string; text: string }
  // no page found, so a short request the reader can copy and send
  | { kind: "copy"; request: string; label: string }

export type NextStep = {
  key: string
  // the category it came from, shown above the title; null for the step
  // that works on every site
  from: { name: string; tier: Tier } | null
  // "If you want ...": an option, never an order
  title: string
  // one to three plain sentences
  body: string[]
  // what to do on this site; null when the guide is the whole step
  action: NextStepAction | null
  // where on /learn this is explained, in words that say where it goes
  guide: { href: string; text: string }
  // the general step at the end, shown lighter
  general?: boolean
}

export type NextSteps = {
  steps: NextStep[]
  // nothing in the report took points off
  nothingConcerning: boolean
}

// At most this many steps about the site, before the general one.
export const MAX_SITE_STEPS = 4

const CONCERNING: Partial<Record<Tier, number>> = { SEVERE: 0, EXTENSIVE: 1, MODERATE: 2 }
const CONCERN_RANK: Record<string, number> = { severe: 3, high: 2, medium: 1, info: 0 }

// Where /learn explains Global Privacy Control, browser by browser.
export const GPC_LEARN = "/learn#gpc"
export const RIGHTS_LEARN = "/learn#rights"

const DELETION = "deletion_on_request"
const ACCESS = "access_and_export"

// Per category: the option it offers, what to ask for when the site has no
// page of its own (`confirm` adds a line asking them to confirm it's done),
// the copy button's words, the right it is about (its answer is always said,
// document by document when they disagree) and its guide on /learn.
type CategoryStep = {
  title: string
  request: string
  confirm: boolean
  copy: string
  right?: string
  guide: { href: string; text: string }
}
const CATEGORY_STEPS: Record<string, CategoryStep> = {
  selling_sharing: {
    title: "If you don’t want them selling or sharing your data",
    request: "Please do not sell or share my personal information, including with advertising partners.",
    confirm: true,
    copy: "Copy an opt-out request to send them",
    guide: { href: "/learn#sells_personal_data", text: "Guide: opting out of the sale of your data" },
  },
  ai_training: {
    title: "If you don’t want your content training their AI",
    request: "Please do not use my content or personal information to train AI models.",
    confirm: true,
    copy: "Copy a request to send them",
    guide: { href: "/learn#trains_ai_on_user_data", text: "Guide: keeping your content out of AI training" },
  },
  retention: {
    title: "If you want your data deleted",
    request: "Please delete the personal information you hold about me.",
    confirm: true,
    copy: "Copy a deletion request to send them",
    right: DELETION,
    guide: {
      href: "/learn#deletion_on_request",
      text: "Guide: how a deletion request works, and what to do if they say no",
    },
  },
  collection: {
    title: "If you want to know what they hold about you",
    request: "Please tell me what personal information you hold about me, and where it came from.",
    confirm: false,
    copy: "Copy a request to send them",
    guide: { href: "/learn#access_and_export", text: "Guide: asking a site what it holds about you" },
  },
  user_rights: {
    title: "If you want a copy of your data",
    request: "Please send me a copy of the personal information you hold about me.",
    confirm: false,
    copy: "Copy a request for your data",
    right: ACCESS,
    guide: { href: RIGHTS_LEARN, text: "Guide: which rights you have where you live" },
  },
  security: {
    title: "If you want to know how they protect your data",
    request:
      "Please tell me how you protect my personal information, and whether you will tell me if it is part of a data breach.",
    confirm: false,
    copy: "Copy a request to send them",
    guide: { href: "/learn#security_measures", text: "Guide: protecting your accounts when security is vague" },
  },
  government: {
    title: "If you want to know about government requests",
    request:
      "Please tell me whether you will let me know when a government or the police ask for my data, where the law allows it.",
    confirm: false,
    copy: "Copy a request to send them",
    guide: { href: "/learn#discloses_to_government", text: "Guide: what to do about government requests" },
  },
  terms: {
    title: "If you want to know your options under the terms",
    request: "Please tell me what choices I have under your terms, including any way to opt out of arbitration.",
    confirm: false,
    copy: "Copy a request to send them",
    guide: { href: "/learn#findings", text: "Guide: what to do about each finding" },
  },
}
const OTHER_STEP: CategoryStep = {
  title: "If you want to know your options",
  request: "Please tell me what choices I have about how you handle my personal information.",
  confirm: false,
  copy: "Copy a request to send them",
  guide: { href: "/learn#findings", text: "Guide: what to do about each finding" },
}

const sentence = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`)
const said = (f: Evidence) => sentence(f.plain ?? f.meaning)
// "Anyone can ask..." -> "anyone can ask...", but "EU users..." stays as is
const lowerFirst = (s: string) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s)
// how each document is named in a sentence, with its verb
const DOC_SAYS: Record<string, string> = { privacy: "Their privacy policy says", terms: "Their terms say" }

// A short, polite request in plain words, ready to paste into an email.
export function requestText(categoryKey: string, domain: string): string {
  const c = CATEGORY_STEPS[categoryKey] ?? OTHER_STEP
  return [
    "Hello,",
    "",
    `I use ${domain}. ${c.request}${c.confirm ? " Please confirm when this is done." : ""}`,
    "",
    "Thank you.",
  ].join("\n")
}

// The finding that weighs most in a category: highest concern, then most
// exposure, then the first one listed.
function topFinding(category: CategoryScore): Evidence | null {
  let top: Evidence | null = null
  for (const f of category.findings) {
    if (
      !top ||
      (CONCERN_RANK[f.concern ?? ""] ?? 0) > (CONCERN_RANK[top.concern ?? ""] ?? 0) ||
      ((CONCERN_RANK[f.concern ?? ""] ?? 0) === (CONCERN_RANK[top.concern ?? ""] ?? 0) && f.exposure > top.exposure)
    )
      top = f
  }
  return top
}

// What the documents say about one question. One sentence when they agree;
// when the privacy policy and the terms answer differently, one sentence
// for each, naming the document, so the box never contradicts itself.
// Silence ("not disclosed") isn't an answer and is left out.
function answers(findings: Evidence[], checkId: string): string[] {
  const said_ = findings.filter((f) => f.check_id === checkId && f.status !== "not_disclosed")
  if (said_.length === 0) return []
  if (new Set(said_.map((f) => f.status)).size === 1) return [said(said_[0])]
  return said_.map((f) => `${DOC_SAYS[f.document] ?? `Their ${f.document} says`} ${lowerFirst(said(f))}`)
}

const linkFor = (site: Site, key: string): SiteLink | undefined => (site.links ?? []).find((l) => l.category === key)

// Harvested link text sometimes keeps the quote marks around it on the page.
const unquote = (s: string) => s.trim().replace(/^['"‘“]+|['"’”]+$/g, "").trim() || s
const onSite = (l: SiteLink): NextStepAction => ({ kind: "link", href: l.url, text: unquote(l.text) })

// One option per topic: what the report found, what the reader can do on
// this site, and where /learn explains it.
function stepFor(site: Site, category: CategoryScore, findings: Evidence[], top: Evidence | null): NextStep {
  const c = CATEGORY_STEPS[category.key] ?? OTHER_STEP
  const link = linkFor(site, category.key)
  const right = c.right ? answers(findings, c.right) : []
  const body = [...(top && top.check_id !== c.right ? [said(top)] : []), ...right]
  if (right.length > 1 && !link) body.push("You can ask either way.")
  return {
    key: category.key,
    from: { name: category.name, tier: category.tier },
    title: c.title,
    body,
    action: link ? onSite(link) : { kind: "copy", request: requestText(category.key, site.domain), label: c.copy },
    guide: c.guide,
  }
}

export function buildNextSteps(site: Site): NextSteps | null {
  const card = site.scorecard
  // no box for a site that isn't rated
  if (!card || card.headline === "UNCLEAR" || card.headline === "NOT_DISCLOSED") return null

  // Points each category lost, to order categories of the same tier.
  const points = new Map<string, number>()
  for (const d of card.score?.deductions ?? []) points.set(d.category, (points.get(d.category) ?? 0) + d.points)
  const weight = (c: CategoryScore) =>
    points.get(c.key) ?? c.findings.reduce((sum, f) => sum + Math.max(0, f.exposure), 0)

  const concerning = card.categories
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => CONCERNING[c.tier] !== undefined)
    .sort((a, b) => CONCERNING[a.c.tier]! - CONCERNING[b.c.tier]! || weight(b.c) - weight(a.c) || a.i - b.i)
    .map(({ c }) => c)

  const steps: NextStep[] = concerning.map((category) =>
    stepFor(site, category, category.findings, topFinding(category)),
  )

  // A right the documents grant to anyone (the protective answer,
  // "all_users"), in a category that has no step of its own: still worth
  // knowing about. Rights already covered by a step are said there.
  const covered = new Set(steps.map((s) => s.key))
  for (const key of ["retention", "user_rights"]) {
    const category = card.categories.find((c) => c.key === key)
    const right = CATEGORY_STEPS[key].right!
    if (!category || covered.has(key)) continue
    const grants = category.findings.some((f) => f.check_id === right && f.status === "all_users" && f.exposure === 0)
    if (grants) steps.push(stepFor(site, category, category.findings, null))
  }

  const shown = steps.slice(0, MAX_SITE_STEPS)
  shown.push({
    key: "gpc",
    from: null,
    title: "If you want to tell every site not to sell your data",
    body: [
      "Global Privacy Control is a browser setting that tells every site you visit not to sell or share your data.",
      "In several US states, businesses must honor it.",
    ],
    action: null,
    guide: { href: GPC_LEARN, text: "Turn it on: steps for Chrome, Firefox, Safari, Edge and Brave" },
    general: true,
  })

  return { steps: shown, nothingConcerning: concerning.length === 0 }
}
