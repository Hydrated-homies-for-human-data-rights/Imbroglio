import { BottomBar, Masthead } from "./chrome"
import "./home.css"
import "./pages.css"

// Frame for the editorial pages: the front page's tokens and pink bars
// around an article. `current` marks the masthead link for this page.
export default function Page({
  current,
  eyebrow,
  title,
  lede,
  children,
}: {
  current: string
  eyebrow: string
  title: string
  lede?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="home page">
      <Masthead current={current} />
      <main className="page-main">
        <div className="page-head">
          <div className="eyebrow mono">{eyebrow}</div>
          <h1>{title}</h1>
          {lede && <p className="lede">{lede}</p>}
        </div>
        {children}
      </main>
      <BottomBar />
    </div>
  )
}

export function Chapter({
  id,
  eyebrow,
  title,
  wide = false,
  children,
}: {
  id?: string
  eyebrow?: string
  title: string
  wide?: boolean
  children: React.ReactNode
}) {
  return (
    <section className="chapter" id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <h2 id={id ? `${id}-h` : undefined}>
        {eyebrow && <span className="eyebrow mono">{eyebrow}</span>}
        {title}
      </h2>
      <div className={`chapter-body${wide ? " wide" : ""}`}>{children}</div>
    </section>
  )
}
