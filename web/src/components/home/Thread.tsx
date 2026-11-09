"use client"

import { useEffect, useRef } from "react"
import { threadStore } from "./reach"

// The pink thread that runs the length of the front page.
//
// It is one SVG path laid over the page, routed through elements marked
// `data-thread="<id>"`, in the order `route` gives, turning at right angles
// (down first, then across). The corners are rounded and the straight runs
// sag a little, so it reads as a thread and not a wire. Its drawn length
// follows the reader: the tip sits about 70% of the way down the viewport, so
// scrolling pulls the thread. The tip's position is published through
// threadStore; every <Reach> element flips its data-reached attribute once
// the thread has passed it, and the CSS in home.css does the tinting and the
// pins. With reduced motion the whole thread is drawn and everything is
// reached.
//
// `drive="time"` draws the whole thread once, over `duration` ms from when
// the page loads, instead of following the scroll: the about page uses it,
// where the thread is a spine down the story rather than something pulled.

export type Side = "left" | "right" | "top" | "bottom" | "center"
export type Stop = { id: string; side: Side }
export type Drive = "scroll" | "time"

type Pt = { x: number; y: number }
type Sample = { l: number; x: number; y: number }

const CORNER = 34 // corner radius, px
const WAVE_LEN = 230 // px from crest to crest along a run
const WAVE_AMP = 2.2 // px the run strays from straight
const STEP = 4 // px between samples of the drawn path

const f = (v: number) => v.toFixed(1)

// radius of the rounded corner at pts[k]: never more than half a neighbour
const radius = (pts: Pt[], k: number) => {
  const a = Math.hypot(pts[k].x - pts[k - 1].x, pts[k].y - pts[k - 1].y)
  const b = Math.hypot(pts[k + 1].x - pts[k].x, pts[k + 1].y - pts[k].y)
  return Math.min(CORNER, a / 2, b / 2)
}

// cubic Béziers through every point (Catmull-Rom)
const through = (q: Pt[]): string => {
  let d = ""
  for (let j = 0; j < q.length - 1; j++) {
    const p0 = q[j - 1] ?? q[j]
    const p1 = q[j]
    const p2 = q[j + 1]
    const p3 = q[j + 2] ?? p2
    d += `C${f(p1.x + (p2.x - p0.x) / 6)} ${f(p1.y + (p2.y - p0.y) / 6)} ${f(p2.x - (p3.x - p1.x) / 6)} ${f(
      p2.y - (p3.y - p1.y) / 6,
    )} ${f(p2.x)} ${f(p2.y)}`
  }
  return d
}

// The polyline with right-angle corners, as a thread.
function threadPath(pts: Pt[]): string {
  if (pts.length < 2) return ""
  let d = `M${f(pts[0].x)} ${f(pts[0].y)}`
  let phase = 0
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]
    const b = pts[i]
    const L = Math.hypot(b.x - a.x, b.y - a.y)
    if (L < 0.5) continue
    const ux = (b.x - a.x) / L
    const uy = (b.y - a.y) / L
    const rIn = i > 1 ? radius(pts, i - 1) : 0
    const rOut = i < pts.length - 1 ? radius(pts, i) : 0
    const s = { x: a.x + ux * rIn, y: a.y + uy * rIn }
    const e = { x: b.x - ux * rOut, y: b.y - uy * rOut }
    // round the corner we are leaving
    if (rIn) d += `Q${f(a.x)} ${f(a.y)} ${f(s.x)} ${f(s.y)}`
    // the run, with a sideways sway that dies out at both ends
    const run = L - rIn - rOut
    const n = Math.floor(run / (WAVE_LEN / 2))
    const chain: Pt[] = [s]
    for (let k = 1; k <= n; k++) {
      const t = k / (n + 1)
      const along = run * t
      const off = Math.sin(phase + (along / WAVE_LEN) * Math.PI * 2) * WAVE_AMP * Math.sin(Math.PI * t)
      chain.push({ x: s.x + ux * along - uy * off, y: s.y + uy * along + ux * off })
    }
    chain.push(e)
    phase += (run / WAVE_LEN) * Math.PI * 2
    d += n ? through(chain) : `L${f(e.x)} ${f(e.y)}`
  }
  return d
}

const smooth = (v: number) => v * v * (3 - 2 * v)

