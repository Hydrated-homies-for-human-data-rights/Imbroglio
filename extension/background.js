// Looks up the current site in the Imbroglio API and draws the toolbar
// badge. Only cached results are shown: this never asks the API to analyze
// a new site.
//
// Privacy: the site's name never leaves the browser. We hash it with
// sha256 and send only the first 3 hex characters of the hash to /v1/lookup:
// 4,096 buckets, so each one is shared by hundreds of the web's popular
// sites and the server can't tell which of them you are on. We pick our site
// out of the answer by its full hash. (5 characters, before 1.0, came close
// to naming the site: about one popular site per bucket.)
//
// API address: defaults to the website, which forwards lookups to the API and
// adds the API's password on its server, so nothing secret ships in the
// extension. Lookups only read cached results; they never start an analysis.
// For local development, add "http://localhost:8765/*" to host_permissions
// in manifest.json (never in a store build), reload, and run this in the
// service worker console:
//   chrome.storage.local.set({ apiBase: "http://localhost:8765" })
// (and chrome.storage.local.remove("apiBase") to go back).

const DEFAULT_API_BASE = "https://imbroglio.io/api";
const PREFIX_LENGTH = 3; // the website's lookup route accepts 3 (and 5, for copies from before 1.0)
const CACHE_MS = 10 * 60 * 1000; // a rated site's result is reused this long before being looked up again
const MISS_MS = 60 * 1000; // an unrated or unknown site is looked up again sooner, since it may be rated any minute
// (a failed lookup waits this long too, so a busy API isn't asked again on every tab switch)
const MAX_CANDIDATES = 3; // "a.b.c.example.com" asks about c.example.com, example.com and nothing deeper

async function settings() {
    const s = await chrome.storage.local.get(["apiBase"]);
    return { base: (s.apiBase || DEFAULT_API_BASE).replace(/\/+$/, "") };
}

async function sha256Hex(text) {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// "www.old.reddit.com" -> ["old.reddit.com", "reddit.com"]. We store sites
// under their main domain, so subdomains fall back to their parents, at most
// MAX_CANDIDATES of them. Addresses (192.168.1.1, [::1]) and names without a
// dot (intranet hosts, localhost) aren't websites we rate, so nothing is sent.
function candidates(hostname) {
    const host = hostname.toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
    if (!host.includes(".") || host.includes(":") || /^[0-9.]+$/.test(host)) return [];
    const labels = host.split(".");
    const out = [];
    for (let i = 0; i <= labels.length - 2; i++) {
        out.push(labels.slice(i).join("."));
    }
    return out.slice(-MAX_CANDIDATES);
}

async function lookup(domain, api) {
    const hash = await sha256Hex(domain);
    const headers = { Accept: "application/json" };
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
        return { status: "not_analyzed", domain, hash: entry.hash, documents: entry.documents };
    }
    const s = entry.scores;
    return {
        status: "ready",
        domain,
        hash: entry.hash,
        headline: s.headline,
        score: s.score ?? null, // out of 100; null for an UNCLEAR or NOT_DISCLOSED site
        categories: s.categories.map((c) => ({ key: c.key, name: c.name, tier: c.tier, findings: c.findings })),
        analyzedAt: s.analyzed_at,
        changedAt: entry.changed_at || null, // when a policy change was last detected
        rubric: s.rubric_version,
        scorer: s.scorer_version,
        documents: entry.documents,
        links: entry.links || [], // the site's own opt-out and settings pages
    };
}

// Results by hostname, so switching tabs doesn't repeat the lookup. `fresh`
// (the popup opening) looks again unless the site is already rated, so
// someone who just requested a site sees its rating once it's ready.
const recent = new Map();

