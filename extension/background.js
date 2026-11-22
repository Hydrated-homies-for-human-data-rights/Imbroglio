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
// One prefix per site, with one exception: on a subdomain (mail.example.com)
// that has no rating of its own, a second prefix asks about its main domain
// (example.com). Some subdomains are rated as sites of their own
// (accounts.firefox.com), so the name you're on is always asked about first.
//
// API address: defaults to the website, which forwards lookups to the API and
// adds the API's password on its server, so nothing secret ships in the
// extension. For local development, add "http://localhost:8765/*" to
// host_permissions in manifest.json (never in a store build), reload, and run
// this in the service worker console:
//   chrome.storage.local.set({ apiBase: "http://localhost:8765" })
// (and chrome.storage.local.remove("apiBase") to go back).

const DEFAULT_API_BASE = "https://imbroglio.io/api";
const PREFIX_LENGTH = 3; // the only length the website's lookup route accepts
const CACHE_MS = 10 * 60 * 1000; // a rated site's result is reused this long before being looked up again
const MISS_MS = 60 * 1000; // an unrated or unknown site is looked up again sooner, since it may be rated any minute
// (a failed lookup waits this long too, so a busy API isn't asked again on every tab switch)
const TIMEOUT_MS = 8000; // a lookup that takes longer than this counts as a failed one
const MAX_WAIT_MS = 60 * 60 * 1000; // the longest a Retry-After from the API can hold lookups back

async function settings() {
    const s = await chrome.storage.local.get(["apiBase"]);
    return { base: (s.apiBase || DEFAULT_API_BASE).replace(/\/+$/, "") };
}

