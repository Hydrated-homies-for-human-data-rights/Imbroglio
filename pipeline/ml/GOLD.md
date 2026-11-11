# Gold set protocol (draft for Gage and Sam)

Every label in the paragraph dataset is Claude's. The gold set is the small part labeled by people,
and it is the only thing any of our ML results get tested against. Without it we can only report how
well a model copies Claude.

Status: draft protocol, tooling built (see the end). Decisions marked **open** need Gage and Sam.

## What it is used for

| Who | Measurement | Gold label used |
| --- | --- | --- |
| Sam | Agreement between the two annotators (Cohen's kappa) | both raw label sets |
| Sam | Claude's answers against people's, per question | answers |
| Sam | Precision and recall of the evidence-word filter | passage relevance of quoted paragraphs |
| Sam | Classical baselines (TF-IDF + logistic regression, linear SVM) | passage relevance |
| Gage | Transformer paragraph classifier, per-question P/R/F1 | passage relevance |
| Gage | BM25 against the classifier as a ranker, recall@k | passage relevance |

## Prerequisite: a frozen split

Gold documents come from the test split, so the split has to be final first. Split 0 groups only
identical texts. Template policies that differ by a company name can still sit on both sides, and a
gold document whose near-twin is in training would flatter every model. Split 1 adds near-duplicate
groups (`ml.neardup`, see README.md); once its threshold has been checked by hand it is frozen and
never reassigned.

## Sample

**24 documents** from the test split: 13 privacy policies and 11 terms of service, in proportion to
the test split (77 and 68). Drawn at random with a fixed seed, leaving out documents with more than
250 substantive paragraphs (about the longest 8%) to keep the work bounded. That exclusion is a
known bias and gets reported. **Open:** 24 or 30 documents (see Effort).

Substantive means 40 characters or more. Shorter lines are mostly headings; they are shown for
context but not judged.

## What annotators do, per document

Two layers, always in this order, so the candidate list can't steer the answers.

**A. Answers.** Read the document and answer all 14 questions with the rubric's statuses and
guidance (`rubric/v0.2.yaml`), or `not_disclosed`. Mark the paragraph or paragraphs the answer rests
on. Claude's answer is hidden. A free-text note and an "unsure" flag are optional.

**B. Passages.** For each question, judge a list of candidate paragraphs: does this paragraph help
answer the question, yes or no? Candidates are pooled, and where each came from is hidden:

- paragraphs holding one of Claude's quotes, verified or rejected by the evidence-word check
- paragraphs containing one of the question's evidence words
- paragraphs the annotator marked in layer A
- later, the top-ranked paragraphs from each model to be tested that aren't judged yet (judged
  before that model is scored)

Pooling is how search evaluations are built (TREC). It misses relevant paragraphs that no source
proposed, so we measure how much it misses:

**C. Pool check.** 10 random substantive paragraphs per document that are in no pool. For each,
mark which questions, if any, it helps answer. This estimates the share of relevant paragraphs the
pool misses, with a confidence interval, which bounds how optimistic the recall figures are.

## Two annotators

1. **Pilot.** Both label the same 2 documents from the dev split, compare, and tighten the guideline.
   Pilot labels are not part of the gold set.
2. **Double-labeled.** The first 12 gold documents are labeled by both, independently. Kappa is
   computed on these raw labels: per question for layer A, over all judgments for layer B.
3. **Adjudication.** Disagreements on those 12 are settled together, and the settled label is gold.
   Both raw labels are kept.
4. **Single-labeled.** The remaining 12 are split, 6 each.

## Effort

From the test split: a median document has 81 substantive paragraphs, takes about 18 minutes to
read, and has about 151 pooled judgments across the 14 questions (mean 209). At about 5 seconds a
judgment that is about 35 to 45 minutes per document, plus a few minutes for layer C.

| Plan | Documents each annotator labels | Hours each, roughly |
| --- | --- | --- |
| 24 documents (12 double, 12 single) | 18 | 11 to 14 |
| 30 documents (15 double, 15 single) | 22 or 23 | 14 to 17 |

Plus about 2 hours together for the pilot and adjudication.

Thin questions stay thin: at 24 documents, questions like breach notification will have only a
handful of positive paragraphs, so their figures get wide intervals or are reported together.

## Tooling (`ml/gold.py`)

