"use client"

import { useEffect } from "react"

// The finding topics on /learn are closed <details>. Reports and the
// extension link to /learn#<check_id>, so open the one the address names,
// on arrival and whenever the hash changes, and bring it into view.
export default function OpenFromHash() {
  useEffect(() => {
    const open = () => {
      const id = decodeURIComponent(window.location.hash.slice(1))
      if (!id) return
      const el = document.getElementById(id)
      if (el instanceof HTMLDetailsElement) {
        el.open = true
        el.scrollIntoView({ block: "start" })
      }
    }
    open()
    window.addEventListener("hashchange", open)
    return () => window.removeEventListener("hashchange", open)
  }, [])
  return null
}