async function getData(hostname, fresh = false) {
    const hit = recent.get(hostname);
    if (hit) {
        const ready = hit.data.status === "ready";
        if (Date.now() - hit.at < (ready ? CACHE_MS : MISS_MS) && (ready || !fresh)) return hit.data;
    }
    const api = await settings();
    let data = { status: "unknown" };
    try {
        for (const domain of candidates(hostname)) {
            const entry = await lookup(domain, api);
            if (entry) {
                data = toSiteData(domain, entry);
                break;
            }
        }
    } catch (err) {
        data = { status: "error", error: String(err.message || err) };
    }
    recent.set(hostname, { at: Date.now(), data });
    return data;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "getData") {
        getData(request.domain, request.fresh === true)
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
// corner the site's worst level in the scorecard's own shape and color (the
// Figma's "toolbar badge = the site's worst level"), straight on the pink.
// The score stays in the hover text, not on the icon. A site we haven't rated
// gets the icon dimmed with no badge. At 16 px the curvy i becomes a slanted bar with
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

    // the badge in the corner: the level's shape in its color, no plate
    if (badge) {
        ctx.globalAlpha = 1;
        const c = size * 0.76;
        const w = size * 0.54;
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

// --- the two notifications --------------------------------------------------------
//
// Both sit behind a switch in the popup's footer, on until turned off, and
// each fires at most once per site per occasion when a tab finishes
// loading. What the extension remembers about a site is a date, kept under
// a key made from the site's name with a secret random to this install
// (HMAC-SHA-256), never the name itself. Plain sha256 wouldn't do: anyone can
// hash every rated site and match, but without this install's secret the keys
// say nothing about where you have been.
//
// The Extensive nudge: the first time you land on a site rated Extensive
// or Severe, one notification says so and names the category behind it;
// clicking it opens the report.
//
// The change alert: the first visit to a site only records which policy
// version you have seen. When a later visit finds a change detected after
// that, one notification says the policy changed, with the date; clicking
// it opens the change history. The words in a notification are our own
// plus the domain and a date; nothing from the network is shown.

const NUDGE_TIERS = new Set(["EXTENSIVE", "SEVERE"]);

let hmacKey = null;
async function siteKey(kind, domain) {
    if (!hmacKey) {
        let { installSecret } = await chrome.storage.local.get("installSecret");
        if (!installSecret) {
            installSecret = [...crypto.getRandomValues(new Uint8Array(32))]
                .map((b) => b.toString(16).padStart(2, "0")).join("");
            await chrome.storage.local.set({ installSecret });
        }
        const raw = new Uint8Array(installSecret.match(/../g).map((h) => parseInt(h, 16)));
        hmacKey = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    }
    const mac = await crypto.subtle.sign("HMAC", hmacKey, new TextEncoder().encode(domain));
    return `${kind}:` + [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Before 1.0 the records sat under the plain sha256 ("nudged:<hash>",
// "seen:<hash>"), which can be matched against the public list of rated
// sites. Drop them; the next visit records a site again.
chrome.runtime.onInstalled.addListener(async () => {
    const all = await chrome.storage.local.get(null);
    const old = Object.keys(all).filter((k) => k.startsWith("nudged:") || k.startsWith("seen:"));
    if (old.length) await chrome.storage.local.remove(old);
});

async function maybeNudge(data) {
    if (!NUDGE_TIERS.has(data.headline) || !data.domain) return;
    const key = await siteKey("n", data.domain);
    const got = await chrome.storage.local.get(["warnExtensive", key]);
    if (got.warnExtensive === false || got[key]) return;
    await chrome.storage.local.set({ [key]: Date.now() });
    const tier = data.headline.charAt(0) + data.headline.slice(1).toLowerCase();
    const behind = data.categories.filter((c) => c.tier === data.headline).map((c) => c.name);
    const because = behind.length ? ` for ${behind.join(" and ")}` : "";
    chrome.notifications.create(`imbroglio:rating:${data.domain}`, {
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: `${data.domain} is rated ${tier}`,
        message: `Imbroglio rated this site ${tier}${because}. Click to see the quotes behind it.`,
        priority: 0,
    });
}

async function maybeChangeAlert(data) {
    if (!data.changedAt || !data.domain) return;
    const changed = Date.parse(data.changedAt);
    if (isNaN(changed)) return;
    const key = await siteKey("s", data.domain);
    const got = await chrome.storage.local.get(["policyChanges", key]);
    if (got.policyChanges === false) return;
    const seen = got[key];
    if (seen === undefined) {
        await chrome.storage.local.set({ [key]: changed }); // first visit: nothing to compare yet
        return;
    }
    if (changed <= seen) return;
    await chrome.storage.local.set({ [key]: changed });
    const when = new Date(changed).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    chrome.notifications.create(`imbroglio:change:${data.domain}`, {
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: `${data.domain} changed its policy`,
        message: `A change to its privacy policy or terms was found on ${when}. Click to see what changed.`,
        priority: 0,
    });
}

chrome.notifications.onClicked.addListener((id) => {
    const m = /^imbroglio:(rating|change):(.+)$/.exec(id);
    if (!m) return;
    const page = `https://imbroglio.io/site/${encodeURIComponent(m[2])}` + (m[1] === "change" ? "/history" : "");
    chrome.tabs.create({ url: page });
    chrome.notifications.clear(id);
});

async function setBadge(tabId, url, loaded = false) {
    let headline = null;
    let score = null;
    let title = "Imbroglio: this site's privacy rating";
    try {
        const u = new URL(url || "");
        if (["http:", "https:"].includes(u.protocol)) {
            const data = await getData(u.hostname);
            if (data.status === "ready") {
                headline = data.headline;
                score = data.score ?? null;
                title = `Imbroglio: ${data.domain} is rated ${headline.toLowerCase().replace("_", " ")}`
                    + (score != null ? `, ${score} out of 100` : "");
                if (loaded) {
                    maybeNudge(data).catch((err) => console.warn("imbroglio BG: nudge failed", err));
                    maybeChangeAlert(data).catch((err) => console.warn("imbroglio BG: change alert failed", err));
                }
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
    if (change.url || change.status === "complete") setBadge(tabId, tab.url, change.status === "complete");
});
