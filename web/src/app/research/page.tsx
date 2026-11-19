import type { Metadata } from "next"
import type { ReactNode } from "react"
import { BottomBar, Masthead } from "@/components/home/chrome"
import Knot from "@/components/home/Knot"
import Thread, { type Stop } from "@/components/home/Thread"
import { Reach } from "@/components/home/reach"
import {
  AS_OF,
  BACKBONES,
  BM25,
  CHECKS,
  CONSISTENCY,
  CURVE,
  EVIDENCE,
  GOLD_AGREEMENT,
  GOLD_MODELS,
  LEAKAGE,
  LOGREG,
  NEARDUP_REVIEW,
  OPP115,
  OPP115_SETUP,
  PEOPLE,
  RANDOM,
  ROBERTA,
  ROBERTA_VS_LOGREG,
  SPLITS,
  STATUS,
  SVM,
  SWEEP,
  TEST,
  TRUNCATION,
  WEEK,
  fixed,
  type Fig,
  type Model,
  type Person,
  type Row4,
} from "@/components/home/research"
import "@/components/home/home.css"
import "@/components/home/research.css"

export const metadata: Metadata = {
  title: "The research · Imbroglio",
  description:
    "The data science behind Imbroglio: how steady Claude’s answers are, whether small models can learn to find the same evidence, and whether Claude agrees with people.",
}

// The research page: each team member's data science portion, with every
// finished result and a pending slot for each one still to come. The figures
// live in components/home/research.ts; fill them in there.
//
// The thread is pulled by the scroll, as on the front page. It leaves the
// knot on the right and crosses the page at the top of every band, so each
// part has its own gutter: it runs down the left of one part and the right of
// the next, and each question's pin lights as the tip passes.
const ROUTE: Stop[] = [
  { id: "knot", side: "right" },
  { id: "l-portions", side: "right" },
  { id: "l-portions", side: "left" },
  { id: "l-status", side: "left" },
  { id: "l-status", side: "right" },
  { id: "l-data", side: "right" },
  { id: "l-data", side: "left" },
  { id: "l-sam", side: "left" },
  { id: "l-sam", side: "right" },
  { id: "l-gage", side: "right" },
  { id: "l-gage", side: "left" },
  { id: "l-alex", side: "left" },
  { id: "l-alex", side: "right" },
  { id: "l-together", side: "right" },
  { id: "l-together", side: "left" },
  { id: "l-limits", side: "left" },
  { id: "l-limits", side: "right" },
  { id: "close-r", side: "center" },
  { id: "close-l", side: "center" },
]

const person = (key: Person["key"]) => PEOPLE.find((p) => p.key === key)!

// ---- small pieces ----

function Line({ id }: { id: string }) {
  return <div className="r-line" data-thread={id} aria-hidden="true" />
}

function Wait({ children = "pending" }: { children?: string }) {
  return <span className="r-wait mono">{children}</span>
}

function Num({ v, sub }: { v: string | null; sub?: ReactNode }) {
  if (v === null)
    return (
      <td className="n wait">
        <span>pending</span>
      </td>
    )
  return (
    <td className="n">
      {v}
      {sub && <small>{sub}</small>}
    </td>
  )
}

