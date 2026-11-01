// Renders the popup from the lookup result background.js returns. No data is
// fetched here; see background.js for how the site is looked up without
// sending its name.

const WEBSITE = "https://imbroglio.io";
const DOC_NAMES = { privacy: "privacy policy", terms: "terms" };
const TIER_WORDS = {
  SEVERE: "Severe",
  EXTENSIVE: "Extensive",
  MODERATE: "Moderate",
  LIMITED: "Limited",
  NOT_DISCLOSED: "Not disclosed",
  UNCLEAR: "Unclear",
  INFO: "Info",
};
// Why a site got its overall rating when no single category explains it
// (scorer s2; the wording follows the API's tier meanings).
const HEADLINE_NOTES = {
  LIMITED: "No red flags, and enough of the key questions were answered to say so.",
  UNCLEAR: "Too few of the key questions were answered to say this site's practices are limited.",
  NOT_DISCLOSED: "The documents say nothing about the practices we check.",
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function tierClass(tier) {
  return (tier || "NOT_DISCLOSED").toLowerCase();
}

function mark(tier) {
  return el("span", `mark m-${tierClass(tier)}`);
}

function tierWord(tier, className = "") {
  return el("span", `${className} t-${tierClass(tier)}`.trim(), TIER_WORDS[tier] || tier);
}

function formatDate(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d) ? d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "unknown date";
}

// ["privacy", "terms"] -> "Privacy policy and terms of service"
function documentNames(documents) {
  const names = (documents || []).map((d) => DOC_NAMES[d] || d);
  if (!names.length) return "";
  const joined = names.join(" and ");
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

// Popup links don't open on their own, so open them in a new tab.
function setButton(text, url) {
  const a = $("cta");
  a.textContent = text;
  a.href = url;
  a.hidden = false;
  a.onclick = (e) => {
    e.preventDefault();
    chrome.tabs.create({ url });
  };
}

function reportUrl(domain) {
  return `${WEBSITE}/site/${encodeURIComponent(domain)}`;
}

// Requests go through the website, where the per-visitor and daily request
// limits apply. Opening the link is the user's choice to tell us the site.
function requestUrl(domain) {
  return `${WEBSITE}/search?q=${encodeURIComponent(domain)}`;
}

function showMessage(domain, text, button) {
  $("domain").textContent = domain;
  $("rating").hidden = true;
  $("because").hidden = true;
  $("categories").hidden = true;
  const m = $("message");
  m.textContent = text;
  m.hidden = false;
  if (button) setButton(button.text, button.url);
}

function render(site) {
  $("domain").textContent = site.domain;
  $("rating").replaceChildren(mark(site.headline), tierWord(site.headline));

  // The categories that set a concerning overall rating; the other ratings
  // come from the whole site, so they get a note instead. Category names are
  // capitalized ("Retention and deletion"); mid-sentence they lose that,
  // except names that start with an initialism ("AI and model training").
  const drivers = HEADLINE_NOTES[site.headline]
    ? []
    : site.categories
        .filter((c) => c.tier === site.headline)
        .map((c) => (/^[A-Z][a-z]/.test(c.name) ? c.name.charAt(0).toLowerCase() + c.name.slice(1) : c.name));
  const list = drivers.length > 1 ? `${drivers.slice(0, -1).join(", ")} and ${drivers[drivers.length - 1]}` : drivers[0];
  $("because").textContent = drivers.length ? `Because of ${list}.` : HEADLINE_NOTES[site.headline] || "";

  $("categories").replaceChildren(
    ...site.categories.map((c) => {
      const li = el("li");
      const n = c.findings || 0;
      li.append(
        mark(c.tier),
        el("span", "cat-name", c.name),
        tierWord(c.tier, "cat-tier"),
        el("span", "cat-count", c.tier === "NOT_DISCLOSED" ? "" : `${n} finding${n === 1 ? "" : "s"}`),
      );
      return li;
    }),
  );

  const parts = [`Analyzed ${formatDate(site.analyzedAt)}`, documentNames(site.documents), `rubric ${site.rubric}`];
  $("meta").textContent = parts.filter(Boolean).join(" · ");
  setButton("See the full report", reportUrl(site.domain));
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    // activeTab lets us read this tab's address only because the user clicked the icon.
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab && tab.url ? new URL(tab.url) : null;
    if (!url || !["http:", "https:"].includes(url.protocol)) {
      showMessage("No website open", "Open a website to see its privacy rating.");
      return;
    }
    const shown = url.hostname.replace(/^www\./, "");
    $("domain").textContent = shown;

    chrome.runtime.sendMessage({ action: "getData", domain: url.hostname }, (response) => {
      if (chrome.runtime.lastError || !response) {
        console.error("Error communicating with background:", chrome.runtime.lastError);
        showMessage(shown, "Something went wrong. Close this and try again.");
        return;
      }
      const site = response.data;
      if (site.status === "ready") {
        render(site);
      } else if (site.status === "not_analyzed") {
        const docs = documentNames(site.documents);
        const them = site.documents && site.documents.length === 1 ? "it" : "them";
        showMessage(site.domain, `We have this site's ${docs ? docs.toLowerCase() : "documents"} but haven't rated ${them} yet.`,
          { text: "See it on imbroglio.io", url: reportUrl(site.domain) });
      } else if (site.status === "error") {
        showMessage(shown, `Couldn't reach Imbroglio (${site.error}). Try again in a moment.`);
      } else {
        showMessage(shown, "We haven't analyzed this site yet. You can ask for it on imbroglio.io, and it will be rated in turn.",
          { text: "Request it on imbroglio.io", url: requestUrl(shown) });
      }
    });
  } catch (error) {
    console.error("Popup initialization failed:", error);
    showMessage("Imbroglio", "Something went wrong. Close this and try again.");
  }
});
