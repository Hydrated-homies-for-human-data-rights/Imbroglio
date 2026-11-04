// Posts GitHub activity on this repo to the team's Discord channel through
// the team's bot (see .github/workflows/discord.yml). Three kinds of post:
//
//   push                  who pushed how many commits to which branch, with
//                         the commit messages, no ping
//   pull_request opened   "@everyone PR #N needs a review", with a 👀
//                         reaction already on it: whoever takes the review
//                         reacts, and the others see it is taken
//   pull_request_review   approved or changes requested, no ping
//
// What is sent is the repository's own data (branch names, commit messages,
// PR titles, GitHub logins) and nothing else. Mentions are limited to the one
// @everyone on a review request: allowed_mentions never parses users or
// roles out of commit messages or titles, so text can't ping anyone.
//
// Set DRY_RUN=1 to print the payloads instead of sending them.

import { readFileSync } from 'node:fs';

const DISCORD_API = 'https://discord.com/api/v10';
const TOKEN = process.env.DISCORD_BOT_TOKEN;
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID;
const DRY_RUN = process.env.DRY_RUN === '1';
const EVENT_NAME = process.env.GITHUB_EVENT_NAME;
const EYES = '👀';
const MAX_COMMITS = 6;

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

if (!EVENT_NAME) fail('GITHUB_EVENT_NAME is not set; this runs inside GitHub Actions');
if (!DRY_RUN && (!TOKEN || !CHANNEL_ID)) fail('DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID are required');

const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
const repo = event.repository?.full_name ?? process.env.GITHUB_REPOSITORY ?? 'the repo';
const repoName = repo.split('/').pop();

// Discord's markdown: keep a line of someone's text from opening formatting.
const plain = (s) => String(s ?? '').replace(/[*_~`|>]/g, '\\$&').replace(/\s+/g, ' ').trim();
const firstLine = (s) => String(s ?? '').split('\n')[0];
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

function buildPush() {
  const branch = event.ref?.replace(/^refs\/heads\//, '') ?? '?';
  if (event.deleted) return null; // a deleted branch is not news
  const commits = event.commits ?? [];
  const who = event.pusher?.name ?? event.sender?.login ?? 'someone';
  if (commits.length === 0) return null; // a tag or a force-push with nothing new
  const n = commits.length;
  const lines = commits.slice(-MAX_COMMITS).map((c) => `• ${clip(plain(firstLine(c.message)), 100)}`);
  if (n > MAX_COMMITS) lines.unshift(`• … ${n - MAX_COMMITS} more`);
  const header = `**${plain(who)}** pushed ${n === 1 ? 'a commit' : `${n} commits`} to \`${plain(branch)}\` on ${repoName}`;
  return {
    content: [header, ...lines, `<${event.compare}>`].join('\n'),
    allowed_mentions: { parse: [] },
  };
}

function buildReviewRequest() {
  const pr = event.pull_request;
  const author = pr.user?.login ?? 'someone';
  const what = event.action === 'ready_for_review' ? 'is ready for review' : 'needs a review';
  return {
    content: [
      `@everyone **PR #${pr.number}** ${what}: ${clip(plain(pr.title), 120)} (by ${plain(author)})`,
      `<${pr.html_url}>`,
      `React with ${EYES} when you take it, so only one person reviews.`,
    ].join('\n'),
    allowed_mentions: { parse: ['everyone'] },
    react: EYES,
  };
}

function buildReview() {
  const pr = event.pull_request;
  const review = event.review;
  const by = plain(review.user?.login ?? 'someone');
  const state = (review.state ?? '').toLowerCase();
  let line;
  if (state === 'approved') line = `✅ **PR #${pr.number}** approved by ${by}: ${clip(plain(pr.title), 100)}`;
  else if (state === 'changes_requested') line = `✏️ **PR #${pr.number}**: ${by} asked for changes on ${clip(plain(pr.title), 100)}`;
  else return null; // a plain comment review is not news
  return { content: `${line}\n<${pr.html_url}>`, allowed_mentions: { parse: [] } };
}

async function discord(method, path, body) {
  const res = await fetch(`${DISCORD_API}${path}`, {
    method,
    headers: {
      Authorization: `Bot ${TOKEN}`,
      'Content-Type': 'application/json',
      'User-Agent': `ImbroglioRepoBot (github.com/${repo}, 1.0)`,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) fail(`Discord ${method} ${path} -> ${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

const message =
  EVENT_NAME === 'push' ? buildPush()
  : EVENT_NAME === 'pull_request' ? buildReviewRequest()
  : EVENT_NAME === 'pull_request_review' ? buildReview()
  : null;

if (!message) {
  console.log(`nothing to post for ${EVENT_NAME}${event.action ? ` ${event.action}` : ''}`);
  process.exit(0);
}

const { react, ...payload } = message;
if (DRY_RUN) {
  console.log(JSON.stringify({ payload, react }, null, 2));
  process.exit(0);
}
const posted = await discord('POST', `/channels/${CHANNEL_ID}/messages`, payload);
if (react) {
  await discord('PUT', `/channels/${CHANNEL_ID}/messages/${posted.id}/reactions/${encodeURIComponent(react)}/@me`);
}
console.log(`posted ${EVENT_NAME}${event.action ? ` ${event.action}` : ''} as message ${posted.id}`);
