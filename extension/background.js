// Looks up the current site in the Imbroglio API and draws the toolbar
// badge. Only cached results are shown: this never asks the API to analyze
// a new site.
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
const PREFIX_LENGTH = 5; // the website's lookup route only accepts 5 (the API itself takes 4 to 8)
const CACHE_MS = 10 * 60 * 1000; // a site's result is reused this long before being looked up again

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

// What the popup renders: the overall rating, one entry per rubric category
// in the rubric's order, and when and from which documents it was made.
function toSiteData(domain, entry) {
    if (!entry.scores) {
        return { status: "not_analyzed", domain, documents: entry.documents };
    }
    const s = entry.scores;
    return {
        status: "ready",
        domain,
        headline: s.headline,
        categories: s.categories.map((c) => ({ key: c.key, name: c.name, tier: c.tier, findings: c.findings })),
        analyzedAt: s.analyzed_at,
        rubric: s.rubric_version,
        scorer: s.scorer_version,
        documents: entry.documents,
        links: entry.links || [], // the site's own opt-out pages, once the API carries them
    };
}

// Results by hostname, so switching tabs doesn't repeat the lookup.
const recent = new Map();

async function getData(hostname) {
    const hit = recent.get(hostname);
    if (hit && Date.now() - hit.at < CACHE_MS) return hit.data;
    const api = await settings();
    let data = { status: "unknown" };
    for (const domain of candidates(hostname)) {
        const entry = await lookup(domain, api);
        if (entry) {
            console.log(`imbroglio BG: found ${domain}`);
            data = toSiteData(domain, entry);
            break;
        }
    }
    if (data.status === "unknown") console.log(`imbroglio BG: no data for ${hostname}`);
    recent.set(hostname, { at: Date.now(), data });
    return data;
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

// --- the toolbar badge ------------------------------------------------------------
//
// The icon is drawn here rather than shipped as files: the logo, and in the
// corner the site's worst level in the scorecard's own shape (the Figma's
// "toolbar badge = the site's worst level"). A site we haven't rated gets the
// icon dimmed with no badge. At 16 px the curvy i becomes a slanted bar with
// a bigger dot, so it still reads at toolbar size.

const LOGO_PATH = "M450 398C478 382 530 378 560 402C588 425 585 465 565 505L492 632C478 658 485 690 510 705C527 715 545 715 560 710L583 795C555 815 525 823 497 822C450 821 410 800 393 760C378 723 385 670 405 630L478 492C492 465 485 448 470 440C460 434 446 432 436 433Z";
const BADGE = {
    SEVERE: { shape: "square", color: "#c34135" },
    EXTENSIVE: { shape: "triangle", color: "#d36b20" },
    MODERATE: { shape: "dot", color: "#697b8f" },
    LIMITED: { shape: "ring", color: "#4d8b65" },
    NOT_DISCLOSED: { shape: "dot", color: "#99a4b2" },
    UNCLEAR: { shape: "dot", color: "#99a4b2" },
};

function drawIcon(size, headline) {
    const canvas = new OffscreenCanvas(size, size);
    const ctx = canvas.getContext("2d");
    const badge = headline ? BADGE[headline] : null;
    ctx.globalAlpha = headline ? 1 : 0.45;

    // the logo: pink rounded square, red dot, the i
    const r = size * 0.22;
    ctx.fillStyle = "#f59abf";
    ctx.beginPath();
    ctx.roundRect(0, 0, size, size, r);
    ctx.fill();
    const k = size / 1024;
    if (size >= 24) {
        ctx.fillStyle = "#c0392b";
        ctx.beginPath();
        ctx.arc(544 * k, 260 * k, 92 * k, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#33202a";
        ctx.save();
        ctx.scale(k, k);
        ctx.fill(new Path2D(LOGO_PATH));
        ctx.restore();
    } else {
        ctx.fillStyle = "#c0392b";
        ctx.beginPath();
        ctx.arc(size * 0.55, size * 0.27, size * 0.12, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#33202a";
        ctx.lineWidth = size * 0.17;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(size * 0.52, size * 0.44);
        ctx.lineTo(size * 0.43, size * 0.8);
        ctx.stroke();
    }

    // the badge in the corner, on a white plate so it reads on the pink
    if (badge) {
        ctx.globalAlpha = 1;
        const c = size * 0.78;
        const w = size * 0.42;
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.arc(c, c, w * 0.62, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = badge.color;
        ctx.strokeStyle = badge.color;
        ctx.beginPath();
        if (badge.shape === "triangle") {
            ctx.moveTo(c, c - w * 0.42);
            ctx.lineTo(c + w * 0.42, c + w * 0.32);
            ctx.lineTo(c - w * 0.42, c + w * 0.32);
            ctx.closePath();
            ctx.fill();
        } else if (badge.shape === "square") {
            ctx.roundRect(c - w * 0.36, c - w * 0.36, w * 0.72, w * 0.72, w * 0.1);
            ctx.fill();
        } else if (badge.shape === "ring") {
            ctx.lineWidth = Math.max(1.5, w * 0.16);
            ctx.arc(c, c, w * 0.32, 0, Math.PI * 2);
            ctx.stroke();
        } else {
            ctx.arc(c, c, w * 0.36, 0, Math.PI * 2);
            ctx.fill();
        }
    }
    return ctx.getImageData(0, 0, size, size);
}

const icons = new Map();

function iconFor(headline) {
    const key = headline || "none";
    if (!icons.has(key)) icons.set(key, { 16: drawIcon(16, headline), 32: drawIcon(32, headline) });
    return icons.get(key);
}

async function setBadge(tabId, url) {
    let headline = null;
    let title = "Imbroglio: this site's privacy rating";
    try {
        const u = new URL(url || "");
        if (["http:", "https:"].includes(u.protocol)) {
            const data = await getData(u.hostname);
            if (data.status === "ready") {
                headline = data.headline;
                title = `Imbroglio: ${data.domain} is rated ${headline.toLowerCase().replace("_", " ")}`;
            } else if (data.status === "not_analyzed") {
                title = `Imbroglio: ${data.domain} is stored but not rated yet`;
            } else if (data.status === "unknown") {
                title = `Imbroglio: ${u.hostname.replace(/^www\./, "")} hasn't been analyzed. Click to request it.`;
            }
        }
    } catch (err) {
        console.warn("imbroglio BG: badge lookup failed", err);
    }
    try {
        await chrome.action.setIcon({ tabId, imageData: iconFor(headline) });
        await chrome.action.setTitle({ tabId, title });
    } catch {
        // the tab may have closed meanwhile
    }
}

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
    try {
        const tab = await chrome.tabs.get(tabId);
        setBadge(tabId, tab.url);
    } catch {
        // gone already
    }
});

chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
    if (change.url || change.status === "complete") setBadge(tabId, tab.url);
});
