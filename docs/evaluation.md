# Evaluation: what we've measured so far

This page collects every accuracy figure we have, how each one was measured, and what hasn't been
measured yet. The proposal promised published accuracy instead of asserted accuracy, and requirement
F5 asks for these figures to be public. The website's "How we score" page shows the headline numbers.

Each figure says when it was measured. Rerun them as the system changes and update this page.

## Summary

| What | Result | Target | Measured |
| --- | --- | --- | --- |
| Discovery on the 20-site feasibility sample | 19 of 20 privacy policies found and extracted | 16 of 20 | Sep 2026 |
| Discovery on 100 random ToS;DR services | Privacy policy found on 68 of 86 reachable sites (79%) | | Oct 2026 |
| Quote verification | 99.7% of 627 cited quotes found word for word | 95% | Oct 6, 2026 |
| Classifier (TF-IDF + logistic regression, OPP-115 test split) | Macro F1 0.765 | 0.70 | Oct 2026 |
| Run-to-run consistency | Not measured yet | 90% agreement | |
| Agreement with ToS;DR | Not usable yet (see below) | | |

## Discovery

**Feasibility gate.** We ran discovery on 20 hand-picked sites from large, medium and small
services, and checked each extracted policy by hand. 19 of 20 privacy policies passed. Canva failed: it blocks
automated visitors, and we got back only 61 characters of text. The gate in the proposal was
16 of 20. Per-site results: [spike_a/results/report.md](../pipeline/spike_a/results/report.md).

**Random sample.** On 100 random services from the ToS;DR catalogue, discovery found a privacy policy
on 68, terms of service on 56, and at least one document on 72, in 5 minutes. 14 sites couldn't be
reached at all (blocked or down), so among the 86 reachable sites the privacy policy rate is 79%.

**Wrong-document check.** Reviewers on the audit page found that 11 of 44 scored sites had been rated
on the wrong page (a marketing page or a "privacy center" hub). Discovery was fixed to follow hubs to
the real policy and skip side-program terms and blog posts. After a recrawl ($0.96 of LLM cost), all
11 have their real policy except Reddit, which blocks our crawler and is reported as "no policy found".

## Quote verification

Every quote the AI cites is checked against the stored document in code
([verify.py](../pipeline/imbroglio/verify.py)). It forgives only differences that don't change
meaning (whitespace, curly versus straight quotes, letter case, an ellipsis skipping words) plus a
strict fuzzy match for one-character typos. It never accepts a quote whose negations ("not", "never",
"no") differ from the document. Quotes must also contain one of the question's evidence words, so a
real quote about a different topic doesn't count.

Across the first 40 rated sites, 99.7% of 627 cited quotes verified. Unverified quotes are stored for
review but never shown, and a finding with none is never scored.

**Model choice.** We ran Claude Haiku 4.5 and Claude Sonnet 5 on the same policies. Haiku verified
100% of its quotes at $0.064 per document; Sonnet verified 98.5% at $0.036 per document and was more
willing to answer "not disclosed" instead of stretching. They agreed on 83% of answers. We use Sonnet.

## Classifier

TF-IDF features with one-vs-rest logistic regression, trained on the OPP-115 corpus (115 privacy
policies annotated by law students), split by policy (80/10/10, seed 42) so no policy appears in two
splits. Macro F1 is 0.765 on both the dev and test splits, above the 0.70 target. The weakest
category is Data Retention (F1 0.444 on dev, 0.545 on test), which has the fewest examples. Full
per-category precision, recall and F1:
[spike_b/results/metrics.md](../pipeline/spike_b/results/metrics.md).

This is the baseline. The neural network classifier and its comparison against this baseline are in
progress, and no classifier is used in live ratings yet.

## Ratings spread

Under scorer s1, all 45 analyzed sites rated SEVERE (29) or EXTENSIVE (16), so the rating didn't tell
sites apart. Five scoring schemes were compared on the same stored findings:
[rubric-calibration.md](rubric-calibration.md). The chosen replacement, scorer s2, is described in
[rubric.md](rubric.md).

## Not measured yet

- **Run-to-run consistency (N2).** Analyze 50 documents three times each with the same rubric and
  model, and count how often the answers match. Target: 90% agreement. Sonnet 5 doesn't accept a
  temperature setting, so consistency has to be measured rather than configured. Estimated cost:
  about $7.50.
- **Agreement with ToS;DR.** 37 of our sites are also graded by ToS;DR, but 30 of those are D or E,
  so their letter grades are too narrow to compare against (every scheme correlated between -0.1 and
  0.24). They also grade things outside privacy, like arbitration. We plan to compare against their
  individual findings ("this service sells your data") instead of their letter grade.
- **Change detection audit.** Waits on the daily change monitor.
- **Retrieval.** Precision@k and MRR for clause retrieval, compared with whole-document extraction.
