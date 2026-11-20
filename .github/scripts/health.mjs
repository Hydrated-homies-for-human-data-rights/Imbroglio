// The health watch (see .github/workflows/health.yml). Looks at Imbroglio
// from the outside every half hour and posts to a Discord webhook only when
// something changes:
//
//   a problem starts      the full list of what's wrong
//   still wrong 6h later  a reminder with the list
//   everything clears     "back to normal", with what cleared
//   once a day, all good  one line with the day's numbers
//
// A problem is remembered by its wording with the numbers taken out, so "has
// waited 25 minutes" and "has waited 55 minutes" are the same problem. The
// state lives in STATE_FILE, carried between runs by actions/cache.
//
// Sends only counts, times and commit ids: never which sites anyone asked
// about (GET /v1/health doesn't know them either). Mentions are off, so
// nothing in a message can ping anyone.
//
// Set DRY_RUN=1 to print the messages instead of posting them.

import { existsSync, readFileSync, writeFileSync, appendFileSync } from 'node:fs';

const SITE_URL = process.env.SITE_URL || 'https://imbroglio.io';
const API_URL = (process.env.IMBROGLIO_API_URL || '').replace(/\/+$/, '');
const API_USER = process.env.IMBROGLIO_API_USER || '';
const API_PASSWORD = process.env.IMBROGLIO_API_PASSWORD || '';
const WEBHOOK = process.env.DISCORD_HEALTH_WEBHOOK || '';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';
const REPO = process.env.GITHUB_REPOSITORY || 'Hydrated-homies-for-human-data-rights/Imbroglio';
const STATE_FILE = process.env.STATE_FILE || '.health-state.json';
const DRY_RUN = process.env.DRY_RUN === '1';
const DIGEST_HOUR_UTC = Number(process.env.DIGEST_HOUR_UTC || 15); // 8 or 9 am in Denver
const REMIND_HOURS = 6;
const DEPLOY_GRACE_MINUTES = 20; // a deploy usually lands within a few minutes of the merge
const TIMEOUT_MS = 20_000;

async function get(url, headers = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { headers, signal: ctrl.signal, redirect: 'follow' });
  } finally {
    clearTimeout(t);
  }
}

async function checkSite(problems) {
  try {
    const res = await get(SITE_URL);
    if (res.status !== 200) {
      problems.push(`imbroglio.io answered ${res.status} instead of 200.`);
    } else if (!res.headers.get('x-frame-options') || !res.headers.get('content-security-policy')) {
      problems.push('imbroglio.io answered without its security headers (check web/next.config.ts and the last deploy).');
    }
  } catch (err) {
    problems.push(`imbroglio.io didn't answer (${err.name}).`);
  }
}

async function checkApi(problems) {
  if (!API_URL) {
    problems.push('The health watch has no IMBROGLIO_API_URL secret, so the API, queue and budget were not checked.');
    return null;
  }
  try {
    const res = await get(`${API_URL}/healthz`);
    if (res.status !== 200) {
      problems.push(`The API's /healthz answered ${res.status}.`);
      return null;
    }
  } catch (err) {
    problems.push(`The API didn't answer (${err.name}).`);
    return null;
  }
  const auth = 'Basic ' + Buffer.from(`${API_USER}:${API_PASSWORD}`).toString('base64');
  try {
    const res = await get(`${API_URL}/v1/health`, { Authorization: auth });
    if (res.status === 401) {
      problems.push("The health watch can't log in to the API (check IMBROGLIO_API_USER and IMBROGLIO_API_PASSWORD).");
      return null;
    }
    const body = await res.json();
    for (const p of body.problems || []) problems.push(p);
    return body;
  } catch (err) {
    problems.push(`The API's health report couldn't be read (${err.name}).`);
    return null;
  }
}

