// Renders the popup from the lookup result background.js returns. No data is
// fetched here; see background.js for how the site is looked up without
// sending its name. Three screens (the UX team's Figma): the overview, the
// category breakdown, and what you can do.

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
// Worst first: the order of the count tiles and of the biggest flags.
const SEVERITY = ["SEVERE", "EXTENSIVE", "MODERATE", "LIMITED", "UNCLEAR", "INFO", "NOT_DISCLOSED"];
// Tiers that count as concerns in the overview card's headline.
const CONCERNS = new Set(["SEVERE", "EXTENSIVE", "MODERATE"]);

// The overview card's one-line reading of the overall rating. The wording
// follows the API's tier meanings and the Figma's sample copy.
const HEADLINE_TEXT = {
  SEVERE: "This site does things with your data that most people would object to.",
  EXTENSIVE: "This site uses your data in ways most people would not expect.",
  MODERATE: "This site uses your data about as much as most sites do.",
  LIMITED: "No red flags, and enough of the key questions were answered to say so.",
  UNCLEAR: "Too few of the key questions were answered to say this site's practices are limited.",
  NOT_DISCLOSED: "The documents say nothing about the practices we check.",
};

// What you can do, per rubric category, shown for the categories flagged on
// the site: what is available to you, not a to-do list. `how` links to the
// steps on imbroglio.io/learn (the check the advice hangs on). A button to
// the site's own page appears only when the lookup carries that link (the
// API's link harvest); `verb` is its text.
const ACTIONS = {
  ai_training: { title: "Opt out of AI training", why: "You can stop your content being used to train their models.", verb: "Open setting", check: "trains_ai_on_user_data" },
  selling_sharing: { title: "Do not sell or share", why: "You can tell them not to sell or share your data with ad partners.", verb: "Opt out", check: "sells_personal_data" },
  retention: { title: "Delete your data", why: "You can ask them to delete what they hold about you.", verb: "Request", check: "deletion_on_request" },
  user_rights: { title: "Get a copy of your data", why: "You can ask for a copy of what they hold, in some states.", verb: "Request", check: "access_and_export" },
  collection: { title: "Limit what you share", why: "Optional fields can stay empty, and an app's permissions can be trimmed.", verb: "Open setting", check: "collects_sensitive_data" },
  security: { title: "Lock down your account", why: "A unique password and two-step sign-in limit what a breach exposes.", verb: "Open setting", check: "security_measures" },
  government: { title: "Government requests", why: "Whether they tell you when your data is requested is in the policy.", verb: "Read it", check: "notifies_users_of_requests" },
};

const $ = (id) => document.getElementById(id);
const state = { site: null, domain: "", open: null };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function tierClass(tier) {
  return (tier || "NOT_DISCLOSED").toLowerCase();
}

function mark(tier, big = false) {
  return el("span", `mark${big ? " big" : ""} m-${tierClass(tier)}`);
}

function tierWord(tier, className = "tier") {
  return el("span", `${className} t-${tierClass(tier)}`, TIER_WORDS[tier] || tier);
}

function chevron() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("chev");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M7.5 4.5 13 10l-5.5 5.5");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.8");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

function formatDate(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d) ? d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "unknown date";
}

