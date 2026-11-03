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
| Quote verification, rubric v0.2, 559 sites | 99.4% of 8,407 cited quotes found word for word; 78.7% also about the question | 95% | Nov 2, 2026 |
| Quote verification, rubric v0, first 40 sites | 99.7% of 627 cited quotes found word for word | 95% | Oct 6, 2026 |
| Classifier (TF-IDF + logistic regression, OPP-115 test split) | Macro F1 0.765 | 0.70 | Oct 2026 |
| Run-to-run consistency (N2), rubric v0.2 | 88.4% of answers the same in all 3 runs (95% CI 85.9% to 91.0%) | 90% | Oct 30, 2026 |
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

Across the first 40 rated sites (rubric v0, October 6), 99.7% of 627 cited quotes verified.

Under rubric v0.2 (November 2: 559 sites, 973 documents, 6,159 answers that cite a quote):

| Measure | Result |
| --- | --- |
| Quotes found word for word in the document | 99.4% (8,356 of 8,407) |
| Quotes found word for word and containing an evidence word (shown on the site) | 78.7% (6,617 of 8,407) |
| Answers with at least one quote found word for word (the proposal's measure) | 99.7% (6,143 of 6,159) |
| Answers with at least one quote that passes both checks (scored) | 84.1% (5,180 of 6,159) |

So the model almost never misquotes: 51 of 8,407 quotes weren't in the document. Nearly all of the
gap comes from the evidence-word check. Some of the quotes it rejects are off topic; others answer the
question in words the list doesn't include ("other users may provide information about you" for data
from third parties). We haven't yet measured how often each happens. Rejected quotes are stored for
review but never shown, and an answer with none is never scored, so a rejected quote costs coverage,
not correctness.

By question, worst first:

| Question | Quotes | Found word for word | Also contains an evidence word |
| --- | --- | --- | --- |
| `collects_from_third_parties` | 682 | 99.9% | 51.0% |
| `collects_sensitive_data` | 853 | 98.6% | 66.9% |
| `access_and_export` | 728 | 99.2% | 71.0% |
| `content_license` | 439 | 100.0% | 75.2% |
| `sells_personal_data` | 577 | 99.5% | 76.9% |
| `security_measures` | 797 | 99.7% | 82.8% |
| `deletion_on_request` | 736 | 99.5% | 82.9% |
| `shares_for_advertising` | 835 | 99.8% | 83.4% |
| `opt_out_of_tracking` | 817 | 98.4% | 85.8% |
| `discloses_to_government` | 750 | 99.3% | 87.2% |
| `retention_period` | 821 | 99.6% | 89.8% |
| `trains_ai_on_user_data` | 219 | 100.0% | 90.9% |
| `notifies_users_of_requests` | 68 | 100.0% | 97.1% |
| `breach_notification` | 85 | 100.0% | 98.8% |

**Correction, November 2.** The figure published on October 31, "91.9% of 13,496 cited quotes
verified", was the share of answers marked verified, and "not disclosed" answers, which cite no
quote, counted as verified. 13,496 was the number of answers, not quotes. The v0.1 figure of 96.5%
it was compared with was counted the same way, so the reported drop between rubrics was mostly an
artifact. On the 92 documents analyzed under both, the share of quotes passing both checks went from
85.1% (v0.1) to 83.9% (v0.2). The lower rate across all sites comes from the sites added since, not
from the rubric change.

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

Under rubric v0.2 and scorer s2, the 550 sites analyzed on October 30 spread across every tier:
MODERATE 239, UNCLEAR 118, LIMITED 84, EXTENSIVE 79, SEVERE 18, NOT DISCLOSED 12. 65 of the 79
EXTENSIVE sites are there for one answer, training AI on user data; whether that alone should be a
red flag is an open rubric question.

## Run-to-run consistency (N2)

50 privacy policies (random, seed 1) were analyzed three times each under rubric v0.2 with Claude
Sonnet 5, 14 questions per run, on October 30 ($5.89). The model doesn't accept a temperature
setting, so this measures how much its answers vary rather than assuming they don't.

| Measure | Result | Target |
| --- | --- | --- |
| Same answer in every run, per document and question | 88.4% (95% CI 85.9% to 91.0%) | 90% |
| Same answer, averaged over pairs of runs | 92.1% | |
| Same category rating in every run (scorer s2) | 88.6% (95% CI 84.9% to 92.0%) | |
| Same overall rating in every run | 66.0% (95% CI 54.0% to 80.0%) | |

Just under the target. The steadiest questions were breach notification, content license and
notification of government requests (100%, mostly "not disclosed"); the least steady was access and
export (72%), where runs moved between "all users" and "some jurisdictions". A single changed answer
can move the overall rating, which is why it agrees far less often than the answers do. Rerun with
`cli consistency` after any rubric or model change; the full per-question table is written by that
command.

## Not measured yet

- **Agreement with ToS;DR.** 37 of our sites are also graded by ToS;DR, but 30 of those are D or E,
  so their letter grades are too narrow to compare against (every scheme correlated between -0.1 and
  0.24). They also grade things outside privacy, like arbitration. We plan to compare against their
  individual findings ("this service sells your data") instead of their letter grade.
- **Change detection audit.** Waits on the daily change monitor.
- **Retrieval.** Precision@k and MRR for clause retrieval, compared with whole-document extraction.
