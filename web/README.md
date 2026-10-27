# web

The public Imbroglio website (Next.js 16, App Router, Tailwind v4), deployed on Vercel.

**Design source:** the UX team's Figma Make file "Website UX Design". Screens are built from it exactly:
the shared pieces live in `src/components/design.tsx` and `Header.tsx`. Anything the design doesn't
cover yet (home page, loading and empty states, "What can you do?", the learn page) is deliberately
plain until the UX team designs it. Don't restyle; design changes come from Figma.

| Route | Screen | Data |
| --- | --- | --- |
| `/` | home (plain for now) | none |
| `/search?q=` | search results, filters, request form | `GET /v1/search`, `POST /v1/requests` |
| `/site/[domain]` | privacy report | `GET /v1/sites/{domain}` |
| `/site/[domain]/history` | change history (timeline API not built yet) | `GET /v1/sites/{domain}` |
| `/learn` | what you can do (plain for now) | `GET /v1/learn` |

All API calls happen on the server (`src/lib/api.ts`), so the API address and password never reach
the browser.

## Run locally

```bash
npm install
IMBROGLIO_API_URL=https://<api host> IMBROGLIO_API_USER=imbroglio IMBROGLIO_API_PASSWORD=... npm run dev
```

Environment variables (set in Vercel → Project → Settings → Environment Variables):

- `IMBROGLIO_API_URL`: the read API, e.g. `https://api.imbroglio.io`
- `IMBROGLIO_API_USER`, `IMBROGLIO_API_PASSWORD`: only while the API is password-protected
- `IMBROGLIO_WEB_KEY`: the same value as the API's `WEB_CLIENT_KEY`. It lets the site pass on
  each visitor's address, so the API's rate limit counts visitors one by one. Without it, every
  visitor shares this server's limit
