// "2 days ago", "today": coarse on purpose, matching the design's copy.
export function ago(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return "today"
  if (days === 1) return "1 day ago"
  if (days < 60) return `${days} days ago`
  const months = Math.round(days / 30)
  return months < 24 ? `${months} months ago` : `${Math.round(days / 365)} years ago`
}

// "Sep 14, 2026"
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
}

export const docName = (t: "privacy" | "terms") => (t === "privacy" ? "Privacy Policy" : "Terms of Service")
