import type { CategoryScore, Evidence, Site, SiteLink, Tier } from "@/lib/api"

// "Your next steps" on a report: a short, ordered list of things to do,
// built only from what the report already has. Nothing here is written
// about one site. The site-specific parts are the categories and their
// tiers, each category's top finding in the rubric's own plain words, and
// the links stored for the site (Site.links). Kept free of React so it is
// easy to read and to check by hand.

export type NextStepAction =
  // a page: the site's own, or one of ours
  | { kind: "link"; href: string; text: string; onSite: boolean }
  // no page found, so a short request the reader can copy and send
  | { kind: "copy"; request: string }

export type NextStep = {
  key: string
  title: string
  // one or two plain sentences
  body: string[]
  action: NextStepAction
  // the categories it came from; empty for the step that works on every site
  from: { name: string; tier: Tier }[]
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

// Where /learn explains how to turn on Global Privacy Control: the first
// step of the "When a site sells your data" topic (advice.yaml).
export const GPC_LEARN = "/learn#sells_personal_data"
export const RIGHTS_LEARN = "/learn#rights"

// Per category: the step's title when the site has its own page for it
// (`act`), the title when it doesn't (`ask`), and what to ask for.
// `confirm` adds a line asking them to confirm it's done.
type CategoryStep = { act: string; ask: string; request: string; confirm: boolean }
const CATEGORY_STEPS: Record<string, CategoryStep> = {
  selling_sharing: {
    act: "Opt out of selling and sharing",
    ask: "Ask them not to sell or share your data",
    request: "Please do not sell or share my personal information, including with advertising partners.",
    confirm: true,
  },
  ai_training: {
    act: "Check their AI training settings",
    ask: "Ask them not to train AI on your content",
    request: "Please do not use my content or personal information to train AI models.",
    confirm: true,
  },
  retention: {
    act: "Delete what you no longer need",
    ask: "Ask them to delete your data",
    request: "Please delete the personal information you hold about me.",
    confirm: true,
  },
  collection: {
    act: "Limit what they collect",
    ask: "Ask what they hold about you",
    request: "Please tell me what personal information you hold about me, and where it came from.",
    confirm: false,
  },
  user_rights: {
    act: "Use your privacy settings",
    ask: "Ask for your data, or to opt out",
    request:
      "Please send me a copy of the personal information you hold about me, and opt me out of targeted advertising.",
    confirm: true,
  },
  security: {
    act: "Check your account security",
    ask: "Ask how they protect your data",
    request:
      "Please tell me how you protect my personal information, and whether you will tell me if it is part of a data breach.",
    confirm: false,
  },
  government: {
    act: "See how they handle government requests",
    ask: "Ask about government requests",
    request:
      "Please tell me whether you will let me know when a government or the police ask for my data, where the law allows it.",
    confirm: false,
  },
  terms: {
    act: "Check your options under the terms",
    ask: "Ask about your options under the terms",
    request: "Please tell me what choices I have under your terms, including any way to opt out of arbitration.",
    confirm: false,
  },
}
const OTHER_STEP: CategoryStep = {
  act: "See your options",
  ask: "Ask them about this",
  request: "Please tell me what choices I have about how you handle my personal information.",
  confirm: false,
}

const sentence = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`)
const said = (f: Evidence) => sentence(f.plain ?? f.meaning)

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

const linkFor = (site: Site, key: string): SiteLink | undefined => (site.links ?? []).find((l) => l.category === key)

const onSite = (l: SiteLink): NextStepAction => ({ kind: "link", href: l.url, text: l.text, onSite: true })

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

  const steps: NextStep[] = []
  for (const category of concerning) {
    const top = topFinding(category)
    const link = linkFor(site, category.key)
    const c = CATEGORY_STEPS[category.key] ?? OTHER_STEP
    steps.push({
      key: category.key,
      title: link ? c.act : c.ask,
      body: [
        ...(top ? [said(top)] : []),
        link
          ? `${site.domain} has its own page for this.`
          : "We didn’t find a page for this on their site, but you can ask them directly.",
      ],
      action: link ? onSite(link) : { kind: "copy", request: requestText(category.key, site.domain) },
      from: [{ name: category.name, tier: category.tier }],
    })
  }

  // The rights step: when the documents say anyone can get a copy of their
  // data or have it deleted (the protective answer, "all_users").
  const rights = card.categories
    .filter((c) => c.key === "user_rights" || c.key === "retention")
    .flatMap((c) =>
      c.findings
        .filter(
          (f) =>
            (f.check_id === "access_and_export" || f.check_id === "deletion_on_request") &&
            f.status === "all_users" &&
            f.exposure === 0,
        )
        .map((f) => ({ category: c, finding: f })),
    )
  const copy = rights.find((r) => r.finding.check_id === "access_and_export")
  const remove = rights.find((r) => r.finding.check_id === "deletion_on_request")
  if (copy || remove) {
    const link =
      (copy && linkFor(site, copy.category.key)) ?? (remove && linkFor(site, remove.category.key))
    const from = [copy, remove]
      .filter((r) => r !== undefined)
      .map((r) => r.category)
      .filter((c, i, all) => all.findIndex((o) => o.key === c.key) === i)
      .map((c) => ({ name: c.name, tier: c.tier }))
    steps.push({
      key: "rights",
      title: copy && remove ? "Get a copy, or have it deleted" : copy ? "Get a copy of your data" : "You can have your data deleted",
      body: [copy, remove].filter((r) => r !== undefined).map((r) => said(r.finding)),
      action: link ? onSite(link) : { kind: "link", href: RIGHTS_LEARN, text: "How to ask for it", onSite: false },
      from,
    })
  }

  const shown = steps.slice(0, MAX_SITE_STEPS)
  shown.push({
    key: "gpc",
    title: "Send a “do not sell or share” signal from your browser",
    body: [
      "Global Privacy Control is a browser setting that tells every site you visit not to sell or share your data.",
      "In several US states, businesses must honor it.",
    ],
    action: { kind: "link", href: GPC_LEARN, text: "How to turn it on", onSite: false },
    from: [],
    general: true,
  })

  return { steps: shown, nothingConcerning: concerning.length === 0 }
}
