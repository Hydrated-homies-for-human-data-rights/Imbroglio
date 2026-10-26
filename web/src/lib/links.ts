// Public links shown on every page.

export const REPO_URL = "https://github.com/Hydrated-homies-for-human-data-rights/Imbroglio"

// Disputes are GitHub issues from .github/ISSUE_TEMPLATE/dispute.yml, with the
// site filled in. That is the published correction path the proposal promised.
export function disputeUrl(domain?: string): string {
  const params = new URLSearchParams({ template: "dispute.yml" })
  if (domain) {
    params.set("title", `Dispute: ${domain}`)
    params.set("site", domain)
  }
  return `${REPO_URL}/issues/new?${params}`
}
