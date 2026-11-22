// Public links shown on every page.

// The site's own address, for links that leave the page (sitemap, robots,
// link previews). SITE_URL overrides it for preview deployments.
export const SITE_URL = (process.env.SITE_URL ?? "https://imbroglio.io").replace(/\/+$/, "")

// "Report a problem" is the published correction path (proposal risk 8): a
// form on the site, stored for the team to reread against the stored
// document. The site's report page passes its domain so the form is filled in,
// and a finding's own link passes which one (check_id:document) so the form
// starts on it.
export function disputeUrl(domain?: string, finding?: { check_id: string; document: string }): string {
  if (!domain) return "/report"
  const site = `/report?site=${encodeURIComponent(domain)}`
  return finding ? `${site}&finding=${encodeURIComponent(`${finding.check_id}:${finding.document}`)}` : site
}