// The latest commit on main should have Vercel's and Railway's deploy
// statuses. On 2026-11-20 Vercel never got a push for main and nothing said so.
async function checkDeploys(problems) {
  const headers = { Accept: 'application/vnd.github+json', ...(GITHUB_TOKEN && { Authorization: `Bearer ${GITHUB_TOKEN}` }) };
  try {
    const commit = await (await get(`https://api.github.com/repos/${REPO}/commits/main`, headers)).json();
    const sha = commit.sha;
    const ageMin = (Date.now() - Date.parse(commit.commit.committer.date)) / 60000;
    if (!sha || ageMin < DEPLOY_GRACE_MINUTES) return;
    const { statuses = [] } = await (await get(`https://api.github.com/repos/${REPO}/commits/${sha}/status`, headers)).json();
    const short = sha.slice(0, 7);
    const want = { Vercel: /vercel/i, 'Railway API': /pipeline/i, 'Railway worker': /worker/i };
    for (const [name, re] of Object.entries(want)) {
      const s = statuses.find((x) => re.test(x.context));
      if (!s) problems.push(`main ${short} has no ${name} deploy (it never started; redeploy main by hand).`);
      else if (s.state === 'failure' || s.state === 'error') problems.push(`The ${name} deploy of main ${short} failed.`);
    }
  } catch (err) {
    problems.push(`GitHub couldn't be asked about the latest deploy (${err.name}).`);
  }
}

const keyOf = (p) => p.replace(/\d+(\.\d+)?/g, '#').replace(/\b[0-9a-f]{7}\b/g, '#');

function loadState() {
  try {
    if (existsSync(STATE_FILE)) return JSON.parse(readFileSync(STATE_FILE, 'utf8'));
  } catch {}
  return { problems: [], lastPost: null, lastDigest: null };
}

function bullets(list) {
  return list.map((p) => `• ${p}`).join('\n');
}

function digest(h) {
  if (!h) return 'Imbroglio is running normally.';
  return `Imbroglio is running normally. ${h.finished_last_hour} jobs finished in the last hour, ` +
    `${h.queued} queued, $${h.spent_24h_usd.toFixed(2)} of $${h.budget_usd.toFixed(2)} analysis budget used in 24 hours.`;
}

async function post(content) {
  const text = content.length > 1900 ? content.slice(0, 1900) + '\n…' : content;
  console.log(`--- message ---\n${text}\n`);
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${text}\n\n`);
  if (DRY_RUN) return;
  if (!WEBHOOK) {
    console.log('::notice::DISCORD_HEALTH_WEBHOOK is not set, so nothing was posted (see the run summary).');
    return;
  }
  const res = await fetch(`${WEBHOOK}?wait=true`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: text, username: 'Imbroglio health', allowed_mentions: { parse: [] } }),
  });
  if (!res.ok) console.log(`::warning::Discord answered ${res.status}: ${(await res.text()).slice(0, 200)}`);
}

const problems = [];
await checkSite(problems);
const report = await checkApi(problems);
await checkDeploys(problems);

const state = loadState();
const now = new Date();
const before = new Map(state.problems.map((p) => [keyOf(p), p]));
const current = new Map(problems.map((p) => [keyOf(p), p]));
const started = [...current.keys()].filter((k) => !before.has(k));
const cleared = [...before.keys()].filter((k) => !current.has(k)).map((k) => before.get(k));
const hoursSincePost = state.lastPost ? (now - Date.parse(state.lastPost)) / 3_600_000 : Infinity;

let message = null;
if (started.length) {
  message = `**Imbroglio needs a look**\n${bullets(problems)}`;
  if (cleared.length) message += `\n\nCleared since last check:\n${bullets(cleared)}`;
} else if (cleared.length && !problems.length) {
  message = `**Imbroglio is back to normal**\nCleared:\n${bullets(cleared)}`;
} else if (cleared.length) {
  message = `**Imbroglio: some problems cleared**\nCleared:\n${bullets(cleared)}\n\nStill open:\n${bullets(problems)}`;
} else if (problems.length && hoursSincePost >= REMIND_HOURS) {
  message = `**Imbroglio still needs a look**\n${bullets(problems)}`;
}

const today = now.toISOString().slice(0, 10);
const digestDue = !problems.length && now.getUTCHours() >= DIGEST_HOUR_UTC && state.lastDigest !== today;

if (message) {
  await post(message);
  state.lastPost = now.toISOString();
} else if (digestDue) {
  await post(digest(report));
  state.lastDigest = today;
} else {
  console.log(problems.length ? `No change: ${problems.length} open problem(s).` : 'All good, nothing to post.');
  if (problems.length) console.log(bullets(problems));
}

state.problems = problems;
writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
