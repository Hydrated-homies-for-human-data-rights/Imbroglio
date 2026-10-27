const DOC_NAMES = { privacy: "Privacy Policy", terms: "Terms of Service" };
const WEBSITE = "https://imbroglio.io";

function showMessage(text, link) {
  document.getElementById('overall-badge').style.display = 'none';
  document.getElementById('p-subtitle').style.display = 'none';
  const p = document.createElement('p');
  p.textContent = text;
  document.getElementById('p-list').replaceChildren(...(link ? [p, makeLink(link)] : [p]));
}

// Popup links don't open on their own, so open them in a new tab.
function makeLink(link) {
  const a = document.createElement('a');
  a.className = 'p-link';
  a.href = link.url;
  a.textContent = link.text;
  a.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: link.url });
  });
  return a;
}

// Requests go through the website, where the per-visitor and daily request
// limits apply. Opening the link is the user's choice to tell us the site.
function requestLink(domain) {
  return { text: 'Request it on imbroglio.io', url: `${WEBSITE}/search?q=${encodeURIComponent(domain)}` };
}

function reportLink(domain) {
  return { text: 'See the full report', url: `${WEBSITE}/site/${encodeURIComponent(domain)}` };
}

function badge(level) {
  const span = document.createElement('span');
  span.className = `p-badge p-${level.toLowerCase()}`;
  span.textContent = level.replace('_', ' ');
  return span;
}

function render(siteData) {
  document.getElementById('domain-name').textContent = siteData.domain;

  const overallBadge = document.getElementById('overall-badge');
  overallBadge.replaceWith(Object.assign(badge(siteData.overall), { id: 'overall-badge' }));

  const docs = (siteData.documents || []).map((d) => DOC_NAMES[d] || d).join(' + ');
  const analyzed = siteData.analyzedAt ? siteData.analyzedAt.slice(0, 10) : 'unknown';
  document.getElementById('p-meta').textContent = `Analyzed ${analyzed} · ${docs} · rubric ${siteData.rubric}`;

  const listContainer = document.getElementById('p-list');
  for (const [category, data] of Object.entries(siteData.scores)) {
    const findings = data.findings || 0;

    const row = document.createElement('div');
    row.className = 'p-row';
    const name = document.createElement('div');
    name.textContent = category;
    const right = document.createElement('div');
    right.className = 'p-right';
    const count = document.createElement('span');
    count.className = 'p-findings';
    count.textContent = `${findings} finding${findings !== 1 ? 's' : ''}`;
    right.append(badge(data.level || 'UNKNOWN'), count);
    row.append(name, right);
    listContainer.appendChild(row);
  }
  listContainer.appendChild(makeLink(reportLink(siteData.domain)));
}

document.addEventListener('DOMContentLoaded', async () => {
  try {
    // activeTab lets us read this tab's address only because the user clicked the icon.
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab && tab.url ? new URL(tab.url) : null;
    if (!url || !['http:', 'https:'].includes(url.protocol)) {
      document.getElementById('domain-name').textContent = 'Imbroglio';
      showMessage('Open a website to see its privacy ratings.');
      return;
    }
    document.getElementById('domain-name').textContent = url.hostname.replace(/^www\./, '');

    chrome.runtime.sendMessage({ action: "getData", domain: url.hostname }, (response) => {
      if (chrome.runtime.lastError || !response) {
        console.error("Error communicating with background:", chrome.runtime.lastError);
        showMessage("Something went wrong. Try again.");
        return;
      }
      const siteData = response.data;
      if (siteData.status === 'ready') {
        render(siteData);
      } else if (siteData.status === 'not_analyzed') {
        document.getElementById('domain-name').textContent = siteData.domain;
        showMessage("We have this site's documents but haven't rated them yet.", reportLink(siteData.domain));
      } else if (siteData.status === 'error') {
        showMessage(`Couldn't reach the Imbroglio API (${siteData.error}).`);
      } else {
        showMessage("We haven't analyzed this site yet.", requestLink(url.hostname.replace(/^www\./, '')));
      }
    });
  } catch (error) {
    console.error("Popup initialization failed:", error);
    showMessage("Something went wrong. Try again.");
  }
});