async function sha256Hex(text) {
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// --- which names to ask about -------------------------------------------------------

// Endings under which each name is a separate site: two-part country
// suffixes (bbc.co.uk is the site, not co.uk), and hosting platforms whose
// subdomains belong to different people (someone's app on vercel.app is not
// Vercel). The same country list as pipeline/imbroglio/locate.py. A name not
// covered here falls back to its last two labels.
const SUFFIXES = new Set([
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.jp",
    "ne.jp", "or.jp", "com.br", "com.cn", "co.nz", "co.in", "com.mx", "co.kr",
    "com.tr", "com.sg", "co.za", "com.ar", "com.tw", "com.hk",
    "github.io", "gitlab.io", "vercel.app", "netlify.app", "pages.dev", "workers.dev",
    "herokuapp.com", "web.app", "firebaseapp.com", "onrender.com", "fly.dev", "up.railway.app",
]);

// Names that never reach the public web: your own computer, your network,
// and the endings set aside for testing and private use.
const PRIVATE_ENDINGS = ["localhost", "local", "internal", "intranet", "lan", "home", "corp",
    "home.arpa", "test", "example", "invalid", "onion"];

// The site name we'd look up: lowercase, no trailing dot, no "www.". Null
// for anything that isn't a public website: addresses (192.168.1.1,
// [::1]), names without a dot, and private endings. Nothing is sent for those.
function publicName(hostname) {
    const host = String(hostname || "").toLowerCase().replace(/\.$/, "").replace(/^www\./, "");
    if (!host.includes(".") || host.includes(":") || host.startsWith("[") || /^[0-9.]+$/.test(host)) return null;
    if (PRIVATE_ENDINGS.some((end) => host === end || host.endsWith(`.${end}`))) return null;
    return host;
}

// "policies.google.com" -> "google.com"; "news.bbc.co.uk" -> "bbc.co.uk".
function mainDomain(host) {
    const labels = host.split(".");
    for (let i = 1; i < labels.length; i++) {
        if (SUFFIXES.has(labels.slice(i).join("."))) return labels.slice(i - 1).join(".");
    }
    return labels.slice(-2).join(".");
}

// The names to ask about, in order: the site itself, then its main domain
// if that's different. "www.old.reddit.com" -> ["old.reddit.com",
// "reddit.com"]; "a.b.example.com" -> ["a.b.example.com", "example.com"];
// "github.com" -> ["github.com"]; "localhost" -> [].
function candidates(hostname) {
    const host = publicName(hostname);
    if (!host) return [];
    const main = mainDomain(host);
    return main === host ? [host] : [host, main];
}

// --- the lookup -------------------------------------------------------------------

// chrome.storage.session lives in memory and is cleared when the browser
// closes, but unlike a variable it survives the service worker going to
// sleep. Chrome before 102 lacks it; those fall back to a Map that lasts as
// long as the worker does.
const memory = new Map();
const session = chrome.storage.session || {
    async get(keys) {
        if (keys === null) return Object.fromEntries(memory);
        const out = {};
        for (const k of [].concat(keys)) if (memory.has(k)) out[k] = memory.get(k);
        return out;
    },
    async set(items) {
        for (const [k, v] of Object.entries(items)) memory.set(k, v);
    },
    async remove(keys) {
        for (const k of [].concat(keys)) memory.delete(k);
    },
};

// When the API last said to slow down (429 or 503), and until when: no
// lookup goes out before then, from any tab.
const NOT_BEFORE = "lookupNotBefore";

// Retry-After is either seconds or an HTTP date. Without a usable one we
// wait as long as after any failed lookup.
function retryAfterMs(header, now = Date.now()) {
    let ms = MISS_MS;
    if (header && /^\s*\d+\s*$/.test(header)) ms = Number(header) * 1000;
    else if (header && !isNaN(Date.parse(header))) ms = Date.parse(header) - now;
    return Math.min(Math.max(ms, 0), MAX_WAIT_MS);
}

async function lookup(domain, api) {
    const held = (await session.get(NOT_BEFORE))[NOT_BEFORE];
    if (held && Date.now() < held.until) throw new Error(`API returned ${held.status}`);
    const hash = await sha256Hex(domain);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
        const res = await fetch(`${api.base}/v1/lookup/${hash.slice(0, PREFIX_LENGTH)}`, {
            headers: { Accept: "application/json" },
            signal: controller.signal,
        });
        if (res.status === 429 || res.status === 503) {
            const until = Date.now() + retryAfterMs(res.headers.get("Retry-After"));
            await session.set({ [NOT_BEFORE]: { until, status: res.status } });
        }
        if (!res.ok) {
            throw new Error(`API returned ${res.status}`);
        }
        const body = await res.json();
        return (body.sites || []).find((s) => s.hash === hash) || null;
    } catch (err) {
        // a timeout reads like any other network failure
        if (err && err.name === "AbortError") throw new Error("lookup timed out");
        throw err;
    } finally {
        clearTimeout(timer);
    }
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

// Results by site, kept in session storage so switching tabs doesn't repeat
// the lookup, even after the worker has slept. Each is filed under an HMAC
// of the site's name (siteKey below), so an unrated site you visited isn't
// named there. `fresh` (the popup opening) looks again unless the site is
// already rated, so someone who just requested a site sees its rating once
// it's ready. Lookups already on their way are shared, so a tab that
// finishes loading while the popup opens sends its prefix once.
const CACHE_PREFIX = "c:";
const inflight = new Map();
let lastPrune = 0;

async function pruneCache(now) {
    if (now - lastPrune < MISS_MS) return;
    lastPrune = now;
    const all = await session.get(null);
    const old = Object.keys(all).filter((k) => k.startsWith(CACHE_PREFIX) && now - all[k].at >= CACHE_MS);
    if (old.length) await session.remove(old);
}

async function lookUpSite(names) {
    const api = await settings();
    let data = { status: "unknown" };
    for (const domain of names) {
        const entry = await lookup(domain, api);
        if (!entry) continue;
        const found = toSiteData(domain, entry);
        if (found.status === "ready") return found;
        // stored but not rated: say so if the main domain has nothing better
        if (data.status === "unknown") data = found;
    }
    return data;
}

async function getData(hostname, fresh = false) {
    const names = candidates(hostname);
    if (!names.length) return { status: "not_public" };
    const key = await siteKey("c", names[0]); // "c:<hmac>", matching CACHE_PREFIX
    const hit = (await session.get(key))[key];
    if (hit) {
        const ready = hit.data.status === "ready";
        if (Date.now() - hit.at < (ready ? CACHE_MS : MISS_MS) && (ready || !fresh)) return hit.data;
    }
    if (!inflight.has(key)) {
        const run = (async () => {
            let data;
            try {
                data = await lookUpSite(names);
            } catch (err) {
                data = { status: "error", error: String(err.message || err) };
            }
            const now = Date.now();
            await session.set({ [key]: { at: now, data } });
            pruneCache(now).catch(() => {});
            return data;
        })();
        inflight.set(key, run);
        run.finally(() => inflight.delete(key)).catch(() => {});
    }
    return inflight.get(key);
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
// loading. What the extension remembers about a site is a date (or 0 for
// "no change known yet"), kept under a key made from the site's name with a
// secret random to this install (HMAC-SHA-256), never the name itself. Plain
// sha256 wouldn't do: anyone can hash every rated site and match, but
// without this install's secret the keys say nothing about where you have
// been.
//
// The Extensive nudge: the first time you land on a site rated Extensive
// or Severe, one notification says so and names the category behind it;
// clicking it opens the report.
//
// The change alert: the first visit to a site only records the last policy
// change known then (or that none is known). When a later visit finds a
// change detected after that, one notification says the policy changed,
// with the date; clicking it opens the change history. The words in a
// notification are our own plus the domain and a date; nothing from the
// network is shown.

const NUDGE_TIERS = new Set(["EXTENSIVE", "SEVERE"]);

// The HMAC key, made once per worker. Every caller waits on the same
// promise, so two lookups at once on a fresh install can't each create a
// different secret and file records under one that is then overwritten.
let hmacKey = null;
function installKey() {
    if (!hmacKey) {
        hmacKey = (async () => {
            let { installSecret } = await chrome.storage.local.get("installSecret");
            if (!installSecret) {
                installSecret = [...crypto.getRandomValues(new Uint8Array(32))]
                    .map((b) => b.toString(16).padStart(2, "0")).join("");
                await chrome.storage.local.set({ installSecret });
            }
            const raw = new Uint8Array(installSecret.match(/../g).map((h) => parseInt(h, 16)));
            return crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
        })();
        hmacKey.catch(() => { hmacKey = null; }); // try again next time
    }
    return hmacKey;
}

async function siteKey(kind, domain) {
    const mac = await crypto.subtle.sign("HMAC", await installKey(), new TextEncoder().encode(domain));
    return `${kind}:` + [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Each record is read, checked and written in one go, one at a time, so
// two tabs finishing the same site together can't both see "no record" and
// both notify.
let records = Promise.resolve();
function oneAtATime(task) {
    const run = records.then(task);
    records = run.catch(() => {});
    return run;
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
    await oneAtATime(async () => {
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
    });
}

// What to do on a visit, given the record (undefined on the first visit)
// and the last change the lookup knows of (0 when none is known): the value
// to store, if any, and whether to alert.
function changeDecision(seen, changed) {
    if (seen === undefined) return { store: changed, alert: false }; // first visit: note where things stand
    if (changed > seen) return { store: changed, alert: true };
    return { store: undefined, alert: false };
}

async function maybeChangeAlert(data) {
    if (!data.domain) return;
    const parsed = data.changedAt ? Date.parse(data.changedAt) : NaN;
    const changed = isNaN(parsed) ? 0 : parsed;
    const key = await siteKey("s", data.domain);
    await oneAtATime(async () => {
        const got = await chrome.storage.local.get(["policyChanges", key]);
        if (got.policyChanges === false) return;
        const { store, alert } = changeDecision(got[key], changed);
        if (store !== undefined) await chrome.storage.local.set({ [key]: store });
        if (!alert) return;
        const when = new Date(changed).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        chrome.notifications.create(`imbroglio:change:${data.domain}`, {
            type: "basic",
            iconUrl: "icons/icon128.png",
            title: `${data.domain} changed its policy`,
            message: `A change to its privacy policy or terms was found on ${when}. Click to see what changed.`,
            priority: 0,
        });
    });
}

chrome.notifications.onClicked.addListener((id) => {
    const m = /^imbroglio:(rating|change):(.+)$/.exec(id);
    if (!m) return;
    const page = `https://imbroglio.io/site/${encodeURIComponent(m[2])}` + (m[1] === "change" ? "/history" : "");
    chrome.tabs.create({ url: page });
    chrome.notifications.clear(id);
});

// --- keeping the badge on the right tab -------------------------------------------
//
// A lookup can finish after its tab has moved on to another site. Each
// badge update gets a number per tab; when the answer arrives it is drawn
// only if the tab still shows the same host and no newer update for the
// tab has started since.

const badgeRuns = new Map();

async function stillShows(tabId, hostname) {
    try {
        const tab = await chrome.tabs.get(tabId);
        return new URL(tab.url || "").hostname === hostname;
    } catch {
        return false; // closed, or no address we can read
    }
}

async function setBadge(tabId, url, loaded = false) {
    const run = (badgeRuns.get(tabId) || 0) + 1;
    badgeRuns.set(tabId, run);
    let headline = null;
    let score = null;
    let title = "Imbroglio: this site's privacy rating";
    let host = null;
    let data = null;
    try {
        const u = new URL(url || "");
        if (["http:", "https:"].includes(u.protocol)) {
            host = u.hostname;
            data = await getData(host);
            if (data.status === "ready") {
                headline = data.headline;
                score = data.score ?? null;
                title = `Imbroglio: ${data.domain} is rated ${headline.toLowerCase().replace("_", " ")}`
                    + (score != null ? `, ${score} out of 100` : "");
            } else if (data.status === "not_analyzed") {
                title = `Imbroglio: ${data.domain} is stored but not rated yet`;
            } else if (data.status === "unknown") {
                title = `Imbroglio: ${u.hostname.replace(/^www\./, "")} hasn't been analyzed. Click to request it.`;
            } else if (data.status === "not_public") {
                title = "Imbroglio: rates public websites only";
            }
        }
    } catch (err) {
        console.warn("imbroglio BG: badge lookup failed", err);
    }
    if (host !== null && !(await stillShows(tabId, host))) return; // the tab has moved on
    // The tab is still on this site, so the notifications hold even if a
    // newer update (a tab switch, say) is about to redraw the same badge.
    if (loaded && data && data.status === "ready") {
        maybeNudge(data).catch((err) => console.warn("imbroglio BG: nudge failed", err));
        maybeChangeAlert(data).catch((err) => console.warn("imbroglio BG: change alert failed", err));
    }
    if (badgeRuns.get(tabId) !== run) return; // a newer update for this tab draws it
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

chrome.tabs.onRemoved.addListener((tabId) => badgeRuns.delete(tabId));
