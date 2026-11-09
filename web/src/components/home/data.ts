import type { Tier } from "@/lib/api"

// Content for the front page that the read API does not serve: the policy
// excerpt (the API returns quotes, not the paragraphs around them), the line
// each category's evidence sits on, and the recently rated list.
//
// Everything here is copied from the production database, not written. The
// excerpt is tiktok.com's stored privacy policy, document version 996, fetched
// 2026-10-28; line numbers count lines of that stored text. The verdicts are
// the ones the live site shows. When the stored document changes, this file
// has to change with it. Never add a quote here that is not in the database.

export const EXCERPT = {
  domain: "tiktok.com",
  title: "U.S. Privacy Policy",
  updated: "July 15, 2026",
  version: 996,
  fetched: "2026-10-28",
  lines: 90,
  chars: 27_176,
  sha256: "6f2a…c41e",
  questions: 14,
  answered: 11,
}

export type Clause = {
  line: number
  // The verified quote comes first; `quoteChars` is how many characters of
  // `text` it covers. Only those characters are tinted.
  text: string
  quoteChars: number
  key: string
  category: string
  tier: Tier
  note: string
}

export const CLAUSES: Clause[] = [
  {
    line: 25,
    text:
      "We may collect biometric identifiers and biometric information as defined under US laws, such as faceprints and voiceprints, from your user content. Where required by law, we will seek any required permissions from you prior to any such collection.",
    quoteChars: 150,
    key: "collection",
    category: "Data collection",
    tier: "INFO",
    note: "biometrics, from what you post",
  },
  {
    line: 37,
    text:
      "To review, support, improve, and develop the Services, and train, test, and improve technology, such as machine learning models and algorithms, including by analyzing how people are using the Services; conducting research; soliciting feedback; monitoring your activity and usage across the devices you use to access the Services; and scanning, analyzing, and reviewing user content, messages, AI interactions, and associated metadata.",
    quoteChars: 139,
    key: "ai_training",
    category: "AI and model training",
    tier: "EXTENSIVE",
    note: "trains models on content and messages",
  },
  {
    line: 75,
    text:
      "We use reasonable measures to help protect information from loss, theft, misuse, unauthorized access, disclosure, alteration, or destruction. You should understand that no data storage system or transmission of data over the Internet or any other public network can be guaranteed to be 100 percent secure.",
    quoteChars: 138,
    key: "security",
    category: "Security",
    tier: "INFO",
    note: "“reasonable measures”, no more",
  },
  {
    line: 76,
    text:
      "We retain information for as long as necessary to provide the Services and for the other purposes set out in this Privacy Policy. We also retain information when necessary to comply with contractual and legal obligations, when we have a legitimate business interest to do so (such as improving and developing the Services, and enhancing its safety, security and stability), and for the exercise or defense of legal claims.",
    quoteChars: 128,
    key: "retention",
    category: "Retention and deletion",
    tier: "MODERATE",
    note: "kept “as long as necessary”",
  },
]

// Fragments of the same document caught in the opening tangle. Each is a
// substring of a verified quote above.
export const FRAGMENTS = [
  { text: "faceprints and voiceprints", line: 25 },
  { text: "as long as necessary", line: 76 },
  { text: "train, test, and improve technology", line: 37 },
  { text: "reasonable measures", line: 75 },
]

// The headline finding the thread straightens into.
export const FIRST_THREAD = {
  key: "ai_training",
  category: "AI and model training",
  tier: "EXTENSIVE" as Tier,
  quote: "train, test, and improve technology, such as machine learning models and algorithms",
  line: 37,
  // the finding in plain words, as the opening screen's card shows it
  why: "trains AI on your content and messages",
}

// Per category: the line of the stored text its evidence sits on, and a
// plain reading of what the verified answers said. Names and tiers come from
// the live scorecard when it can be fetched; this is the fallback.
export const INDEX: { key: string; name: string; tier: Tier; line: number; why: string }[] = [
  { key: "selling_sharing", name: "Data selling and sharing", tier: "MODERATE", line: 58, why: "shares with advertising partners; does not sell" },
  { key: "collection", name: "Data collection", tier: "INFO", line: 25, why: "biometrics, third parties, public sources" },
  { key: "retention", name: "Retention and deletion", tier: "MODERATE", line: 76, why: "“as long as necessary”; deletion on request" },
  { key: "user_rights", name: "Your rights", tier: "MODERATE", line: 68, why: "access and export for all users; a narrower ad opt-out in the terms" },
  { key: "security", name: "Security", tier: "INFO", line: 75, why: "“reasonable measures”" },
  { key: "ai_training", name: "AI and model training", tier: "EXTENSIVE", line: 37, why: "trains models on content and messages" },
  { key: "government", name: "Government requests", tier: "LIMITED", line: 64, why: "discloses under legal process" },
]

