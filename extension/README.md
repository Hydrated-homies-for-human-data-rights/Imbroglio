# Browser extension

Shows the Imbroglio rating for the site in the current tab: the overall
rating, the category that drove it, and one row per category, with a link to
the full report on imbroglio.io. Manifest V3; works in Chrome, Edge, Opera and
other Chromium browsers.

It is a thin client over the public read API. Nothing is analyzed in the
browser, there is no account, and the site's name never leaves the browser:
`background.js` hashes the domain with sha256 and sends only the first five
characters of the hash to `imbroglio.io/api/v1/lookup/<prefix>`, then picks
the site out of the matches by its full hash. Lookups only read cached
results. A site we haven't analyzed gets a link to request it on the website,
where the request limits apply.

## Files

- `manifest.json`: permissions (`activeTab` to read the current tab's address
  when the icon is clicked, `storage` for the local API override).
- `background.js`: the lookup.
- `popup.html`, `popup.css`, `popup.js`: the card. Colors and rating marks
  follow the website (`web/src/components/design.tsx`) until the UX team's
  Figma for the extension arrives.
- `icons/`: the logo at the sizes Chrome asks for.

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

By default the extension talks to imbroglio.io. To point it at a local API,
open the service worker console from the extension's card and run:

```js
chrome.storage.local.set({ apiBase: "http://localhost:8765" })
```

and `chrome.storage.local.remove("apiBase")` to go back. Opera blocks
extension requests to localhost, so test locally in Chrome or Edge.
