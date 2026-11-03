import type { NextRequest } from "next/server"
import { ApiError, getRequest } from "@/lib/api"

// Read-only status of one analysis request, polled by the request progress
// box while a site is queued or running. The API credentials are added here
// on the server. Ids are integers; anything else is refused before the API
// is asked. Never cached: the point is to see the job move.

const ID = /^[1-9][0-9]{0,11}$/

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  if (!ID.test(id)) return Response.json({ error: "not a request id" }, { status: 400 })
  try {
    return Response.json(await getRequest(Number(id)), { headers: { "Cache-Control": "no-store" } })
  } catch (e) {
    const status = e instanceof ApiError && e.status < 500 ? e.status : 502
    return Response.json({ error: status === 404 ? "request not found" : "status unavailable" }, { status })
  }
}