export default function Thread({
  route,
  drive = "scroll",
  duration = 3200,
  delay = 400,
}: {
  route: Stop[]
  drive?: Drive
  duration?: number
  delay?: number
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const pathRef = useRef<SVGPathElement>(null)
  const tipRef = useRef<SVGCircleElement>(null)

  useEffect(() => {
    const svg = svgRef.current
    const path = pathRef.current
    const tip = tipRef.current
    if (!svg || !path || !tip) return
    const root = svg.parentElement as HTMLElement
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    let samples: Sample[] = []
    let total = 0
    let raf = 0
    const t0 = performance.now() + delay

    // Time mode: the drawn length is a share of the whole, by the clock.
    const updateByTime = (now: number) => {
      const rr = root.getBoundingClientRect()
      const p = reduced ? 1 : smooth(Math.min(1, Math.max(0, (now - t0) / duration)))
      const drawn = total * p
      let at: Pt = samples[0] ?? { x: 0, y: 0 }
      for (const s of samples) {
        if (s.l > drawn) break
        at = s
      }
      path.style.strokeDashoffset = `${Math.max(0, total - drawn)}`
      tip.style.transform = `translate(${f(at.x)}px, ${f(at.y)}px)`
      tip.style.opacity = drawn > 8 ? "1" : "0"
      threadStore.set(at.y + rr.top + window.scrollY)
      if (p < 1) raf = requestAnimationFrame(updateByTime)
    }

    const point = (s: Stop, rr: DOMRect): Pt | null => {
      const el = root.querySelector<HTMLElement>(`[data-thread="${s.id}"]`)
      if (!el) return null
      const r = el.getBoundingClientRect()
      const x = s.side === "left" ? r.left : s.side === "right" ? r.right : r.left + r.width / 2
      const y = s.side === "top" ? r.top : s.side === "bottom" ? r.bottom : r.top + r.height / 2
      return { x: x - rr.left, y: y - rr.top }
    }

    const update = () => {
      if (drive === "time") {
        cancelAnimationFrame(raf)
        raf = requestAnimationFrame(updateByTime)
        return
      }
      const rr = root.getBoundingClientRect()
      // The tip sits 70% of the way down the viewport, and reaches the very
      // end of the thread as the page reaches the end of its scroll, so the
      // close is drawn even though it can never be scrolled to 70%.
      // Before the reader scrolls, nothing is drawn past the knot: the thread
      // may only run ahead of the knot's end by 1.6 times the distance
      // scrolled, so it catches up with the 70% line within a short pull.
      const vh = window.innerHeight
      const maxScroll = Math.max(1, document.documentElement.scrollHeight - vh)
      const sf = Math.min(1, window.scrollY / maxScroll)
      const start = samples[0]?.y ?? 0
      const targetY = reduced
        ? Number.POSITIVE_INFINITY
        : Math.min(-rr.top + vh * (0.7 + 0.4 * sf * sf), start + window.scrollY * 1.6)
      // drawn up to the first point of the path below the target line. A run
      // across the page sways a little, so allow it that much.
      let drawn = 0
      let at: Pt = samples[0] ?? { x: 0, y: 0 }
      for (let i = 0; i < samples.length; i++) {
        const s = samples[i]
        if (s.y > targetY + WAVE_AMP + 0.5) {
          const prev = samples[i - 1]
          if (prev && s.y > prev.y) {
            const k = Math.min(1, Math.max(0, (targetY - prev.y) / (s.y - prev.y)))
            drawn = prev.l + (s.l - prev.l) * k
            at = { x: prev.x + (s.x - prev.x) * k, y: prev.y + (s.y - prev.y) * k }
          }
          break
        }
        drawn = s.l
        at = s
      }
      path.style.strokeDashoffset = `${Math.max(0, total - drawn)}`
      tip.style.transform = `translate(${f(at.x)}px, ${f(at.y)}px)`
      tip.style.opacity = drawn > 8 ? "1" : "0"
      threadStore.set(targetY + rr.top + window.scrollY)
    }

    const build = () => {
      const rr = root.getBoundingClientRect()
      const raw = route.map((s) => point(s, rr)).filter((p): p is Pt => p !== null)
      const pts: Pt[] = []
      for (const p of raw) {
        const prev = pts[pts.length - 1]
        if (prev && Math.abs(prev.x - p.x) > 0.5 && Math.abs(prev.y - p.y) > 0.5) pts.push({ x: prev.x, y: p.y })
        pts.push(p)
      }
      svg.setAttribute("viewBox", `0 0 ${rr.width} ${rr.height}`)
      path.setAttribute("d", threadPath(pts))
      total = path.getTotalLength()
      samples = []
      for (let l = 0; l < total; l += STEP) {
        const p = path.getPointAtLength(l)
        samples.push({ l, x: p.x, y: p.y })
      }
      const end = path.getPointAtLength(total)
      samples.push({ l: total, x: end.x, y: end.y })
      // lay the thread out without the easing the scroll uses
      path.style.transition = "none"
      tip.style.transition = "none"
      path.style.strokeDasharray = `${total}`
      update()
      void path.getBoundingClientRect()
      path.style.transition = ""
      tip.style.transition = ""
    }

    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(update)
    }
    const onResize = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(build)
    }

    build()
    const ro = new ResizeObserver(onResize)
    ro.observe(root)
    if (drive === "scroll") window.addEventListener("scroll", onScroll, { passive: true })
    window.addEventListener("resize", onResize)
    document.fonts?.ready.then(build).catch(() => {})
    return () => {
      ro.disconnect()
      window.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onResize)
      cancelAnimationFrame(raf)
    }
  }, [route, drive, duration, delay])

  return (
    <svg ref={svgRef} className="thread-svg" aria-hidden="true" preserveAspectRatio="none">
      <path ref={pathRef} className="thread-path" d="" />
      <circle ref={tipRef} className="thread-tip" r="4" />
    </svg>
  )
}
