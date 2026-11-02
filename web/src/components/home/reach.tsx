"use client"

import { useEffect, useRef, useState, type ReactNode, type Ref } from "react"

// Where the thread's tip is, in document coordinates. Thread.tsx publishes it
// on every scroll; each <Reach> compares its own position and flips its
// data-reached attribute. React owns that attribute, so server and client
// HTML agree and nothing is stamped onto elements before they hydrate.

let targetDocY = Number.NEGATIVE_INFINITY
const listeners = new Set<() => void>()

export const threadStore = {
  get: () => targetDocY,
  set(y: number) {
    if (y === targetDocY) return
    targetDocY = y
    listeners.forEach((l) => l())
  },
  subscribe(l: () => void) {
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  },
}

type Props = {
  as?: "div" | "li"
  className?: string
  children: ReactNode
}

export function Reach({ as = "div", className, children }: Props) {
  const ref = useRef<HTMLElement>(null)
  const [reached, setReached] = useState(false)
  useEffect(() => {
    const check = () => {
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const cy = r.top + window.scrollY + Math.min(r.height / 2, 40)
      setReached(cy <= threadStore.get())
    }
    check()
    return threadStore.subscribe(check)
  }, [])
  const attrs = { className, "data-reached": reached ? "true" : "false" }
  if (as === "li") {
    return (
      <li ref={ref as Ref<HTMLLIElement>} {...attrs}>
        {children}
      </li>
    )
  }
  return (
    <div ref={ref as Ref<HTMLDivElement>} {...attrs}>
      {children}
    </div>
  )
}
