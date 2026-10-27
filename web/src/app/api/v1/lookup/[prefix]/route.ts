import type { NextRequest } from "next/server"
import { ApiError, lookup } from "@/lib/api"

// Read-only lookup for the browser extension. It forwards a sha256 hash
// prefix to the API and adds the API credentials here on the server, so the
// extension carries no secret. Only the prefix reaches us, never the site
// name, and this route can't start an analysis: new sites are requested on
// the website, where the request limits apply.
//
// Responses are cached at the edge for a few minutes, so repeated lookups for
// the same prefix rarely reach the API.

const PREFIX = /^[0-9a-f]{4,8}$/
const CACHE = "public, s-maxage=300, stale-while-revalidate=600"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ prefix: string }> }) {
  const { prefix } = await params
  if (!PREFIX.test(prefix)) {
    return Response.json({ error: "prefix must be 4 to 8 lowercase hex characters" }, { status: 400 })
  }
  try {
    return Response.json(await lookup(prefix), { headers: { "Cache-Control": CACHE } })
  } catch (e) {
    const status = e instanceof ApiError && e.status < 500 ? e.status : 502
    return Response.json({ error: "lookup failed" }, { status })
  }
}
