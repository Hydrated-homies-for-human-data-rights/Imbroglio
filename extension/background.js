// Looks up the current site in the Imbroglio API. Only cached results are
// shown: this never asks the API to analyze a new site.
//
// Privacy: the site's name never leaves the browser. We hash it with
// sha256, send the first few characters of the hash to /v1/lookup, and pick
// our site out of the matches by its full hash.
//
// API address: defaults to the website, which forwards lookups to the API and
// adds the API's password on its server, so nothing secret ships in the
// extension. Lookups only read cached results; they never start an analysis.
// For local development, run this in the service worker console:
//   chrome.storage.local.set({ apiBase: "http://localhost:8765" })
// (and chrome.storage.local.remove("apiBase") to go back).

const DEFAULT_API_BASE = "https://imbroglio.io/api";
const PREFIX_LENGTH = 5; // the API accepts 4 to 8; shorter shares the prefix with more sites

async function settings() {
    const s = await chrome.storage.local.get(["apiBase", "apiUser", "apiPassword"]);
    return {
        base: (s.apiBase || DEFAULT_API_BASE).replace(/\/+$/, ""),
        user: s.apiUser || "",
        password: s.apiPassword || "",
    };
}

async function sha256Hex(text) {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// "www.old.reddit.com" -> ["old.reddit.com", "reddit.com"]. We store sites
// under their main domain, so subdomains fall back to their parents.
function candidates(hostname) {
    const labels = hostname.toLowerCase().replace(/^www\./, "").split(".");
    const out = [];
    for (let i = 0; i <= labels.length - 2; i++) {
        out.push(labels.slice(i).join("."));
    }
    return out;
}

async function lookup(domain, api) {
    const hash = await sha256Hex(domain);
    const headers = { Accept: "application/json" };
    if (api.user && api.password) {
        headers.Authorization = "Basic " + btoa(`${api.user}:${api.password}`);
    }
    const res = await fetch(`${api.base}/v1/lookup/${hash.slice(0, PREFIX_LENGTH)}`, { headers });
    if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
    }
    const body = await res.json();
    return body.sites.find((s) => s.hash === hash) || null;
}

// Same shape the popup and content script already use: overall + scores by category name.
function toSiteData(domain, entry) {
    if (!entry.scores) {
        return { status: "not_analyzed", domain, documents: entry.documents };
    }
    const scores = {};
    for (const c of entry.scores.categories) {
        scores[c.name] = { level: c.tier, findings: c.findings };
    }
    return {
        status: "ready",
        domain,
        overall: entry.scores.headline,
        scores,
        analyzedAt: entry.scores.analyzed_at,
        rubric: entry.scores.rubric_version,
        documents: entry.documents,
    };
}

async function getData(hostname) {
    const api = await settings();
    for (const domain of candidates(hostname)) {
        const entry = await lookup(domain, api);
        if (entry) {
            console.log(`imbroglio BG: found ${domain}`);
            return toSiteData(domain, entry);
        }
    }
    console.log(`imbroglio BG: no data for ${hostname}`);
    return { status: "unknown" };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getData") {
        getData(request.domain)
            .then((data) => sendResponse({ data }))
            .catch((err) => {
                console.error("imbroglio BG: lookup failed", err);
                sendResponse({ data: { status: "error", error: String(err.message || err) } });
            });
        return true; // Keeps the message channel open
    }
});