// ["privacy", "terms"] -> "Privacy policy and terms"
function documentNames(documents) {
  const names = (documents || []).map((d) => DOC_NAMES[d] || d);
  if (!names.length) return "";
  const joined = names.join(" and ");
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

// Popup links don't open on their own, so open them in a new tab.
function openInTab(url) {
  if (typeof chrome !== "undefined" && chrome.tabs) chrome.tabs.create({ url });
  else window.open(url, "_blank");
}

function linkTo(node, url) {
  node.href = url;
  node.onclick = (e) => {
    e.preventDefault();
    openInTab(url);
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

function sortedCategories(site) {
  return [...site.categories].sort(
    (a, b) => SEVERITY.indexOf(a.tier) - SEVERITY.indexOf(b.tier) || (b.findings || 0) - (a.findings || 0),
  );
}

// --- screens -------------------------------------------------------------------

// The screens in depth order; going deeper slides in from the right,
// going back from the left. The popup itself never changes size.
const ORDER = ["overview", "breakdown", "actions"];
let current = "overview";

function show(id) {
  const forward = ORDER.indexOf(id) > ORDER.indexOf(current);
  current = id;
  for (const s of document.querySelectorAll(".screen")) {
    s.hidden = s.id !== id;
    s.classList.remove("enter-forward", "enter-back");
  }
  const screen = $(id);
  screen.classList.add(forward ? "enter-forward" : "enter-back");
  screen.addEventListener("animationend", () => screen.classList.remove("enter-forward", "enter-back"), { once: true });
  screen.querySelector(".body").scrollTop = 0;
  const first = screen.querySelector(".back") || screen.querySelector("button, a");
  if (first) first.focus({ preventScroll: true });
}

function showMessage(domain, text, button) {
  $("domain").textContent = domain;
  $("checked").textContent = "";
  $("concern").hidden = true;
  $("flags-label").hidden = true;
  $("flags").hidden = true;
  $("see-all").hidden = true;
  const m = $("message");
  m.textContent = text;
  m.hidden = false;
  if (button) {
    const a = $("cta");
    a.textContent = button.text;
    linkTo(a, button.url);
    a.hidden = false;
  }
}

// A policy change counts as recent for this long (the website's rule too).
const RECENT_DAYS = 30;

function renderOverview(site) {
  const sorted = sortedCategories(site);
  $("domain").textContent = site.domain;
  $("checked").textContent = `Policy checked ${formatDate(site.analyzedAt)}`;

  // A recent change to the policy, with the history page behind it.
  const changed = site.changedAt ? new Date(site.changedAt) : null;
  const recent = changed && !isNaN(changed) && Date.now() - changed.getTime() < RECENT_DAYS * 86_400_000;
  const line = $("changed");
  line.hidden = !recent;
  if (recent) {
    const a = el("a", "", "see what changed");
    linkTo(a, `${reportUrl(site.domain)}/history`);
    line.replaceChildren(`Policy changed ${formatDate(site.changedAt)} · `, a);
  }

  // The card: how many categories sit at the overall rating, and what it means.
  const head = site.headline;
  const atHead = site.categories.filter((c) => c.tier === head).length;
  const card = $("concern");
  card.style.setProperty("--wash", `var(--${tierClass(head).replace("_", "-")}-wash, var(--grey-wash))`);
  $("concern-mark").className = `mark big m-${tierClass(head)}`;
  $("concern-title").textContent = CONCERNS.has(head)
    ? `${atHead} ${TIER_WORDS[head].toLowerCase()} concern${atHead === 1 ? "" : "s"}`
    : TIER_WORDS[head] || head;
  $("concern-text").textContent = HEADLINE_TEXT[head] || "";

  // One tile per tier present, worst first, at most four.
  const counts = new Map();
  for (const c of site.categories) counts.set(c.tier, (counts.get(c.tier) || 0) + 1);
  $("tiles").replaceChildren(
    ...SEVERITY.filter((t) => counts.has(t))
      .slice(0, 4)
      .map((t) => {
        const li = el("li", `tile t-${tierClass(t)}`);
        li.append(el("b", "", String(counts.get(t))), el("small", "", TIER_WORDS[t]));
        return li;
      }),
  );

  // The three worst categories. Each opens the breakdown at that category.
  $("flags").replaceChildren(
    ...sorted.slice(0, 3).map((c) => {
      const li = el("li");
      const b = el("button", "row");
      b.type = "button";
      b.append(mark(c.tier), el("span", "name", c.name), tierWord(c.tier), chevron());
      b.onclick = () => {
        state.open = c.key;
        renderBreakdown(site);
        show("breakdown");
      };
      li.append(b);
      return li;
    }),
  );
  $("see-all").textContent = `See all ${site.categories.length} categories`;
  $("see-all").hidden = false;
  $("see-all").onclick = () => {
    renderBreakdown(site);
    show("breakdown");
  };
}

// What a row says when opened. The lookup carries the ratings and how many
// verified findings sit behind each, not the findings themselves; those are
// on the full report, which the link opens at this category.
function detailFor(site, c) {
  const d = el("div", "detail");
  const n = c.findings || 0;
  let text;
  if (c.tier === "NOT_DISCLOSED") text = "The documents don’t address this.";
  else if (c.tier === "INFO") text = `${n} ${n === 1 ? "thing" : "things"} worth knowing, nothing that affects the rating.`;
  else text = `${n} verified ${n === 1 ? "finding" : "findings"}, each backed by a quote from the site’s own documents.`;
  d.append(el("p", "", text));
  const from = el("p", "from");
  const a = el("a", "", "Read the quotes on the full report");
  linkTo(a, `${reportUrl(site.domain)}#${c.key}`);
  from.append(a);
  d.append(from);
  return d;
}

function renderBreakdown(site) {
  $("categories-label").textContent = `${site.categories.length} categories`;
  for (const n of document.querySelectorAll("[data-domain]")) n.textContent = site.domain;
  linkTo($("report-link"), reportUrl(site.domain));

  const list = $("categories");
  const items = site.categories.map((c) => {
    const li = el("li");
    const b = el("button", "row");
    b.type = "button";
    b.setAttribute("aria-expanded", "false");
    b.append(mark(c.tier), el("span", "name", c.name), tierWord(c.tier), chevron());
    b.onclick = () => {
      state.open = state.open === c.key ? null : c.key;
      renderBreakdown(site);
    };
    li.append(b);
    if (state.open === c.key) {
      li.classList.add("open");
      b.setAttribute("aria-expanded", "true");
      li.append(detailFor(site, c));
    }
    return li;
  });
  list.replaceChildren(...items);
  $("collapse").hidden = state.open === null;
  $("collapse").onclick = () => {
    state.open = null;
    renderBreakdown(site);
  };
}

// --- what you can do -------------------------------------------------------------

// The site's own page for an action, when the lookup carries one for the
// category (the API's link harvest). Without one there is no button: we
// don't send people to a page we haven't found.
function ownLink(site, key) {
  const own = (site.links || []).find((l) => l.category === key && /^https?:/.test(l.url || ""));
  return own ? own.url : null;
}

function renderActions(site) {
  // Only the categories flagged on this site get a card.
  const cards = sortedCategories(site).filter((c) => ACTIONS[c.key] && CONCERNS.has(c.tier));
  const list = $("action-cards");
  list.replaceChildren(
    ...cards.map((c) => {
      const a = ACTIONS[c.key];
      const li = el("li", "card");
      const text = el("div", "card-text");
      const how = el("a", "how", "How, on imbroglio.io");
      linkTo(how, `${WEBSITE}/learn#${a.check}`);
      text.append(el("p", `eyebrow t-${tierClass(c.tier)}`, c.name), el("h3", "", a.title), el("p", "why", a.why), how);
      li.append(text);
      const url = ownLink(site, c.key);
      if (url) {
        const buttons = el("div", "card-buttons");
        const go = el("a", "button primary small", a.verb);
        linkTo(go, url);
        buttons.append(go);
        li.append(buttons);
      }
      return li;
    }),
  );
  const none = document.querySelector("#actions .none");
  if (none) none.remove();
  if (!cards.length) {
    list.after(el("p", "none", "Nothing is flagged on this site, so there is nothing to opt out of here."));
  }
}

// --- wiring ----------------------------------------------------------------------

function wireNavigation() {
  for (const b of document.querySelectorAll("[data-go]")) {
    b.addEventListener("click", () => {
      const to = b.dataset.go;
      if (to === "actions" && state.site) renderActions(state.site);
      show(to);
    });
  }
  linkTo($("site-link"), WEBSITE);
}

// The two switches in the footer. Both are on until switched off; the
// background script reads the same keys before it notifies.
async function wireWarnToggle() {
  if (typeof chrome === "undefined" || !chrome.storage) return;
  const got = await chrome.storage.local.get(["warnExtensive", "policyChanges"]);
  for (const [id, key] of [["warn", "warnExtensive"], ["changes", "policyChanges"]]) {
    const box = $(id);
    box.checked = got[key] !== false;
    box.addEventListener("change", () => chrome.storage.local.set({ [key]: box.checked }));
  }
}

function setFavicon(url) {
  if (url && /^https?:/.test(url)) $("favicon").style.backgroundImage = `url("${url.replace(/"/g, "%22")}")`;
}

async function render(site, favIconUrl) {
  state.site = site;
  state.domain = site.domain;
  setFavicon(favIconUrl);
  renderOverview(site);
  renderBreakdown(site);
}

// For a look without the extension loaded: popup.html?mock=ready|unknown|error
// serves a sample site, with nothing fetched.
function mockSite(kind) {
  if (kind === "unknown") return { status: "unknown" };
  if (kind === "error") return { status: "error", error: "API returned 503" };
  if (kind === "not_analyzed") return { status: "not_analyzed", domain: "example-shop.com", documents: ["privacy"] };
  return {
    status: "ready",
    domain: "example-shop.com",
    headline: "EXTENSIVE",
    analyzedAt: "2026-11-02T19:29:33Z",
    changedAt: new Date(Date.now() - 4 * 86_400_000).toISOString(),
    rubric: "v0.2",
    documents: ["privacy", "terms"],
    links: [{ category: "ai_training", url: "https://example-shop.com/settings/privacy" }],
    categories: [
      { key: "selling_sharing", name: "Data selling and sharing", tier: "MODERATE", findings: 3 },
      { key: "collection", name: "Collection scope", tier: "INFO", findings: 2 },
      { key: "retention", name: "Retention and deletion", tier: "MODERATE", findings: 2 },
      { key: "user_rights", name: "User rights", tier: "LIMITED", findings: 2 },
      { key: "security", name: "Security", tier: "INFO", findings: 1 },
      { key: "ai_training", name: "AI and model training", tier: "EXTENSIVE", findings: 1 },
      { key: "government", name: "Government requests", tier: "LIMITED", findings: 1 },
    ],
  };
}

function handle(site, shown, favIconUrl) {
  if (site.status === "ready") {
    render(site, favIconUrl);
  } else if (site.status === "not_analyzed") {
    const docs = documentNames(site.documents);
    const them = site.documents && site.documents.length === 1 ? "it" : "them";
    showMessage(site.domain, `We have this site’s ${docs ? docs.toLowerCase() : "documents"} but haven’t rated ${them} yet.`,
      { text: "See it on imbroglio.io", url: reportUrl(site.domain) });
  } else if (site.status === "error") {
    showMessage(shown, `Couldn’t reach Imbroglio (${site.error}). Try again in a moment.`);
  } else {
    showMessage(shown, "We haven’t analyzed this site yet. You can ask for it on imbroglio.io, and it will be rated in turn.",
      { text: "Request it on imbroglio.io", url: requestUrl(shown) });
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  wireNavigation();
  wireWarnToggle();

  const mock = new URLSearchParams(location.search).get("mock");
  if (mock) {
    handle(mockSite(mock), "example-shop.com", "");
    return;
  }
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
    setFavicon(tab.favIconUrl);

    chrome.runtime.sendMessage({ action: "getData", domain: url.hostname }, (response) => {
      if (chrome.runtime.lastError || !response) {
        console.error("Error communicating with background:", chrome.runtime.lastError);
        showMessage(shown, "Something went wrong. Close this and try again.");
        return;
      }
      handle(response.data, shown, tab.favIconUrl);
    });
  } catch (error) {
    console.error("Popup initialization failed:", error);
    showMessage("Imbroglio", "Something went wrong. Close this and try again.");
  }
});
