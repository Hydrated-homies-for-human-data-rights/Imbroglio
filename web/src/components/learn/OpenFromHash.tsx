"use client"

import { useEffect } from "react"

// The finding topics on /learn are closed <details>. Reports and the
// extension link to /learn#<check_id>, so open the one the address names,
// on arrival and whenever the hash changes, and bring it into view.
//
// This sits outside the topics' Suspense boundary: the topics stream in
// after the page, and in production React may never hydrate that boundary
// (it has nothing interactive besides native <details>), so a component
// inside it never runs. Here it waits for the topic to arrive instead.
export default function OpenFromHash() {
  useEffect(() => {
    let observer: MutationObserver | undefined
    let giveUp: ReturnType<typeof setTimeout> | undefined
    const stop = () => {
      observer?.disconnect()
      clearTimeout(giveUp)
    }
    const tryOpen = (id: string) => {
      const el = document.getElementById(id)
      if (!(el instanceof HTMLDetailsElement)) return false
      el.open = true
      el.scrollIntoView({ block: "start" })
      return true
    }
    const open = () => {
      stop()
      const id = decodeURIComponent(window.location.hash.slice(1))
      if (!id || tryOpen(id)) return
      // not streamed in yet: watch for it, for up to 10 seconds
      observer = new MutationObserver(() => {
        if (tryOpen(id)) stop()
      })
      observer.observe(document.body, { childList: true, subtree: true })
      giveUp = setTimeout(stop, 10_000)
    }
    open()
    window.addEventListener("hashchange", open)
    return () => {
      stop()
      window.removeEventListener("hashchange", open)
    }
  }, [])
  return null
}