const f3 = (v: Fig) => fixed(v, 3)
const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(3)}`

function Table({ head, children, caption }: { head: string[]; children: ReactNode; caption?: string }) {
  return (
    <div className="r-box">
      <table>
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

const FOUR = ["Right first", "Top five", "Mean reciprocal rank", "Detection"]

function ModelRow({ m, mark }: { m: Model; mark?: Partial<Record<"r1" | "r5" | "mrr" | "auroc", boolean>> }) {
  const cell = (k: "r1" | "r5" | "mrr" | "auroc") => {
    const v = m[k].toFixed(3)
    const sub = m.ci ? m.ci[k] : m.sd ? `± ${m.sd[k].toFixed(3)}` : undefined
    return (
      <td className="n" key={k}>
        {mark?.[k] ? <mark>{v}</mark> : v}
        {sub && <small>{sub}</small>}
      </td>
    )
  }
  return (
    <tr className={m.floor ? "floor" : undefined}>
      <th scope="row">
        {m.name}
        {(m.note || (m.by && !m.floor)) && <small>{[m.by, m.note].filter(Boolean).join(" · ")}</small>}
        {m.floor && <small>floor</small>}
      </th>
      {cell("r1")}
      {cell("r5")}
      {cell("mrr")}
      {cell("auroc")}
    </tr>
  )
}

function Row4Table({ first, rows }: { first: string; rows: Row4[] }) {
  return (
    <Table head={[first, ...FOUR]}>
      {rows.map((r) => (
        <tr key={r.label} className={r.chosen ? "chosen" : undefined}>
          <th scope="row">
            {r.label}
            {r.chosen && <small>chosen</small>}
          </th>
          <td className="n">{r.r1}</td>
          <td className="n">{r.r5}</td>
          <td className="n">{r.mrr}</td>
          <td className="n">{r.auroc}</td>
        </tr>
      ))}
    </Table>
  )
}

function Q({
  id,
  n,
  eyebrow,
  ask,
  who,
  answer,
  aside,
  children,
}: {
  id: string
  n: number
  eyebrow: string
  ask: string
  who: string
  answer: ReactNode
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <article className="r-q" id={id} aria-labelledby={`${id}-h`}>
      <Reach className="r-qh">
        <div className="eyebrow mono">
          Question {n} · {eyebrow}
        </div>
        <h3 id={`${id}-h`} className="r-ask serif">
          {ask}
        </h3>
        <div className="r-who mono">{who}</div>
        {answer}
      </Reach>
      <div className="r-qb">
        <div className="r-txt">{children}</div>
        {aside && <aside className="r-side serif">{aside}</aside>}
      </div>
    </article>
  )
}

function Answer({ figure, soft = false, children }: { figure: string; soft?: boolean; children?: ReactNode }) {
  return (
    <div className="r-ans">
      <strong className={soft ? "soft serif" : undefined}>{figure}</strong>
      {children && <span>{children}</span>}
    </div>
  )
}

function Note({ k, children }: { k?: string; children: ReactNode }) {
  return (
    <p>
      {k && <span className="k mono">{k}</span>}
      {children}
    </p>
  )
}

function PartHead({ id, n, p }: { id: string; n: string; p: Person }) {
  return (
    <Reach className="r-parthead">
      <div className="eyebrow mono">
        Part {n} · {p.name}
      </div>
      <h2 id={`${id}-h`}>{p.portion}</h2>
      <p className="lede">{p.summary}</p>
      <h3 className="r-methods-h mono">What this part shows</h3>
      <ul className="r-methods">
        {p.methods.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </Reach>
  )
}

// ---- charts ----

function Ladder({ rows, label }: { rows: (Model & { mine?: boolean })[]; label: string }) {
  return (
    <div className="r-plot" role="img" aria-label={label}>
      {rows.map((m) => (
        <div key={m.name} className={`r-prow${m.floor ? " floor" : ""}${m.mine ? " mine" : ""}`}>
          <div>
            {m.name}
            <small>{m.floor ? "floor" : m.by}</small>
          </div>
          <div className="r-track">
            <b style={{ width: `${m.mrr * 100}%` }} />
            <i style={{ left: `${m.mrr * 100}%` }} />
          </div>
          <div className="v mono">{m.mrr.toFixed(3)}</div>
        </div>
      ))}
      <div className="r-axis mono" aria-hidden="true">
        <span />
        <div>
          <span>0</span>
          <span>0.25</span>
          <span>0.5</span>
          <span>0.75</span>
          <span>1</span>
        </div>
        <span />
      </div>
    </div>
  )
}

// One dot per question at its share of documents answered the same in all
// three runs, on a 70% to 100% scale; equal values stack.
function ConsistencyStrip() {
  const seen = new Map<number, number>()
  const dots = CHECKS.map((c) => {
    const k = seen.get(c.same) ?? 0
    seen.set(c.same, k + 1)
    return { left: ((c.same - 70) / 30) * 100, stack: k, low: c.same === Math.min(...CHECKS.map((x) => x.same)), c }
  })
  return (
    <div
      className="r-strip"
      role="img"
      aria-label="Share of documents with the same answer in all three runs, per question, from 72% for access and export to 100% for three questions. The target was 90%."
    >
      <span className="tg" style={{ left: "66.7%" }} />
      <span className="t mono" style={{ left: "66.7%", top: -36 }}>
        target 90%
      </span>
      {dots.map(({ left, stack, low, c }) => (
        <i key={c.label} className={low ? "lo" : undefined} style={{ left: `${left}%`, top: -7 - stack * 14 }} />
      ))}
      <span className="t start mono" style={{ left: 0 }}>
        70%
      </span>
      <span className="t start lo-label mono" style={{ left: 0, top: 34 }}>
        access and export, 72%
      </span>
      <span className="t end mono" style={{ left: "100%" }}>
        100%
      </span>
    </div>
  )
}

function Bars({ rows, label, max }: { rows: { name: string; v: number; text: string; tone?: "hi" | "lo" }[]; label: string; max: number }) {
  return (
    <div className="r-bars" role="img" aria-label={label}>
      {rows.map((r) => (
        <div key={r.name} className={`r-bar${r.tone ? ` ${r.tone}` : ""}`}>
          <span>{r.name}</span>
          <div className="tr">
            <b style={{ width: `${(r.v / max) * 100}%` }} />
          </div>
          <span className="v mono">{r.text}</span>
        </div>
      ))}
    </div>
  )
}

// ---- the page ----

export default function ResearchPage() {
  const sam = person("sam")
  const gage = person("gage")
  const alex = person("alex")
  const lowest = Math.min(...CHECKS.map((c) => c.same))

  return (
    <div className="home research">
      <Thread route={ROUTE} />
      <Masthead current="/research" />

      <section className="band r-hero" aria-labelledby="research-h1">
        <div>
          <div className="eyebrow mono">The research · data science</div>
          <h1 id="research-h1">
            The questions we asked of <em className="serif">our own</em> ratings.
          </h1>
          <p className="lede">
            Imbroglio’s ratings come from Claude reading each privacy policy and terms of service, answering 14
            questions, and quoting the sentences each answer rests on. Our code checks every quote word for word before
            it is shown.
          </p>
          <p className="lede">
            Three of us are also data science majors, and we used the ratings as a research dataset. Each of us took a
            portion: how steady and how trustworthy Claude’s answers are, whether small models can learn to find the
            same evidence, and how a neural network does on a public benchmark labeled by people.
          </p>
        </div>
        <Knot fragments={false} />
      </section>

      <section className="band r-read" aria-label="How to read this page">
        <div>
          <div className="eyebrow mono">What the figures are</div>
          <p>
            Unless a table says otherwise, every figure is measured on our development split: 149 documents from 84
            sites that no model trained on.
          </p>
        </div>
        <div>
          <div className="eyebrow mono">What is still coming</div>
          <p>
            Anything marked <Wait /> has not been measured yet. Nothing here is estimated or filled in ahead of time;
            each slot fills in when its work is done.
          </p>
        </div>
        <div>
          <div className="eyebrow mono">How sure we are</div>
          <p>
            Intervals are 95%, from resampling whole groups of related sites 1,000 times. Differences come from paired
            resampling, with a two-sided p value.
          </p>
        </div>
      </section>

      <section className="band r-portions pin-l" aria-labelledby="portions-h">
        <Line id="l-portions" />
        <div className="eyebrow mono">Who did what</div>
        <h2 id="portions-h">Three portions, one dataset</h2>
        <p className="lede">
          Each portion stands on its own: its own questions, methods and results. They share one dataset and one way of
          scoring, so their results can be compared.
        </p>
        <ul className="r-people">
          {[
            { p: sam, href: "#part-sam", part: "Part one" },
            { p: gage, href: "#part-gage", part: "Part two" },
            { p: alex, href: "#part-alex", part: "Part three" },
          ].map(({ p, href, part }) => (
            <Reach as="li" key={p.key} className="r-pin">
              <span className="r-name serif">{p.name}</span>
              <span>
                <b>{p.portion}.</b> {p.summary}
                <a className="r-to mono" href={href}>
                  {part}: {p.questions.toLowerCase()} →
                </a>
              </span>
            </Reach>
          ))}
        </ul>
      </section>

      <section className="band r-status pin-r" aria-labelledby="status-h">
        <Line id="l-status" />
        <div className="eyebrow mono">
          Where it stands · {AS_OF}, {WEEK}
        </div>
        <h2 id="status-h">Done, under way, and still to do</h2>
        <p className="lede">
          The weeks for unfinished work are our schedule, not results. Week 14 is for the last measurements and
          write-ups; week 15 is the final presentation.
        </p>
        <Table head={["Piece of work", "Who", "State", "Week"]}>
          {STATUS.map((s) => (
            <tr key={s.work}>
              <th scope="row">{s.work}</th>
              <td>{s.who}</td>
              <td>
                <span className={`r-chip ${s.state} mono`}>
                  {s.state === "done" ? "done" : s.state === "now" ? "under way" : "to do"}
                </span>
              </td>
              <td className="n">{s.when || "·"}</td>
            </tr>
          ))}
        </Table>
      </section>

      {/* ---- the shared dataset ---- */}
      <section className="band r-part pin-l" aria-labelledby="q-data-h">
        <Line id="l-data" />
        <Q
          id="q-data"
          n={1}
          eyebrow="The dataset"
          ask="What did the models learn from?"
          who="Gage Gunn, with near-duplicate grouping by Sam Holton"
          answer={
            <Answer figure="130,672">
              paragraphs from 973 privacy policies and terms of service on 559 sites, each marked against our 14
              questions.
            </Answer>
          }
          aside={
            <>
              <Note k="Quotes">
                6,617 of Claude’s quotes were verified and placed in a paragraph. Another 1,739 were found word for word
                but rejected for lacking one of the question’s evidence words; they are kept apart to test that check.
              </Note>
              <Note k="Two known biases">
                Every label is Claude’s, not a person’s. And positives lean toward paragraphs with an evidence word,
                because that check decides which quotes count.
              </Note>
            </>
          }
        >
          <p>
            We split every document Imbroglio has analyzed into paragraphs. For each paragraph and question there are
            three possible labels. It is <b>positive</b> if Claude quoted it for that question and the quote was
            verified. It is <b>negative</b> if the document never addresses the question at all, because then none of
            its paragraphs can. Anything else is <b>unlabeled</b>: Claude cites at most three quotes per answer, so a
            paragraph it didn’t quote may still answer the question.
          </p>
          <p>
            Documents are split 70/15/15 into training, development and test sets by site group, so the same text never
            sits on both sides of a split (question 2).
          </p>
          <h4>The splits</h4>
          <Table head={["Split", "Documents", "Sites", "Site groups", "Paragraphs"]}>
            {SPLITS.map((s) => (
              <tr key={s.split}>
                <th scope="row">{s.split}</th>
                <td className="n">{s.docs}</td>
                <td className="n">{s.sites}</td>
                <td className="n">{s.groups}</td>
                <td className="n">{s.paragraphs.toLocaleString("en-US")}</td>
              </tr>
            ))}
          </Table>
          <h4>Positive paragraphs per question</h4>
          <p>
            Some questions are common and some are rare. Breach notification and notifying users of government requests
            have only about a dozen positive paragraphs in each evaluation split, which limits what can be said about
            them.
          </p>
          <Table head={["Question", "Training", "Development", "Test"]}>
            {CHECKS.map((c) => (
              <tr key={c.label}>
                <th scope="row">{c.label}</th>
                {c.pos.map((v, i) => (
                  <td className="n" key={i}>
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </Table>
        </Q>
      </section>

      {/* ---- part one: Sam ---- */}
      <section className="band r-part pin-r" id="part-sam" aria-labelledby="part-sam-h">
        <Line id="l-sam" />
        <PartHead id="part-sam" n="one" p={sam} />

        <Q
          id="q-leakage"
          n={2}
          eyebrow="Leakage"
          ask="Could a copied template leak into the test?"
          who="Sam Holton"
          answer={
            <Answer figure="3.9% → 1.3%">
              of test paragraphs also seen in training, before and after grouping near-duplicate policies.
            </Answer>
          }
          aside={
            <Note k="What remains">
              The 1.3% left is mostly stock sentences that unrelated sites share. Those paragraphs are flagged (141 of
              14,847 substantive test paragraphs), so results can be reported with and without them.
            </Note>
          }
        >
          <p>
            Many sites use the same policy template with the company name changed. If one copy is in training and
            another in test, every model looks better than it is. Grouping identical texts was not enough.
          </p>
          <p>
            Sam compared all 472,464 pairs of documents from different sites by the overlap of their five-word sequences
            (Jaccard similarity), and grouped sites whose documents reach a threshold. The threshold came from a leakage
            table over five random splits: the share of substantive test paragraphs that appear word for word in
            training.
          </p>
          <h4>Leakage by threshold, mean of five splits</h4>
          <Bars
            label="Leakage by grouping threshold, from 3.9% with identical texts only to 1.3% at the chosen threshold of 0.3."
            max={4}
            rows={LEAKAGE.map((l) => ({
              name: l.chosen ? `${l.threshold}, chosen` : l.threshold === "Identical texts only" ? "identical only" : l.threshold,
              v: l.mean,
              text: `${l.mean.toFixed(1)}%`,
              tone: l.chosen ? "hi" : l.threshold === "Identical texts only" ? "lo" : undefined,
            }))}
          />
          <Table head={["Threshold", "Leakage, mean", "Range over splits", "Groups of 2+ sites", "Largest group"]}>
            {LEAKAGE.map((l) => (
              <tr key={l.threshold} className={l.chosen ? "chosen" : undefined}>
                <th scope="row">
                  {l.threshold}
                  {l.chosen && <small>chosen</small>}
                </th>
                <td className="n">{l.mean.toFixed(1)}%</td>
                <td className="n">{l.range}</td>
                <td className="n">{l.groups}</td>
                <td className="n">{l.largest} sites</td>
              </tr>
            ))}
          </Table>
          <p>
            Below 0.3, leakage barely improves while groups start to chain unrelated sites together. At 0.3 there are 27
            groups covering 72 sites: one company on several domains, terms derived from a common source, and sites
            built from the same policy generator.
          </p>
          <h4>Checked by hand</h4>
          <p>
            Before the split was frozen, 34 pairs across the whole similarity range were marked as the same template,
            shared stock wording, or different. Sam marked 17 by hand, and Claude marked the other 17 following her
            calls; the review file records which is which. The threshold misses some templates: 7 of the 12 pairs below
            0.3 look like one. Lowering it to 0.2 leaves leakage where it is, though, so it stayed at 0.3 and the split
            is now frozen.
          </p>
          <Table head={["Review of 34 pairs", "Result"]}>
            {NEARDUP_REVIEW.map((r) => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                <Num v={r.value === null ? null : String(r.value)} />
              </tr>
            ))}
          </Table>
        </Q>

        <Q
          id="q-consistency"
          n={3}
          eyebrow="Consistency"
          ask="Does Claude give the same answer twice?"
          who="Sam Holton"
          answer={
            <Answer figure="88.4%">
              of answers were the same in all three runs (95% interval 85.9% to 91.0%). Our target was 90%.
            </Answer>
          }
          aside={
            <Note k="Why it matters">
              A model trained on Claude’s answers can’t be steadier than those answers. This sets a ceiling on what any
              agreement figure on this page can mean.
            </Note>
          }
        >
          <p>
            Every model here learns from Claude’s answers, so the first thing to measure was how much those answers
            move. The model doesn’t accept a temperature setting, so the variation was measured rather than assumed
            away: 50 randomly chosen privacy policies, each analyzed three times with the same rubric, 14 questions per
            run. The study cost $5.89.
          </p>
          <ConsistencyStrip />
          <p>
            Each dot is one of the 14 questions, placed by how often its answer held in all three runs. The red one, at{" "}
            {lowest}%, is the least steady.
          </p>
          <h4>Per question</h4>
          <p>
            Fleiss’ kappa treats each run as a separate rater and corrects for agreement expected by chance. It can’t be
            computed where every run gave the same answer on every document.
          </p>
          <Table head={["Question", "Same in all 3 runs", "Fleiss’ kappa"]}>
            {CHECKS.map((c) => (
              <tr key={c.label}>
                <th scope="row">{c.label}</th>
                <td className="n">{c.same}%</td>
                <td className="n">{c.kappa === null ? "n/a" : c.kappa.toFixed(2)}</td>
              </tr>
            ))}
          </Table>
          <h4>What it does to ratings</h4>
          <Table head={["Measure", "Result", "95% interval"]}>
            {CONSISTENCY.map((c) => (
              <tr key={c.label}>
                <th scope="row">{c.label}</th>
                <td className="n">{c.value}</td>
                <td className="n">{c.ci || "·"}</td>
              </tr>
            ))}
          </Table>
        </Q>

        <Q
          id="q-method"
          n={4}
          eyebrow="Method"
          ask="How do we score a model fairly?"
          who="Sam Holton, used by every model on this page"
          answer={<Answer figure="The same way, every time." soft />}
          aside={
            <Note k="What Claude’s labels can’t measure">
              Precision, recall and F1 need to know which unquoted paragraphs are truly irrelevant. Only people can say
              that, so those figures wait for the gold set in question 9.
            </Note>
          }
        >
          <p>
            Every model writes a score for each paragraph and question, and one shared module scores them all. Two tasks
            can be measured with Claude’s labels.
          </p>
          <h4>Ranking within a document</h4>
          <p>
            For a document and a question Claude answered, rank its paragraphs by the model’s score and see where the
            quoted paragraph lands. There are 843 such pairs in the development split.
          </p>
          <ul className="r-facts">
            <li>
              <b>Right paragraph first</b> (recall at 1): how often a quoted paragraph is ranked first.
            </li>
            <li>
              <b>In the top five</b> (recall at 5): how often one is in the first five.
            </li>
            <li>
              <b>Mean reciprocal rank</b>: one over the rank of the first quoted paragraph, averaged. 1.0 means always
              first; 0.5 means second on average.
            </li>
          </ul>
          <h4>Detection across documents</h4>
          <p>
            Does this document answer the question at all? A document’s score is its highest paragraph score, compared
            between documents that answer and documents that don’t, as area under the ROC curve. A random scorer gets
            about 0.60 rather than 0.50 here, because longer documents both have more paragraphs and answer more
            questions.
          </p>
          <h4>How differences are judged</h4>
          <ul className="r-facts">
            <li>Every figure averages the 14 questions with equal weight, so rare questions count as much as common ones.</li>
            <li>Intervals come from resampling whole site groups, not paragraphs, because paragraphs from one site are not independent.</li>
            <li>Two models are compared on the same resamples (a paired bootstrap), which gives the difference an interval and a p value.</li>
            <li>Transformers are trained three times with different random seeds; the spread over seeds is reported apart from the sampling interval.</li>
            <li>
              14 questions and 4 measures make 56 per-question tests, so about 3 will fall under p = 0.05 by chance. A lone
              per-question difference is not read as meaningful.
            </li>
          </ul>
        </Q>

        <Q
          id="q-classical"
          n={5}
          eyebrow="Classical models"
          ask="How far do word counts get you?"
          who="Sam Holton, with the BM25 baseline by Gage Gunn"
          answer={
            <Answer figure={LOGREG.mrr.toFixed(3)}>
              mean reciprocal rank for tuned logistic regression on TF-IDF features, against {BM25.both.mrr.toFixed(3)}{" "}
              for BM25 search.
            </Answer>
          }
          aside={
            <>
              <Note k="Hardest questions">
                Collecting from third parties, sharing for advertising and opting out of tracking are among the weakest
                for every method (per-question figures in question 6).
              </Note>
              <Note k="Tuning cost">
                14 questions × 8 values of C took 170 seconds for logistic regression and 613 for the SVM.
              </Note>
            </>
          }
        >
          <p>
            The classical models treat a paragraph as a bag of words and phrases: 145,006 TF-IDF features learned from
            the 92,839 training paragraphs. Logistic regression and a linear SVM are trained separately for each
            question, and the regularization strength C is tuned per question on development data over eight values
            from 0.01 to 30.
          </p>
          <p>
            BM25 is a search engine method with no training. It scores paragraphs by query words, with three queries
            per question (the question’s own words, its evidence words, or both) and its two parameters tuned on
            development data. Two floors show what no learning gets: random order, and ranking paragraphs that contain
            an evidence word first.
          </p>
          <h4>Mean reciprocal rank</h4>
          <Ladder
            label="Mean reciprocal rank on development data, from 0.061 for random order to 0.839 for logistic regression."
            rows={[RANDOM, EVIDENCE, BM25.question, BM25.evidence, BM25.both, { ...SVM, mine: true }, { ...LOGREG, mine: true }]}
          />
          <h4>All four measures</h4>
          <Table head={["Method", ...FOUR]}>
            <ModelRow m={RANDOM} />
            <ModelRow m={EVIDENCE} />
            <ModelRow m={BM25.both} />
            <ModelRow m={LOGREG} />
            <ModelRow m={SVM} />
          </Table>
          <h4>Where they go wrong</h4>
          <p>Sam’s error analysis of the classical models, question by question, is being written up.</p>
          <Table head={["Error analysis", "Result"]}>
            {[
              "Most common kinds of false positive",
              "Most common kinds of miss",
              "How many top-ranked “errors” actually answer the question",
              "Most informative features per question",
            ].map((l) => (
              <tr key={l}>
                <th scope="row">{l}</th>
                <Num v={null} />
              </tr>
            ))}
          </Table>
        </Q>
      </section>

      {/* ---- part two: Gage ---- */}
      <section className="band r-part pin-l" id="part-gage" aria-labelledby="part-gage-h">
        <Line id="l-gage" />
        <PartHead id="part-gage" n="two" p={gage} />

        <Q
          id="q-transformer"
          n={6}
          eyebrow="Transformers"
          ask="Can a fine-tuned transformer learn to read like Claude?"
          who="Gage Gunn"
          answer={
            <Answer figure={ROBERTA.auroc.toFixed(3)}>
              detection score, ahead of every classical model (+0.024 over logistic regression, p &lt; 0.001), while level
              with them on ranking.
            </Answer>
          }
          aside={
            <>
              <Note k="Reading the result">
                On finding the quoted paragraph, the transformer and logistic regression are level: no ranking difference
                is distinguishable from noise. On telling which documents answer a question at all, the transformer is
                clearly better.
              </Note>
              <Note k="A caution">
                The better epoch was picked on the same development data, which flatters it slightly. The held-out test
                split in question 10 settles it.
              </Note>
            </>
          }
        >
          <p>
            This is distillation: a model of 125 million parameters, RoBERTa-base, fine-tuned to reproduce Claude’s
            judgments paragraph by paragraph. It reads one paragraph and gives 14 scores at once, one per question.
          </p>
          <h4>Training setup</h4>
          <ul className="r-facts">
            <li>
              Binary cross-entropy per question, with positives up-weighted by the square root of each question’s
              imbalance; the rarest question has one positive for about every 2,000 training paragraphs.
            </li>
            <li>Unlabeled paragraphs count as negatives at a weight of 0.1 (chosen in question 7); confirmed negatives count fully.</li>
            <li>Learning rate 2 × 10⁻⁵ with warmup and linear decay, batches of 32, 2 epochs, the better epoch chosen on development data.</li>
            <li>Paragraphs read up to 512 tokens. Every setting is trained with 3 seeds on one RTX 4070 Ti Super, at about 146 paragraphs a second.</li>
          </ul>
          <h4>Against the best classical model</h4>
          <Table head={["Model", ...FOUR]}>
            <ModelRow m={BM25.both} />
            <ModelRow m={{ ...LOGREG, ci: undefined }} mark={{ r1: true, r5: true, mrr: true }} />
            <ModelRow m={ROBERTA} mark={{ auroc: true }} />
            <tr className="diff">
              <th scope="row">
                RoBERTa minus logistic regression<small>seeds averaged, paired bootstrap</small>
              </th>
              {(["r1", "r5", "mrr", "auroc"] as const).map((k) => (
                <td className="n" key={k}>
                  {signed(ROBERTA_VS_LOGREG[k].d)}
                  <small>p {ROBERTA_VS_LOGREG[k].p.startsWith("<") ? ROBERTA_VS_LOGREG[k].p : `= ${ROBERTA_VS_LOGREG[k].p}`}</small>
                </td>
              ))}
            </tr>
          </Table>
          <h4>Mean reciprocal rank per question</h4>
          <Table head={["Question", "Pairs", "BM25", "Logistic regression", "RoBERTa"]}>
            {CHECKS.map((c) => (
              <tr key={c.label}>
                <th scope="row">{c.label}</th>
                <td className="n">{c.pairs}</td>
                <td className="n">{c.mrr.bm25.toFixed(3)}</td>
                <td className="n">{c.mrr.logreg.toFixed(3)}</td>
                <td className="n">{c.mrr.roberta.toFixed(3)}</td>
              </tr>
            ))}
            <tr className="total">
              <th scope="row">All questions, equal weight</th>
              <td className="n">843</td>
              <td className="n">{BM25.both.mrr.toFixed(3)}</td>
              <td className="n">{LOGREG.mrr.toFixed(3)}</td>
              <td className="n">{ROBERTA.mrr.toFixed(3)}</td>
            </tr>
          </Table>
        </Q>

        <Q
          id="q-experiments"
          n={7}
          eyebrow="Controlled experiments"
          ask="What actually drives the transformer’s accuracy?"
          who="Gage Gunn"
          answer={
            <Answer figure="84%">of its full ranking score with a tenth of the training data, once training length is held equal.</Answer>
          }
          aside={
            <>
              <Note k="Why controls matter">
                The first learning curve said a tenth of the data reaches 44% of the full score. Holding training length
                equal moved that to 84%. Without the control, the wrong conclusion would have stood.
              </Note>
              <Note k="Runs">36 training runs in all for these four experiments.</Note>
            </>
          }
        >
          <p>Four experiments, each changing one thing, with 3 seeds per setting. Figures are means ± standard deviation over seeds.</p>

          <h4>1. How much to trust an unquoted paragraph</h4>
          <p>
            An unquoted paragraph may still answer the question, so treating it as a plain negative teaches the model
            wrong answers. The weight given to unlabeled paragraphs was varied from 0 (ignore them) to 1 (count them as
            negatives), a form of positive-unlabeled learning.
          </p>
          <Row4Table first="Unlabeled weight" rows={SWEEP} />
          <p>
            The weight trades ranking against detection. Moving from 0 to 0.1 improves ranking (+0.021 mean reciprocal
            rank, p = 0.012) at no cost to detection; going on to 1 adds nothing to ranking and costs detection (−0.013,
            p &lt; 0.001).
          </p>

          <h4>2. How much data it needs</h4>
          <p>
            A first learning curve trained every fraction for 2 epochs, which gave small fractions far fewer training
            steps. Rerun with the number of steps held equal, most of the apparent gap disappears.
          </p>
          <div
            className="r-bars"
            role="img"
            aria-label="Mean reciprocal rank by share of training data. 10%: 0.355 at 2 epochs, 0.680 with matched steps. 25%: 0.633 and 0.741. 50%: 0.746 and 0.770. 100%: 0.814."
          >
            {CURVE.map((c) => (
              <div className="r-grp" key={c.fraction}>
                <span>{c.fraction}</span>
                {c.epochs !== 2 && (
                  <div className="r-bar lo">
                    <span>2 epochs</span>
                    <div className="tr">
                      <b style={{ width: `${c.fixed * 100}%` }} />
                    </div>
                    <span className="v mono">{c.fixed.toFixed(3)}</span>
                  </div>
                )}
                <div className="r-bar hi">
                  <span>{c.epochs} epochs</span>
                  <div className="tr">
                    <b style={{ width: `${c.matched * 100}%` }} />
                  </div>
                  <span className="v mono">{c.matched.toFixed(3)}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="r-key">
            <span>
              <i className="lo" />
              fixed 2 epochs
            </span>
            <span>
              <i className="hi" />
              steps matched to the full run
            </span>
          </div>
          <p>
            Going from half the data to all of it still helps (+0.020, p = 0.008). With a tenth of the data and matched
            steps, detection is level with logistic regression (0.926 against 0.952, p = 0.42).
          </p>

          <h4>3. Does a legal-domain model help?</h4>
          <p>legal-bert was pretrained on legal text, which sounds closer to privacy policies than RoBERTa’s general web text.</p>
          <Row4Table first="Backbone" rows={BACKBONES} />
          <p>
            No difference overall (−0.004 mean reciprocal rank, p = 0.58). One of 56 per-question tests came out
            significant, about what chance alone produces.
          </p>

          <h4>4. Reading long paragraphs in full</h4>
          <p>
            At 256 tokens, 1.7% of development paragraphs are cut off, but 3.8% of quoted ones are: answers sit in long
            paragraphs more than most. In 49 of the 843 pairs, every quoted paragraph was cut.
          </p>
          <Table head={["Mean reciprocal rank", "All pairs", "49 pairs, every quote cut at 256", "The other 794"]}>
            {TRUNCATION.map((t) => (
              <tr key={t.label} className={t.chosen ? "chosen" : undefined}>
                <th scope="row">
                  {t.label}
                  {t.chosen && <small>chosen</small>}
                </th>
                <td className="n">{t.all}</td>
                <td className="n">{t.cut}</td>
                <td className="n">{t.rest}</td>
              </tr>
            ))}
          </Table>
          <p>
            Reading 512 tokens fixes most of the loss on those pairs. Overall the gain is small and within noise (+0.008,
            p = 0.25), training runs at half the speed (146 against 290 paragraphs a second), and the spread across seeds
            shrinks.
          </p>
        </Q>
      </section>

      {/* ---- part three: Alex ---- */}
      <section className="band r-part pin-r" id="part-alex" aria-labelledby="part-alex-h">
        <Line id="l-alex" />
        <PartHead id="part-alex" n="three" p={alex} />

        <Q
          id="q-opp115"
          n={8}
          eyebrow="OPP-115"
          ask="Can a neural network beat the public benchmark?"
          who="Alex Kimoni"
          answer={
            <Answer figure="0.765">
              is the bar: macro F1 of a TF-IDF and logistic regression baseline across OPP-115’s ten categories. Our
              target was 0.70.
            </Answer>
          }
          aside={
            <Note k="Calibration">
              A reliability diagram bins predictions by stated confidence and plots how often each bin is right.
              Expected calibration error is the average gap between the two.
            </Note>
          }
        >
          <p>
            OPP-115 is a public set of 115 privacy policies whose segments were labeled by law students into ten
            categories of data practice. Unlike our own dataset, its labels come from people, so it checks our methods
            against outside work. It is split by policy, 80/10/10, so no policy is on both sides.
          </p>
          <p>
            The baseline’s weakest category is data retention (F1 0.444 on development, 0.545 on test), which also has
            the fewest examples. Alex’s neural classifier is measured on the same split, along with whether its
            confidence can be trusted: a model that says it is 80% sure should be right about 80% of the time.
          </p>
          <h4>Model and training setup</h4>
          {OPP115_SETUP ? <p>{OPP115_SETUP}</p> : <Wait />}
          <h4>Results</h4>
          <Table head={["Measure", "TF-IDF baseline", "Neural classifier"]}>
            {OPP115.map((r) => (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                <Num v={r.baseline} />
                <Num v={r.neural} />
              </tr>
            ))}
          </Table>
        </Q>
      </section>

      {/* ---- part four: together ---- */}
      <section className="band r-part pin-l" id="part-together" aria-labelledby="part-together-h">
        <Line id="l-together" />
        <Reach className="r-parthead">
          <div className="eyebrow mono">Part four · Sam Holton and Gage Gunn</div>
          <h2 id="part-together-h">Checked against people, and held out</h2>
          <p className="lede">
            Everything above measures agreement with Claude. The last two questions test Claude itself, and every model
            on documents no choice was ever made on.
          </p>
        </Reach>

        <Q
          id="q-gold"
          n={9}
          eyebrow="The gold set"
          ask="Does Claude agree with people?"
          who="Labeled by all four of us; analysis by Sam Holton and Gage Gunn"
          answer={
            <Answer figure="88.9%">
              of Claude’s answers match people’s on the 12 documents labeled in full so far (kappa 0.857).
            </Answer>
          }
          aside={
            <>
              <Note k="Effort">
                The first plan put Sam and Gage at about 9 hours each. Showing each paragraph once, with a box per
                question, and dropping candidates only the evidence-word lists proposed cut that to about an hour of
                passages each, plus reading each document.
              </Note>
              <Note k="Why two depths">
                Answers are quick, and they are all that Claude against people needs, so every document gets them.
                Passage judgments take most of the time and are what scoring the models needs, so 12 documents get them.
              </Note>
            </>
          }
        >
          <p>
            We drew 30 documents at random from the held-out test split to label by hand, without seeing Claude’s
            answers. Before any real label, 4 of the full documents were dropped to keep the work bounded, which leaves
            26. All 26 get people’s answers to the 14 questions, and 12 are answered by two of us independently, so we
            can also measure how often people agree. 12 of the 26 also get passage judgments, from Sam and Gage, 8 of
            them by both.
          </p>
          <div
            className="r-docs"
            role="img"
            aria-label="26 documents: 8 labeled in full by two people, 4 in full by one, and 14 answers only."
          >
            {Array.from({ length: 26 }, (_, i) => (
              <i key={i} className={i < 8 ? "d" : i < 12 ? "f" : "a"} />
            ))}
          </div>
          <div className="r-key">
            <span>
              <i className="doc d" />
              in full, by two of us
            </span>
            <span>
              <i className="doc f" />
              in full, by one
            </span>
            <span>
              <i className="doc a" />
              answers only (4 of them by two of us)
            </span>
          </div>
          <h4>What each of us does per document</h4>
          <ol className="r-steps">
            <li>
              <b>Answer</b> (all 26). Read the whole document and answer all 14 questions with the rubric, marking the
              lines each answer rests on.
            </li>
            <li>
              <b>Judge passages</b> (12). Judge candidate paragraphs yes or no for each question they were proposed for.
              Candidates are pooled from Claude’s quotes, our own marks and each tested model’s top five, with their
              source hidden.
            </li>
            <li>
              <b>Check the pool</b> (12). Mark 10 random paragraphs that no source proposed, to estimate how many
              relevant paragraphs the pool misses.
            </li>
          </ol>
          <p>
            A two-document pilot from the development split came first, labeled by Sam and Gage, to tighten the
            guideline. Disagreements are settled together, and both raw labels are kept. What counts as a gold label,
            how each model is scored, and every model’s cut-offs were fixed and saved before any label is read, so no
            result can steer them.
          </p>
          <p>
            Sam and Gage gave the same answer on 109 of 112 questions and the same passage judgment on 98.7% of lines;
            the 22 places they differed were settled together. Claude is weakest where the rubric asks for a judgment
            of degree: opting out of tracking (60% the same, people said yes where Claude said limited), sensitive data
            and disclosure to government (70% each). It matches people on every answer about retention, selling data,
            AI training and notifying users.
          </p>
          <p>
            The evidence-word check, which throws out a Claude quote that lacks any of the question’s evidence words,
            almost never keeps a wrong one (precision 0.963). But 20 of the 22 quotes it threw out were relevant,
            including all 8 it threw out for collecting data from third parties. The check is too strict, not too loose.
          </p>
          <h4>Results</h4>
          <Table head={["Measure", "Who", "Result"]}>
            {GOLD_AGREEMENT.map((g) => (
              <tr key={g.label}>
                <th scope="row">{g.label}</th>
                <td>{g.who}</td>
                <Num v={g.value} />
              </tr>
            ))}
          </Table>
          <h4>Models against people</h4>
          <p>
            Here precision, recall and F1 become measurable. Each model’s cut-off per question is fixed before it sees the
            gold set.
          </p>
          <Table head={["Model", "Precision", "Recall", "F1", "Top five"]}>
            {GOLD_MODELS.map((m) => (
              <tr key={m.name}>
                <th scope="row">{m.name}</th>
                <Num v={f3(m.precision)} />
                <Num v={f3(m.recall)} />
                <Num v={f3(m.f1)} />
                <Num v={m.top5 === "n/a" ? "n/a" : f3(m.top5)} />
              </tr>
            ))}
          </Table>
          <Wait>Alex and Jaiden’s answers and the models’ scores, week 14</Wait>
        </Q>

        <Q
          id="q-test"
          n={10}
          eyebrow="Held-out test"
          ask="Does it hold on documents we never looked at?"
          who="Gage Gunn and Sam Holton"
          answer={<Answer figure="Scored once, at the end." soft />}
          aside={
            <Note k="Why once">
              Looking at test results and then adjusting would turn the test split into a second development split, and
              its figures would flatter us the same way.
            </Note>
          }
        >
          <p>
            Every choice on this page (unlabeled weight, backbone, length, C, the BM25 settings, the best epoch) was made
            on the development split. The 142 test documents have been held back from all of it. Each final model is
            scored on them exactly once, after every choice is fixed.
          </p>
          <Table head={["Model", ...FOUR]}>
            {TEST.map((t) => (
              <tr key={t.name}>
                <th scope="row">{t.name}</th>
                <Num v={f3(t.r1)} />
                <Num v={f3(t.r5)} />
                <Num v={f3(t.mrr)} />
                <Num v={f3(t.auroc)} />
              </tr>
            ))}
          </Table>
          <Wait>week 14, after the split is frozen</Wait>
        </Q>
      </section>

      <section className="band r-limits pin-r" aria-labelledby="limits-h">
        <Line id="l-limits" />
        <Reach className="r-limits-grid">
          <div>
            <div className="eyebrow mono">Limits</div>
            <h2 id="limits-h">What these results can’t tell you</h2>
          </div>
          <ul className="r-facts">
            <li>Until the gold set is done, every figure about our own dataset measures agreement with Claude, not correctness.</li>
            <li>
              Claude quotes at most three paragraphs per answer, so some paragraphs counted as misses may be right answers.
              The gold set’s pool check estimates how many.
            </li>
            <li>Positive paragraphs lean toward ones containing an evidence word, which favors word-based models.</li>
            <li>
              Breach notification, notifying users of government requests and AI training have few examples; their
              per-question figures have wide intervals.
            </li>
            <li>
              Documents with more than 250 substantive paragraphs, about the longest 6%, are left out of the gold set to
              keep labeling bounded.
            </li>
            <li>Development figures include choices made on that same data, so they lean optimistic. The test split corrects for it.</li>
          </ul>
        </Reach>
      </section>

      <section className="band close r-close" aria-labelledby="close-h">
        <h2 id="close-h" className="serif">
          Pull another thread.
        </h2>
        <form action="/search" className="search" role="search">
          <label className="sr-only" htmlFor="q-research">
            Search a site or service
          </label>
          <input id="q-research" name="q" placeholder="Search a site or service" autoComplete="off" />
          <button type="submit" aria-label="Search">
            ↵
          </button>
          <i data-thread="close-l" style={{ position: "absolute", left: 0, bottom: 0 }} />
          <i data-thread="close-r" style={{ position: "absolute", right: 0, bottom: 0 }} />
        </form>
        <p className="r-asof mono">
          Figures as of {AS_OF}. Policy text from our dataset is never shown on this page; it stays within the team.
        </p>
      </section>

      <BottomBar />
    </div>
  )
}
