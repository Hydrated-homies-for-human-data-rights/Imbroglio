"use client"

import { useId, useMemo, useState } from "react"
import { Verdict } from "@/components/home/chrome"
import type { RubricInfo } from "@/lib/api"
import { signed } from "@/lib/format"
import { rateAnswers, statusIndex, type Answers } from "@/lib/tryRules"

// "Try the rules": every question with every allowed answer. Pick what a
// policy says and the panel shows the rating and score the scorer would give,
// and which rule decided it. The rules themselves are in lib/tryRules.ts.

export type Preset = { label: string; answers: Answers }

// where each rating sits on the 0 to 100 track, as fractions of it
const TRACK: { tier: string; from: number; to: number }[] = [
  { tier: "SEVERE", from: 0, to: 40 },
  { tier: "EXTENSIVE", from: 40, to: 60 },
  { tier: "MODERATE", from: 60, to: 90 },
  { tier: "LIMITED", from: 90, to: 101 },
]

export default function TryRules({ rubric, presets, start = 0 }: { rubric: RubricInfo; presets: Preset[]; start?: number }) {
  const [answers, setAnswers] = useState<Answers>(presets[start]?.answers ?? {})
  const out = rateAnswers(rubric, answers)
  const index = useMemo(() => statusIndex(rubric), [rubric])
  const name = useId()
  if (!out) return null

  const pick = (id: string, status: string | null) =>
    setAnswers((a) => {
      const next = { ...a }
      if (status) next[id] = status
      else delete next[id]
      return next
    })
  const count = (c: string) => out.counted.filter((x) => x.concern === c).length

  return (
    <div className="try">
      <div className="try-presets">
        <span className="eyebrow mono">Start from</span>
        {presets.map((p) => (
          <button key={p.label} type="button" onClick={() => setAnswers(p.answers)}>
            {p.label}
          </button>
        ))}
      </div>

      <div className="try-grid">
        <div className="try-questions">
          {rubric.categories.map((c) => (
            <fieldset key={c.key} id={c.key} className="try-cat">
              <legend className="eyebrow mono">{c.name}</legend>
              {c.checks.map((k) => (
                <div key={k.check_id} className="try-q" role="radiogroup" aria-labelledby={`${name}-${k.check_id}`}>
                  <p id={`${name}-${k.check_id}`}>{k.question}</p>
                  <div className="try-opts">
                    {k.statuses.map((s) => (
                      <label key={s.status}>
                        <input
                          type="radio"
                          name={`${name}-${k.check_id}`}
                          checked={answers[k.check_id] === s.status}
                          onChange={() => pick(k.check_id, s.status)}
                        />
                        <Verdict tier={s.tier} />
                        <span>{s.meaning}</span>
                      </label>
                    ))}
                    <label>
                      <input
                        type="radio"
                        name={`${name}-${k.check_id}`}
                        checked={!(k.check_id in answers)}
                        onChange={() => pick(k.check_id, null)}
                      />
                      <Verdict tier="NOT_DISCLOSED" />
                      <span>The documents don’t address this</span>
                    </label>
                  </div>
                </div>
              ))}
            </fieldset>
          ))}
        </div>

        <aside className="try-panel" aria-label="The result">
          <p className="eyebrow mono">This site would be</p>
          <div className="try-result" aria-live="polite">
            <span className="try-score">{out.score ?? "—"}</span>
            <Verdict tier={out.tier} big />
          </div>
          <div className="try-track" aria-hidden="true">
            {TRACK.map((t) => (
              <i
                key={t.tier}
                className={`t-${t.tier}${t.tier === out.tier ? " on" : ""}`}
                style={{ left: `${t.from}%`, width: `calc(${t.to - t.from}% - 2px)` }}
              />
            ))}
            {out.score != null && <b style={{ left: `${out.score}%` }} />}
          </div>
          <div className="try-track-labels mono" aria-hidden="true">
            <span>0</span>
            <span style={{ left: "40%" }}>40</span>
            <span style={{ left: "60%" }}>60</span>
            <span style={{ left: "90%" }}>90</span>
          </div>
          <dl className="try-counts">
            <div>
              <dt>Severe concerns</dt>
              <dd>{count("severe")}</dd>
            </div>
            <div>
              <dt>High</dt>
              <dd>{count("high")}</dd>
            </div>
            <div>
              <dt>Medium</dt>
              <dd>{count("medium")}</dd>
            </div>
            <div>
              <dt>Red-flag questions answered</dt>
              <dd>
                {out.highAnswered} of {out.highTotal}
              </dd>
            </div>
          </dl>
          <p className="try-why-label mono">The rule that decided it</p>
          <p className="try-why">{out.why}</p>
          {out.raw != null && out.band && (
            <div className="try-math">
              <p>
                Start at {rubric.scoring?.start}
                {out.counted.length === 0 && ", nothing taken off"}.
              </p>
              {out.counted.length > 0 && (
                <ul>
                  {out.counted.map((c) => (
                    <li key={c.check_id}>
                      <span className="mono">−{c.points}</span>
                      {index.get(c.check_id)?.get(answers[c.check_id])?.meaning}
                    </li>
                  ))}
                </ul>
              )}
              <p>
                {out.raw === out.score
                  ? `= ${out.score}, inside the ${out.band[0]} to ${out.band[1]} range.`
                  : `= ${signed(out.raw)}, kept inside the ${out.band[0]} to ${out.band[1]} range: ${out.score}.`}
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
