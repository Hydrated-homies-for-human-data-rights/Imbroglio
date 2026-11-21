import type { RubricInfo, Scorecard, Tier } from "./api"

// "Try the rules" on How we score: the scorer's rules (pipeline/imbroglio/
// scorer.py, rate and score) run on answers a reader picks, one per question.
// Everything it needs comes from GET /v1/rubric, so it can't drift from the
// scorer; pipeline/tests/test_rubric_api.py checks the same steps against the
// real scorer on thousands of random answer sets.

export type Answers = Record<string, string> // check_id -> status

type Status = RubricInfo["categories"][number]["checks"][number]["statuses"][number]

const RANK: Record<string, number> = { NOT_DISCLOSED: -1, LIMITED: 0, INFO: 0.5, MODERATE: 1, EXTENSIVE: 2, SEVERE: 3 }
const RATED = new Set(["severe", "high", "medium"])

export type Outcome = {
  tier: Tier
  score: number | null
  raw: number | null // 100 minus the deductions, before keeping it in the rating's range
  band: [number, number] | null
  counted: { check_id: string; concern: string; points: number }[]
  highAnswered: number
  highTotal: number
  // which rule decided it, in a sentence
  why: string
}

export function statusIndex(rubric: RubricInfo): Map<string, Map<string, Status>> {
  const out = new Map<string, Map<string, Status>>()
  for (const c of rubric.categories)
    for (const k of c.checks) out.set(k.check_id, new Map(k.statuses.map((s) => [s.status, s])))
  return out
}

export function rateAnswers(rubric: RubricInfo, answers: Answers): Outcome | null {
  const sc = rubric.scoring
  if (!sc) return null
  const index = statusIndex(rubric)
  const categoryOf = new Map(rubric.categories.flatMap((c) => c.checks.map((k) => [k.check_id, c.key] as const)))
  const chosen = new Map<string, Status>()
  for (const [id, st] of Object.entries(answers)) {
    const s = index.get(id)?.get(st)
    if (s) chosen.set(id, s)
  }
  const highChecks = [...index].filter(([, ss]) => [...ss.values()].some((s) => s.concern === "severe" || s.concern === "high"))
  const highAnswered = highChecks.filter(([id]) => chosen.has(id)).length
  const base = { highAnswered, highTotal: highChecks.length }

  if (chosen.size === 0)
    return { ...base, tier: "NOT_DISCLOSED", score: null, raw: null, band: null, counted: [], why: "With no answers at all, there is nothing to rate: the site is Not disclosed, and gets no score." }

  const counted = [...chosen]
    .filter(([, s]) => RATED.has(s.concern ?? ""))
    .filter(([, s]) => !(s.same_concern_as && RATED.has(chosen.get(s.same_concern_as)?.concern ?? "")))
    .map(([id, s]) => ({ check_id: id, concern: s.concern as string, points: s.points ?? 0 }))
  const n = (c: string) => counted.filter((x) => x.concern === c).length
  const rated = (s?: Status) => RATED.has(s?.concern ?? "")
  const doubled = [...chosen.values()].some((s) => rated(s) && s.same_concern_as && rated(chosen.get(s.same_concern_as)))

  let tier: Tier
  let why: string
  if (n("severe") > 0) {
    tier = "SEVERE"
    why = "Any severe concern makes a site Severe: selling your data for money, or no way to delete it."
  } else if (n("high") >= 2) {
    tier = "SEVERE"
    why = "Two or more high concerns make a site Severe."
  } else if (n("high") === 1) {
    tier = "EXTENSIVE"
    why = "One high concern makes a site Extensive. Good answers elsewhere can’t average it away."
  } else if (n("medium") >= sc.moderate_needs) {
    tier = "MODERATE"
    why = "A medium concern, and nothing worse, makes a site Moderate."
  } else {
    tier = "LIMITED"
    why = "Nothing takes points off, and enough of the key questions are answered to say so."
  }
  // never below an Extensive or Severe category
  const worst = [...chosen.values()].reduce<Tier>((w, s) => (RANK[s.tier] > RANK[w] ? s.tier : w), "NOT_DISCLOSED")
  if ((worst === "EXTENSIVE" || worst === "SEVERE") && RANK[worst] > RANK[tier]) tier = worst
  if (tier === "LIMITED" && highAnswered < sc.min_high_answered) {
    tier = "UNCLEAR"
    why = `Nothing takes points off, but only ${highAnswered} of the ${highChecks.length} red-flag questions are answered, and Limited needs ${sc.min_high_answered}. Silence is never read as good, so there is no score.`
  }
  if (tier === "LIMITED") {
    const answered = new Set([...chosen.keys()].map((id) => categoryOf.get(id)))
    if (!sc.limited_requires.every((c) => answered.has(c))) {
      tier = "MODERATE"
      why = "Nothing takes points off, but a category Limited needs went unanswered."
    }
  }
  if (doubled) why += " Two of the answers are about the same practice, so they count once."

  const band = sc.bands[tier] ?? null
  if (!band) return { ...base, tier, score: null, raw: null, band: null, counted, why }
  const raw = sc.start - counted.reduce((t, c) => t + c.points, 0)
  return { ...base, tier, score: Math.min(Math.max(raw, band[0]), band[1]), raw, band, counted, why }
}

// A rated site's answers, one per question: the most exposed one that
// counts, as the scorer picks across a site's documents. Null when running
// the rules on them doesn't give the site's published rating, so the page
// never shows an example that disagrees with the report.
export function answersOf(rubric: RubricInfo, card: Scorecard): Answers | null {
  const index = statusIndex(rubric)
  const best = new Map<string, number>()
  const answers: Answers = {}
  for (const c of card.categories)
    for (const f of c.findings) {
      if (f.status === "not_disclosed" || !index.get(f.check_id)?.has(f.status)) continue
      if (!best.has(f.check_id) || f.exposure > (best.get(f.check_id) as number)) {
        best.set(f.check_id, f.exposure)
        answers[f.check_id] = f.status
      }
    }
  const out = rateAnswers(rubric, answers)
  if (!out || out.tier !== card.headline || out.score !== (card.score?.value ?? null)) return null
  return answers
}
