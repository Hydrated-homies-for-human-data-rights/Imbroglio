// Public links shown on every page.

// "Report a problem" is the published correction path (proposal risk 8): a
// form on the site, stored for the team to reread against the stored
// document. The site's report page passes its domain so the form is filled in.
export function disputeUrl(domain?: string): string {
  return domain ? `/report?site=${encodeURIComponent(domain)}` : "/report"
}