// What each category covers and what each rating means, in a reader's words.
// Shown under the cards that pop out beside the policy, since a test user
// couldn't tell what "Data collection: Info" meant. Keep in step with the
// rubric's categories and docs/rubric.md's rating meanings.
export const CATEGORY_ABOUT: Record<string, string> = {
  selling_sharing: "Whether they sell your data or share it with other companies, like advertisers.",
  collection: "What they collect about you, and where it comes from.",
  retention: "How long they keep your data, and whether you can have it deleted.",
  user_rights: "What you can see, download, or opt out of.",
  security: "How they protect your data, and whether they'll tell you about a breach.",
  ai_training: "Whether your data or content is used to train AI.",
  government: "When they hand your data to police or governments.",
}
export const TIER_SHORT: Record<Tier, string> = {
  SEVERE: "the practice at its broadest, with no real choice for you.",
  EXTENSIVE: "a broad practice, with few limits.",
  MODERATE: "the practice has clear limits, or you get a choice.",
  LIMITED: "a narrow practice, or a promise that protects you.",
  NOT_DISCLOSED: "the policy doesn't say.",
  UNCLEAR: "too little was said to rate it.",
  INFO: "we show what it says, but it doesn't lower the rating.",
}

export const FALLBACK_HEADLINE: Tier = "EXTENSIVE"
export const ANALYZED = "2026-10-30"

// Nothing reaches the front page without passing this. Anyone can request a
// site, so a domain that should not be on the home page can land in the
// database; the list below is hand-kept today, and when it comes from the API
// it has to go through the same gate. Blunt on purpose: a false positive just
// keeps a site off the front page, where it can still be searched.
const NOT_FOR_THE_FRONT_PAGE =
  /(^|[.-])(porn|xxx|sex|nudes?|nsfw|hentai|escorts?|onlyfans|casino|gambl|fetish|cam(s|girls)?)([.-]|$)/i
export const showable = (domain: string) => /^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(domain) && !NOT_FOR_THE_FRONT_PAGE.test(domain)

// Hand-kept until the API has a recent-sites endpoint. These are the ratings
// the live site showed on the date given.
export const RECENT_AS_OF = "2026-11-02"
const RECENT_RAW: { domain: string; tier: Tier; why: string }[] = [
  { domain: "wikipedia.org", tier: "SEVERE", why: "accounts cannot be removed entirely" },
  { domain: "target.com", tier: "EXTENSIVE", why: "trains AI on user data" },
  { domain: "epicgames.com", tier: "EXTENSIVE", why: "trains AI on user data" },
  { domain: "canva.com", tier: "MODERATE", why: "shares for advertising" },
  { domain: "discord.com", tier: "MODERATE", why: "retention “as long as necessary”" },
  { domain: "stackoverflow.com", tier: "MODERATE", why: "shares for advertising" },
  { domain: "steampowered.com", tier: "LIMITED", why: "no sale; clear retention" },
  { domain: "bestbuy.com", tier: "LIMITED", why: "access and deletion for all users" },
  { domain: "msudenver.edu", tier: "UNCLEAR", why: "most questions not addressed" },
]
export const RECENT = RECENT_RAW.filter((s) => showable(s.domain))

// From docs/evaluation.md. `found`: quotes found word for word; `onTopic`: found
// and containing one of the question's evidence words (the ones shown).
export const FIGURES = {
  sites: 559,
  quotes: 8_407,
  found: "99.4",
  onTopic: "78.7",
  consistency: "88.4",
  measured: "2026-11-02",
  consistencyMeasured: "2026-10-30",
}

export const TIER_WORD: Record<Tier, string> = {
  SEVERE: "Severe",
  EXTENSIVE: "Extensive",
  MODERATE: "Moderate",
  LIMITED: "Limited",
  NOT_DISCLOSED: "Not disclosed",
  UNCLEAR: "Unclear",
  INFO: "Info",
}
