"use client"

import { useEffect, useRef } from "react"
import { FRAGMENTS } from "./data"

// The tangle on the opening screen, drawn on a canvas so it can move.
//
// Sixteen points drift slowly around their home positions; a smooth curve runs
// through them and ends, always, at the middle of the box's right edge. That
// end is where the page's thread (Thread.tsx) starts, so the thread visibly
// leaves the knot. As the reader scrolls the knot is pulled out through that
// exit: the points nearest the exit straighten onto its line first and slide
// out of the box, the rest of the tangle is dragged after them and unwinds in
// turn, and only near the end does the line fade. Fragments of the real
// policy fade in and out over the tangle (CSS). With reduced motion the knot
// is drawn once and holds still.

type P = { x: number; y: number; ax: number; ay: number; sx: number; sy: number; px: number; py: number }

// home positions as fractions of the box. The order doubles back on itself
// so the curve loops and crosses like a dropped thread, not a zig-zag.
const HOMES: [number, number][] = [
  [0.08, 0.55],
  [0.2, 0.22],
  [0.4, 0.66],
  [0.3, 0.88],
  [0.16, 0.62],
  [0.34, 0.34],
  [0.56, 0.26],
  [0.64, 0.68],
  [0.48, 0.82],
  [0.42, 0.5],
  [0.6, 0.42],
  [0.8, 0.6],
  [0.72, 0.86],
  [0.88, 0.5],
  [0.78, 0.2],
  [0.94, 0.36],
]

const PLACES = [
  { left: "16%", top: "36%", animationDelay: "0s" },
  { left: "50%", top: "12%", animationDelay: "-3.5s" },
  { left: "30%", top: "78%", animationDelay: "-6.5s" },
  { left: "64%", top: "58%", animationDelay: "-9s" },
]

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const smooth = (v: number) => v * v * (3 - 2 * v)

// `still`: the knot drifts but is never pulled out by scrolling (the about
// page, where the thread leaves it on its own).
export default function Knot({ still = false }: { still?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const box = ref.current
    const canvas = box?.querySelector("canvas")
    const ctx = canvas?.getContext("2d")
    if (!box || !canvas || !ctx) return
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    const pts: P[] = HOMES.map(([x, y], i) => ({
      x,
      y,
      ax: 0.03 + (i % 3) * 0.012,
      ay: 0.05 + (i % 4) * 0.014,
      sx: 0.12 + (i % 5) * 0.035,
      sy: 0.1 + (i % 3) * 0.04,
      px: i * 1.7,
      py: i * 0.9,
    }))
    const n = pts.length

    let w = 0
    let h = 0
    let raf = 0
    let visible = true
    const t0 = performance.now()

    const resize = () => {
      const r = box.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      w = r.width
      h = r.height
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const draw = (now: number) => {
      const t = reduced ? 0 : (now - t0) / 1000
      // 0 before scrolling, 1 once the reader has scrolled 80% of a screen
      const pulled = reduced || still ? 0 : clamp01(window.scrollY / (window.innerHeight * 0.8))
      box.style.setProperty("--pulled", pulled.toFixed(3))

      const exit = { x: w, y: h / 2 }
      const gap = w * 0.055 // spacing of the points once they lie on the exit line
      const slide = pulled * pulled * w * 1.1 // how far the straightened run has left through the exit
      const drag = pulled * w * 0.12 // the rest of the tangle is dragged after it
      const xy = pts.map((p, i) => {
        const x = (p.x + Math.sin(t * p.sx + p.px) * p.ax) * w + drag
        const y = (p.y + Math.cos(t * p.sy + p.py) * p.ay) * h
        // the point nearest the exit straightens first, the loose end last
        const order = (n - 1 - i) / (n - 1)
        const e = smooth(clamp01((pulled - order * 0.5) / 0.5))
        const tx = Math.min(exit.x, exit.x - (n - i) * gap + slide)
        return { x: x + (tx - x) * e, y: y + (exit.y - y) * e }
      })
      xy.push(exit)

      ctx.clearRect(0, 0, w, h)
      ctx.lineCap = "round"
      ctx.lineJoin = "round"
      ctx.strokeStyle = "#f79ac0"
      ctx.lineWidth = 2.5
      ctx.globalAlpha = 1 - smooth(clamp01((pulled - 0.55) / 0.45)) * 0.95
      ctx.shadowColor = "rgba(247, 154, 192, 0.55)"
      ctx.shadowBlur = 8
      ctx.beginPath()
      ctx.moveTo(xy[0].x, xy[0].y)
      // Catmull-Rom through the points, as cubic Béziers
      for (let i = 0; i < xy.length - 1; i++) {
        const p0 = xy[i - 1] ?? xy[i]
        const p1 = xy[i]
        const p2 = xy[i + 1]
        const p3 = xy[i + 2] ?? p2
        ctx.bezierCurveTo(
          p1.x + (p2.x - p0.x) / 6,
          p1.y + (p2.y - p0.y) / 6,
          p2.x - (p3.x - p1.x) / 6,
          p2.y - (p3.y - p1.y) / 6,
          p2.x,
          p2.y,
        )
      }
      ctx.stroke()
      // the loose end
      ctx.shadowBlur = 0
      ctx.fillStyle = "#c0392b"
      ctx.beginPath()
      ctx.arc(xy[0].x, xy[0].y, 4.5, 0, Math.PI * 2)
      ctx.fill()

      if (!reduced && visible) raf = requestAnimationFrame(draw)
    }

    resize()
    draw(performance.now())
    const ro = new ResizeObserver(() => {
      resize()
      if (reduced) draw(performance.now())
    })
    ro.observe(box)
    const io = new IntersectionObserver(([e]) => {
      const was = visible
      visible = e.isIntersecting
      if (visible && !was && !reduced) raf = requestAnimationFrame(draw)
    })
    io.observe(box)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
    }
  }, [still])

  return (
    <div ref={ref} className="knot" data-thread="knot" aria-hidden="true">
      <canvas />
      <div className="knot-fragments">
        {FRAGMENTS.map((f, i) => (
          <span key={f.line} className="knot-fragment serif" style={PLACES[i]}>
            {f.text}
            <small className="mono">line {f.line}</small>
          </span>
        ))}
      </div>
    </div>
  )
}
