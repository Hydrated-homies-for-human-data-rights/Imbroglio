// What a reader can do when we couldn't rate a site, by the reason the API
// gives (pipeline/imbroglio/failure.py). The API's own message says what
// went wrong; this says what to try next. "Below" is the paste-a-link form
// on the site page.

type Reason = "unreachable" | "blocked" | "pdf_only" | "timed_out" | "no_policy" | "error"

const NEXT: Record<Reason, string> = {
  unreachable: "If the address is right, the site may be down. Try again later.",
  blocked:
    "If you can open its privacy policy in your browser, paste the link below and we’ll try that page. It may be blocked too.",
  pdf_only: "If there’s a web page version of the policy, paste its link below.",
  timed_out: "Try again later, or paste a direct link to its policy below.",
  no_policy: "If you know where its policy is, paste the link below.",
  error: "Try again in a few minutes.",
}

export const FALLBACK_MESSAGE = "We couldn’t find a privacy policy or terms on this site."

export function nextStep(reason: string | undefined): string {
  return NEXT[(reason ?? "no_policy") as Reason] ?? NEXT.no_policy
}

// A link can help with every reason except a site that doesn't answer.
export function linkCanHelp(reason: string | undefined): boolean {
  return reason !== "unreachable" && reason !== "error"
}
