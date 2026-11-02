# Imbroglio paragraph dataset

Training and evaluation data for the ML workstreams, built from our own analyzed sites instead of
OPP-115. Nothing here is used by the live pipeline.

    python -m imbroglio.cli export-labels --rubric v0.2 --out exports/labels-v0.2
    python -m ml.dataset exports/labels-v0.2 --out data/imbroglio/v0.2-split0

Both outputs are gitignored. They contain companies' policy text, so keep them inside the team.

## Unit and labels

The unit is one line of a document's normalized text, which is one paragraph or heading. For each
paragraph and each of the rubric's 14 checks, the label is one of three things:

| Label | Rule | Why |
| --- | --- | --- |
| positive | a verified quote for that check lies in the paragraph | Claude cited it, and code confirmed it is word for word and about the question |
| negative | the document's answer to that check is `not_disclosed` | if the document never addresses the question, none of its paragraphs do |
| unlabeled | anything else | Claude cites at most 3 quotes, so an unquoted paragraph may still answer the question |

A quote that spans two lines labels both. Positives also keep the answer (status), for the second
task of predicting the answer from a relevant paragraph.

Quotes found word for word but rejected only because they lack one of the check's evidence words
are kept apart as `kw_failed`. They count as unlabeled for training and are what the evidence-word
filter evaluation looks at.

Answers whose quotes all failed verification leave that check unlabeled for the whole document:
Claude said the document addresses it, but we can't say where.

Two known biases, to report rather than hide: labels are Claude's, not people's (all 13,622 v0.2
findings are `machine`), and positives lean toward paragraphs containing an evidence word, because
the filter decides which quotes count.

## Splits

Train, dev and test (70/15/15 of documents), assigned by group with a fixed seed. A group is every
site that shares a document text (same `content_hash`) with another, so identical policies never
sit on both sides of a split. `--groups` takes a CSV of `domain,group` to merge more, which is
where near-duplicate template detection plugs in.

Split 0 groups identical texts only. Split 1 adds near-duplicate groups from `ml.neardup`:

    python -m ml.neardup exports/labels-v0.2 --out data/imbroglio/neardup
    python -m ml.dataset exports/labels-v0.2 --groups data/imbroglio/neardup/groups.csv \
        --out data/imbroglio/v0.2-split1

`ml.neardup` compares every pair of documents by the Jaccard similarity of their word 5-grams and
groups sites whose documents reach 0.3. The threshold comes from its leakage table: the share of
substantive test paragraphs that also appear word for word in training falls from 3.9% (split 0,
mean of 5 seeds) to 1.3% at 0.3, and going lower barely helps while groups start to chain (13
sites in one group at 0.1). On v0.2 that is 27 groups covering 72 sites: one company on several
domains, terms derived from GitHub's, and sites built from the same policy generator.

What remains is mostly stock sentences that unrelated sites share. Dev and test paragraphs whose
text is also a training paragraph carry `in_train: true` (141 of 14,847 substantive test
paragraphs in split 1), so results can be reported with and without them.

Split 1 is frozen, and the gold set drawn from its test part, once the threshold has been checked by
hand: `review.html` and `review.csv` in the neardup folder hold 34 pairs across the similarity
range, to mark as template, boilerplate or different.

## Files

- `paragraphs.jsonl`: `version_id`, `domain`, `doc_type`, `split`, `idx` (line number), `text`,
  `pos` (check to status), `neg` (checks), `kw_failed` (checks), `in_train`
- `documents.jsonl`: one row per document: `version_id`, `domain`, `doc_type`, `split`, `group`,
  `answers` (check to status, verified or not)
- `stats.md`: counts per split and per check, and quotes that couldn't be placed
