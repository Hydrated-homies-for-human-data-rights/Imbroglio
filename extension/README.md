# Browser extension

Shows the Imbroglio rating for the site in the current tab, following the UX
team's Figma (imbroglio browser extension): the toolbar icon carries the
site's worst level as a badge; the popup opens on an overview (the overall
rating and its score out of 100, in plain words, counts per level, the three
biggest flags, and a Share button that copies the report's link), with a
category breakdown behind it and a "what you can do" screen with one action
per flagged category. An action gets a button only when the lookup carries
the site's own page for it (the API's link harvest); otherwise it is text
with a "how" link to imbroglio.io/learn. Manifest V3; works in Chrome, Edge,
Opera and other Chromium browsers.

It is a thin client over the public read API. Nothing is analyzed in the
browser, there is no account, and the site's name never leaves the browser:
`background.js` hashes the domain with sha256 and sends only the first three
characters of the hash to `imbroglio.io/api/v1/lookup/<prefix>`, then picks
the site out of the matches by its full hash. Three hex characters make 4,096
buckets, so many sites share each one and a single prefix doesn't say which
one you're on (five, before 1.0, nearly did). One site, one prefix, with one
exception: a subdomain (mail.example.com) is looked up first as itself, since
some subdomains are rated as sites of their own, and only if it has no rating
does a second prefix ask about its main domain (example.com). Two prefixes
narrow it down more than one, which is why it stops at two (1.0 sent up to
three). The main domain comes from a short built-in list of two-part endings
(co.uk, com.au) and hosting platforms (github.io, vercel.app), not the full
public suffix list. Lookups only read cached results. A site we haven't
analyzed gets a link to request it on the website, where the request limits
apply; localhost, addresses and names on a private network get neither a
lookup nor that link.

## Files

- `manifest.json`: permissions (`tabs` to know which site each tab is on, so
  the badge can be drawn as you browse and the popup knows its site;
  `notifications` for the two one-time alerts, "warn me on Extensive sites"
  and "tell me when a site's policy changes"; `storage` for the two switches,
  the per-site records behind the alerts, and the local API override), and
  `imbroglio.io` as the only host. The per-site records are a date under an
  HMAC of the site's name with a secret random to the install, never the name
  or a plain hash of it. The badge lookups are the same hash-prefix lookups as
  the popup's, cached ten minutes per rated site (a minute for unrated sites
  and failed lookups) in session storage, which is memory only and cleared
  when the browser closes. At most two per page (the site, then its main
  domain if the site has no rating), none for IP addresses, names without a
  dot or private endings like .local, an 8 second timeout on each, and none
  at all until a Retry-After from the API has passed.
- `background.js`: the lookup and the badge. The icon is drawn in a canvas
  (the logo, plus the worst level's shape in the corner; dimmed with no
  badge for a site we haven't rated), so no badge icons are shipped as files.
- `popup.html`, `popup.css`, `popup.js`: the three screens. Tier colors and
  rating marks are the website's (`web/src/components/design.tsx`). Open
  `popup.html?mock=ready` (or `unknown`, `not_analyzed`, `not_public`, `error`) in a plain
  browser tab to see each state with sample data, no extension needed.
- `icons/`: the logo at the sizes Chrome asks for (the store listing and the
  extensions page; the toolbar icon is drawn).

## Loading it unpacked

1. Open `chrome://extensions/` (Opera: `opera://extensions`).
   ![Chrome Extensions](images/chrome-extensions.png)
2. Turn on **Developer mode** (top right).
   ![](images/developer-mode.png)
3. Click **Load unpacked** and pick this `extension` folder.
   ![loaded extension](images/loaded-extension.png)
4. Visit a rated site (tiktok.com, nytimes.com) and click the Imbroglio icon.

After pulling changes, click the reload arrow on the extension's card.

## Local development

By default the extension talks to imbroglio.io, the only host it has
permission for. To point it at a local API, add `"http://localhost:8765/*"`
to `host_permissions` in `manifest.json` (don't commit it: the store build
must not ask for localhost), reload the extension, open the service worker
console from the extension's card and run:

```js
chrome.storage.local.set({ apiBase: "http://localhost:8765" })
```

and `chrome.storage.local.remove("apiBase")` to go back. Opera blocks
extension requests to localhost, so test locally in Chrome or Edge.

## Releasing to the Chrome Web Store

1. Bump `version` in `manifest.json`.
2. Build the upload: `python extension/store/package.py` writes
   `extension/store/imbroglio-<version>.zip` with only the files the
   extension runs on (no README, doc images or store assets).
3. Upload it in the developer dashboard. The listing text, permission
   justifications and privacy answers are in `store/listing.md`; the images
   are made by `store/make_assets.py`. The privacy policy is
   https://imbroglio.io/privacy.