Run from `pipeline/` with `PYTHONPATH=.`:

    python -m ml.gold sample data/imbroglio/v0.2-split1 --out ml/gold/sample.csv
    python -m ml.gold pool data/imbroglio/v0.2-split1 --sample ml/gold/sample.csv --out data/imbroglio/gold
    python -m ml.gold serve data/imbroglio/gold --labels ml/gold/labels
    python -m ml.gold disagree data/imbroglio/gold --labels ml/gold/labels

- **sample** draws the 2 pilot documents (dev, at most 120 substantive paragraphs) and the gold
  documents, and writes who labels each. The double set takes its share of each type, and single
  documents alternate between Gage and Sam. It refuses to overwrite an existing sample, since the
  draw happens once, after split 1 is frozen.
- **pool** writes each document's lines, its candidates per question, and its pool-check sample to
  `data/` (policy text, so out of git), plus `sources.jsonl`, which records where every candidate
  came from and is never shown on the page. A paragraph holding one of Claude's quotes is a
  candidate however short it is; evidence words count only in paragraphs of 40 characters or more,
  since a heading like "Advertising" would always match.
- **serve** runs the labeling page at `http://127.0.0.1:8765/?a=gage` (or `?a=sam`). It listens on
  localhost only. A server replaced the draft's browser-only page so labels land in
  `ml/gold/labels/<annotator>/<version_id>.json` as you go, instead of depending on browser storage
  and remembering to export.
- **disagree** compares the double-labeled documents both annotators have finished and writes
  `disagreements.csv` with an empty `settled` column for adjudication. Passages only one annotator
  judged (their own layer A marks) aren't counted as disagreements. `--pilot` includes the pilot.

The page shows the document on the left and the task on the right:

1. **Answers.** One question at a time with its guidance and answers. Click lines on the left to
   mark what the answer rests on. Finishing locks the answers, because the next step shows
   candidates.
2. **Passages.** One candidate at a time, in document order, with the question above it. `Y` and
   `N` judge it and move on; the arrow keys step back and forth. The annotator's own marked lines
   are added to the candidates.
3. **Pool check.** The random unpooled paragraphs, each with a checkbox per question and "None of
   these".

It also records active seconds per step (idle for a minute stops the clock) for the effort figures.

Labels reference documents by `version_id` and paragraphs by line number, never by text, so the
label files can be committed; notes shouldn't paste policy text. Kappa, Claude against people and
the evidence-word filter's precision and recall are analysis on top of these files (Sam's part) and
aren't in `ml/gold.py`.

A trial run on split 1 as it stands (not frozen) gave candidate counts from 13 to 426 per gold
document, 180 on average, which matches the effort estimate above. With single documents
alternating, one annotator can end up with about 15% more judgments than the other.

## Answers only: the label set for the v1.0 launch bar

The launch bar in `docs/rubric-v1.md` asks one thing of the gold set: do Claude's answers match
people's? That needs layer A only, which is about a third of the work, so the tooling has an
answers-only mode. It labels against any rubric (v0.3 now, v1.0 once it is run) and spreads the work
over all four of us.

    python -m ml.gold sample data/imbroglio/v0.2-split1 --out ml/gold/answers/sample.csv \
        --annotators gage,sam,alex,jaiden --privacy 20 --terms 10 --double 12
    python -m ml.gold pool data/imbroglio/v0.2-split1 --sample ml/gold/answers/sample.csv \
        --out data/imbroglio/gold-answers --rubric v0.3 --answers-only
    python -m ml.gold serve data/imbroglio/gold-answers --labels ml/gold/answers/labels
    python -m ml.gold disagree data/imbroglio/gold-answers --labels ml/gold/answers/labels
    python -m ml.gold agree data/imbroglio/gold-answers --labels ml/gold/answers/labels --out runs/agree.md

- **sample** with `--annotators` gives each double-labeled document to the next pair in turn (all
  six pairs come up equally) and single documents to each person in turn; everyone labels the pilot.
  30 documents with 12 double-labeled is about 10 to 11 documents each.
- **pool --answers-only** writes the documents without candidates or a pool check, and records the
  mode and the annotators in `tasks.json`.
- **serve** shows only the answers step; "Finish document" saves and opens the next one. Each person
  opens `?a=<their name>`.
- **disagree** compares answers only in this mode, naming the pair on each row.
- **agree** reads Claude's stored answers for the same documents and rubric from the database and
  reports, per question, how often they match people's: the launch bar's figure. Each finished label
  counts once; blanks are skipped.

Effort: at about 18 minutes a document, 30 documents with 12 labeled twice is about 3 to 4 hours
each across four people.

