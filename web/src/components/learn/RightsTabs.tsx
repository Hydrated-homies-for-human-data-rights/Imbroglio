"use client"

import { useId, useState } from "react"

// Rights by region on /learn, one tab per region. Every panel is rendered
// on the server; this only picks which one shows. Arrow keys move between
// tabs, as the ARIA tabs pattern expects.
export default function RightsTabs({ tabs }: { tabs: { label: string; panel: React.ReactNode }[] }) {
  const [current, setCurrent] = useState(0)
  const base = useId()

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = (current + step + tabs.length) % tabs.length
    setCurrent(next)
    document.getElementById(`${base}-tab-${next}`)?.focus()
  }

  return (
    <div className="rights-tabs">
      <div role="tablist" aria-label="Where you live" className="tablist" onKeyDown={onKey}>
        {tabs.map((t, i) => (
          <button
            key={t.label}
            id={`${base}-tab-${i}`}
            type="button"
            role="tab"
            aria-selected={i === current}
            aria-controls={`${base}-panel-${i}`}
            tabIndex={i === current ? 0 : -1}
            onClick={() => setCurrent(i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t, i) => (
        <div
          key={t.label}
          id={`${base}-panel-${i}`}
          role="tabpanel"
          aria-labelledby={`${base}-tab-${i}`}
          hidden={i !== current}
          className="tabpanel"
        >
          {t.panel}
        </div>
      ))}
    </div>
  )
}
