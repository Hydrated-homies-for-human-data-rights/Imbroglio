import type { NextRequest } from "next/server"
import { ApiError, lookup } from "@/lib/api"

// Read-only lookup for the browser extension. It forwards a sha256 hash
// prefix to the API and adds the API credentials here on the server, so the
// extension carries no secret. Only the prefix reaches us, never the site
// name, and this route can't start an analysis: new sites are requested on
// the website, where the request limits apply.
//
// Abuse limits: only the exact prefix length the extension sends is
// accepted, so there are few enough distinct URLs for the edge cache to
// absorb repeat traffic, and the visitor's address is passed on so the API's
// per-visitor lookup limit applies.

const PREFIX = /^[0-9a-f]{5}$/ // extension/background.js PREFIX_LENGTH
const CACHE = "public, s-maxage=300, stale-while-revalidate=600"

export async function GET(req: NextRequest, { params }: { params: Promise<{ prefix: string }> }) {
  const { prefix } = await params
  if (!PREFIX.test(prefix)) {
    return Response.json({ error: "prefix must be 5 lowercase hex characters" }, { status: 400 })
  }
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? req.headers.get("x-real-ip")
  try {
    return Response.json(await lookup(prefix, ip ?? null), { headers: { "Cache-Control": CACHE } })
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      return Response.json({ error: "Too many lookups. Try again later." },
                           { status: 429, headers: { "Retry-After": "600" } })
    }
    const status = e instanceof ApiError && e.status < 500 ? e.status : 502
    return Response.json({ error: "lookup failed" }, { status })
  }
}
