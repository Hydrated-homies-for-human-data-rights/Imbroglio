// Every figure on /research, in one place. All of them come from the ML
// workstreams' result files (pipeline/ml, run summaries under
// data/imbroglio/runs) and docs/evaluation.md, measured on the development
// split unless a table says otherwise.
//
// `null` means not measured yet: the page shows "pending" in its place. Fill
// a figure in here when its result exists, and move its row in STATUS along.
// Nothing here is estimated ahead of time.

export type Fig = number | null

export const AS_OF = "November 19, 2026"
export const WEEK = "week 14 of 15"

export const fixed = (v: Fig, digits = 3) => (v === null ? null : v.toFixed(digits))
export const pct = (v: Fig, digits = 1) => (v === null ? null : `${v.toFixed(digits)}%`)

// ---- the people and their portions ----

export type Person = {
  key: "sam" | "gage" | "alex"
  name: string
  portion: string
  summary: string
  methods: string[]
  questions: string
}

export const PEOPLE: Person[] = [
  {
    key: "sam",
    name: "Sam Holton",
    portion: "Label quality and classical models",
    summary:
      "How far Claude’s answers can be trusted as training labels, how to keep copied policies from leaking into the test, and how far classical text models get.",
    methods: [
      "Near-duplicate detection: five-word shingles and exact Jaccard similarity over 472,464 document pairs",
      "Leakage analysis of eight grouping thresholds over five resampled splits",
      "Run-to-run reliability of Claude’s answers: agreement rates and Fleiss’ kappa with bootstrap intervals",
      "The shared evaluation module: ranking and detection measures, resampling by site group, paired significance tests",
      "TF-IDF features with logistic regression and a linear SVM, regularization tuned per question",
      "Error analysis of the classical models",
      "On the gold set: Cohen’s kappa between people, Claude against people, precision and recall of the evidence-word check",
    ],
    questions: "Part one, and the gold set in part four",
  },
  {
    key: "gage",
    name: "Gage Gunn",
    portion: "Transformer fine-tuning and distillation",
    summary:
      "Whether a small transformer trained on Claude’s labels can learn to find the same evidence, what drives its accuracy, and how it compares with search and classical models.",
    methods: [
      "A weakly supervised dataset built from model output: 130,672 paragraphs, three-way labels, splits grouped by site",
      "A BM25 search baseline with three query designs and tuned parameters",
      "Fine-tuning RoBERTa and legal-bert as 14-way multi-label classifiers, distilling Claude’s judgments",
      "Class-imbalance weighting and positive-unlabeled learning for paragraphs Claude didn’t quote",
      "Four controlled experiments over three seeds each, 36 training runs, with seed spread reported apart from sampling error",
      "The gold-set protocol and labeling tool: stratified sample, pooled candidates, a check on what the pool misses",
      "Decision rules and every model's cut-offs fixed before any gold label is read, and the tool that scores the models on it",
      "On the gold set: precision, recall and F1 per question, and ranking against BM25",
    ],
    questions: "The dataset, part two, and the gold set in part four",
  },
  {
    key: "alex",
    name: "Alex Kimoni",
    portion: "A neural classifier on OPP-115, with calibration",
    summary:
      "Whether a neural network beats a TF-IDF baseline on a public benchmark labeled by people, and whether its confidence can be trusted.",
    methods: [
      "A neural multi-label classifier on OPP-115: 115 privacy policies, ten categories, labeled by law students",
      "Comparison against the TF-IDF and logistic regression baseline, split by policy",
      "Calibration: reliability diagrams and expected calibration error",
    ],
    questions: "Part three",
  },
]

// ---- where it stands ----

export type State = "done" | "now" | "later"
export const STATUS: { work: string; who: string; state: State; when: string }[] = [
  { work: "Paragraph dataset from 973 documents", who: "Gage", state: "done", when: "" },
  { work: "Run-to-run consistency study", who: "Sam", state: "done", when: "Oct 30" },
  { work: "Near-duplicate grouping and leakage table", who: "Sam", state: "done", when: "" },
  { work: "Shared metrics with group resampling", who: "Sam", state: "done", when: "" },
  { work: "Tuned logistic regression and linear SVM", who: "Sam", state: "done", when: "" },
  { work: "BM25 search baseline", who: "Gage", state: "done", when: "" },
  { work: "Fine-tuned transformers and four controlled experiments", who: "Gage", state: "done", when: "" },
  { work: "Gold-set protocol and labeling tool", who: "Gage", state: "done", when: "" },
  { work: "Gold-set decision rules, fixed thresholds and scoring tool", who: "Gage", state: "done", when: "" },
  { work: "Review of 34 near-duplicate pairs, then freeze the split", who: "Sam", state: "done", when: "Nov 12" },
  { work: "Error analysis write-up for the classical models", who: "Sam", state: "done", when: "Nov 19" },
  { work: "OPP-115 neural classifier and calibration", who: "Alex", state: "now", when: "week 14" },
  { work: "Gold set: labels, agreement between people, Claude and the models against people", who: "Everyone", state: "now", when: "week 15" },
  { work: "Held-out test split, scored once", who: "Gage and Sam", state: "done", when: "Nov 19" },
  { work: "Final presentation", who: "Everyone", state: "later", when: "week 15" },
]

// ---- question 1: the dataset ----

export const SPLITS = [
  { split: "Training", docs: 682, sites: 391, groups: 357, paragraphs: 92839 },
  { split: "Development", docs: 149, sites: 84, groups: 80, paragraphs: 18869 },
  { split: "Test, held out", docs: 142, sites: 84, groups: 77, paragraphs: 18964 },
]

// The 14 questions, with positive paragraphs per split and, for the
// development split, the number of (document, question) pairs ranked, plus
// each ranking model's mean reciprocal rank on them and the run-to-run
// figures from the consistency study.
export type Check = {
  label: string
  pos: [number, number, number]
  pairs: number
  mrr: { bm25: number; logreg: number; roberta: number }
  same: number
  kappa: Fig
}

export const CHECKS: Check[] = [
  { label: "Sells personal data", pos: [296, 73, 64], pairs: 60, mrr: { bm25: 0.793, logreg: 0.894, roberta: 0.906 }, same: 86, kappa: 0.85 },
  { label: "Shares for advertising", pos: [486, 104, 97], pairs: 74, mrr: { bm25: 0.628, logreg: 0.67, roberta: 0.674 }, same: 84, kappa: 0.84 },
  { label: "Collects sensitive data", pos: [378, 97, 105], pairs: 61, mrr: { bm25: 0.703, logreg: 0.778, roberta: 0.789 }, same: 82, kappa: 0.76 },
  { label: "Collects from third parties", pos: [233, 59, 60], pairs: 51, mrr: { bm25: 0.498, logreg: 0.651, roberta: 0.717 }, same: 80, kappa: 0.73 },
  { label: "Retention period", pos: [490, 114, 94], pairs: 93, mrr: { bm25: 0.71, logreg: 0.828, roberta: 0.826 }, same: 92, kappa: 0.91 },
  { label: "Deletion on request", pos: [427, 100, 104], pairs: 87, mrr: { bm25: 0.595, logreg: 0.799, roberta: 0.792 }, same: 82, kappa: 0.76 },
  { label: "Access and export", pos: [383, 87, 80], pairs: 68, mrr: { bm25: 0.593, logreg: 0.778, roberta: 0.779 }, same: 72, kappa: 0.64 },
  { label: "Opt out of tracking", pos: [508, 104, 97], pairs: 71, mrr: { bm25: 0.62, logreg: 0.713, roberta: 0.71 }, same: 80, kappa: 0.78 },
  { label: "Security measures", pos: [422, 106, 103], pairs: 89, mrr: { bm25: 0.807, logreg: 0.886, roberta: 0.865 }, same: 98, kappa: 0.97 },
  { label: "Breach notification", pos: [56, 10, 19], pairs: 10, mrr: { bm25: 0.87, logreg: 0.95, roberta: 0.837 }, same: 100, kappa: 1.0 },
  { label: "Trains AI on user data", pos: [130, 37, 27], pairs: 32, mrr: { bm25: 0.747, logreg: 0.932, roberta: 0.829 }, same: 96, kappa: 0.89 },
  { label: "Content license", pos: [221, 51, 55], pairs: 51, mrr: { bm25: 0.915, logreg: 0.99, roberta: 0.879 }, same: 100, kappa: null },
  { label: "Discloses to government", pos: [472, 96, 102], pairs: 85, mrr: { bm25: 0.807, logreg: 0.925, roberta: 0.898 }, same: 86, kappa: 0.8 },
  { label: "Notifies users of requests", pos: [42, 11, 11], pairs: 11, mrr: { bm25: 0.667, logreg: 0.955, roberta: 0.919 }, same: 100, kappa: 1.0 },
]

// ---- question 2: near-duplicates ----

export const LEAKAGE = [
  { threshold: "Identical texts only", mean: 3.9, range: "2.9 to 4.5", groups: 15, largest: 3 },
  { threshold: "0.9", mean: 2.5, range: "1.7 to 3.7", groups: 17, largest: 5 },
  { threshold: "0.7", mean: 1.8, range: "1.0 to 3.2", groups: 20, largest: 5 },
  { threshold: "0.5", mean: 2.5, range: "1.7 to 3.7", groups: 23, largest: 5 },
  { threshold: "0.4", mean: 2.0, range: "1.6 to 2.2", groups: 23, largest: 5 },
  { threshold: "0.3", mean: 1.3, range: "0.9 to 1.9", groups: 27, largest: 6, chosen: true },
  { threshold: "0.2", mean: 1.4, range: "0.9 to 2.0", groups: 35, largest: 7 },
  { threshold: "0.1", mean: 1.0, range: "0.8 to 1.1", groups: 45, largest: 13 },
]

// the 34 pairs in neardup/review.csv: 17 marked by Sam, 17 by Claude following her calls (its `by` column)
export const NEARDUP_REVIEW: { label: string; value: Fig | string }[] = [
  { label: "Pairs marked the same template", value: 28 },
  { label: "Pairs marked shared stock wording", value: 5 },
  { label: "Pairs marked different", value: 1 },
  { label: "Marked by hand", value: "17 of 34" },
  { label: "Templates among the 12 pairs below 0.3", value: 7 },
  { label: "Threshold kept or changed", value: "kept at 0.3" },
]

// ---- question 3: consistency ----

export const CONSISTENCY = [
  { label: "Same answer in all three runs", value: "88.4%", ci: "85.9 to 91.0" },
  { label: "Same answer, averaged over pairs of runs", value: "92.1%", ci: "" },
  { label: "Same rating per category", value: "88.6%", ci: "84.9 to 92.0" },
  { label: "Same overall rating for the site", value: "66.0%", ci: "54.0 to 80.0" },
]

// ---- questions 5 and 6: ranking ----

export type Model = {
  name: string
  note?: string
  by?: string
  floor?: boolean
  r1: number
  r5: number
  mrr: number
  auroc: number
  ci?: { r1: string; r5: string; mrr: string; auroc: string }
  sd?: { r1: number; r5: number; mrr: number; auroc: number }
}

export const RANDOM: Model = { name: "Random order", floor: true, r1: 0.016, r5: 0.056, mrr: 0.061, auroc: 0.603 }
export const EVIDENCE: Model = { name: "Has an evidence word", floor: true, r1: 0.152, r5: 0.509, mrr: 0.337, auroc: 0.575 }
export const BM25 = {
  question: { name: "BM25, question words", by: "Gage", r1: 0.348, r5: 0.606, mrr: 0.505, auroc: 0.822 },
  evidence: { name: "BM25, evidence words", by: "Gage", r1: 0.468, r5: 0.824, mrr: 0.663, auroc: 0.818 },
  both: { name: "BM25, both", note: "k1 1.2, b 0.25", by: "Gage", r1: 0.526, r5: 0.846, mrr: 0.711, auroc: 0.867 },
} satisfies Record<string, Model>
export const LOGREG: Model = {
  name: "Logistic regression",
  by: "Sam",
  r1: 0.681,
  r5: 0.938,
  mrr: 0.839,
  auroc: 0.952,
  ci: { r1: "0.642 to 0.720", r5: "0.921 to 0.954", mrr: "0.817 to 0.861", auroc: "0.941 to 0.964" },
}
export const SVM: Model = {
  name: "Linear SVM",
  by: "Sam",
  r1: 0.682,
  r5: 0.926,
  mrr: 0.836,
  auroc: 0.955,
  ci: { r1: "0.644 to 0.718", r5: "0.907 to 0.942", mrr: "0.814 to 0.857", auroc: "0.944 to 0.967" },
}

// logistic regression's errors (ml.errorkinds, data/imbroglio/runs/errorkinds.md): kinds counted by
// fixed rules on the development split; the last row uses logreg-features.json. How many of the
// "errors" people judge relevant waits for the gold set.
export const ERROR_KINDS: { label: string; value: string }[] = [
  {
    label: "Most common kinds of false positive",
    value: "a full sentence on a neighboring topic 53%, a heading 30%, a negated statement 17% (30 in all)",
  },
  {
    label: "Most common kinds of miss",
    value: "a different passage ranked first 53%, the line next to the quote 27%, a heading or lead-in 18% (238 in all)",
  },
  {
    label: "Most informative features per question",
    value: "the question’s own topic words count for it; terms-of-service wording counts against it in 12 of 14 questions",
  },
]
export const ROBERTA: Model = {
  name: "RoBERTa, fine-tuned",
  note: "mean ± sd over 3 seeds",
  by: "Gage",
  r1: 0.648,
  r5: 0.924,
  mrr: 0.816,
  auroc: 0.973,
  sd: { r1: 0.005, r5: 0.005, mrr: 0.002, auroc: 0.003 },
}
export const LEGALBERT: Model = {
  name: "legal-bert, fine-tuned",
  note: "mean over 3 seeds",
  by: "Gage",
  r1: 0.638,
  r5: 0.912,
  mrr: 0.805,
  auroc: 0.974,
}
// RoBERTa (seeds averaged) minus logistic regression, paired bootstrap
export const ROBERTA_VS_LOGREG = {
  r1: { d: -0.026, p: "0.20" },
  r5: { d: -0.001, p: "0.89" },
  mrr: { d: -0.012, p: "0.29" },
  auroc: { d: 0.024, p: "< 0.001" },
}

// ---- question 7: the four experiments (means ± sd over 3 seeds) ----

export type Row4 = { label: string; r1: string; r5: string; mrr: string; auroc: string; chosen?: boolean }

export const SWEEP: Row4[] = [
  { label: "0, confirmed negatives only", r1: "0.610 ± 0.003", r5: "0.908 ± 0.008", mrr: "0.786 ± 0.003", auroc: "0.974 ± 0.001" },
  { label: "0.1", r1: "0.644 ± 0.025", r5: "0.918 ± 0.005", mrr: "0.814 ± 0.013", auroc: "0.973 ± 0.003", chosen: true },
  { label: "0.3", r1: "0.641 ± 0.011", r5: "0.908 ± 0.007", mrr: "0.809 ± 0.004", auroc: "0.969 ± 0.001" },
  { label: "1, all unlabeled as negative", r1: "0.647 ± 0.016", r5: "0.911 ± 0.004", mrr: "0.813 ± 0.010", auroc: "0.959 ± 0.004" },
]

export const CURVE = [
  { fraction: "10% of training sites", fixed: 0.355, matched: 0.68, epochs: 20 },
  { fraction: "25%", fixed: 0.633, matched: 0.741, epochs: 8 },
  { fraction: "50%", fixed: 0.746, matched: 0.77, epochs: 4 },
  { fraction: "100%", fixed: 0.814, matched: 0.814, epochs: 2 },
]

export const BACKBONES: Row4[] = [
  { label: "RoBERTa-base", r1: "0.644 ± 0.025", r5: "0.918 ± 0.005", mrr: "0.814 ± 0.013", auroc: "0.973 ± 0.003" },
  { label: "legal-bert-base", r1: "0.638 ± 0.011", r5: "0.912 ± 0.012", mrr: "0.805 ± 0.012", auroc: "0.974 ± 0.000" },
]

export const TRUNCATION = [
  { label: "RoBERTa, 256 tokens", all: "0.814 ± 0.013", cut: "0.743", rest: "0.814" },
  { label: "RoBERTa, 512 tokens", all: "0.816 ± 0.002", cut: "0.809", rest: "0.818", chosen: true },
  { label: "Logistic regression", all: "0.839", cut: "0.860", rest: "0.818" },
]

// ---- question 8: the gold set (ml/GOLD.md; reports in data/imbroglio/runs/gold-*.md) ----

export const GOLD_AGREEMENT: { label: string; who: string; value: string | null }[] = [
  { label: "Agreement between people on answers (Cohen’s kappa)", who: "Sam", value: null },
  { label: "Agreement between people on passages", who: "Sam", value: null },
  { label: "Claude’s answers against people’s (Cohen’s kappa)", who: "Sam", value: null },
  { label: "Evidence-word check: precision", who: "Sam", value: null },
  { label: "Evidence-word check: recall", who: "Sam", value: null },
  { label: "Share of relevant paragraphs the pool misses", who: "Sam and Gage", value: null },
]

// ml.goldeval score: cut-offs fixed on 2026-11-11 in ml/gold/thresholds.json, means over questions.
// Top five is ranking.
export type PRF = { name: string; precision: Fig; recall: Fig; f1: Fig; top5: Fig | "n/a" }
export const GOLD_MODELS: PRF[] = [
  { name: "BM25, both queries", precision: null, recall: null, f1: null, top5: null },
  { name: "Logistic regression", precision: null, recall: null, f1: null, top5: null },
  { name: "Linear SVM", precision: null, recall: null, f1: null, top5: null },
  { name: "RoBERTa, fine-tuned", precision: null, recall: null, f1: null, top5: null },
  { name: "Claude’s own quotes", precision: null, recall: null, f1: null, top5: "n/a" },
]

// ---- question 9: OPP-115 (Alex) ----

export const OPP115: { label: string; baseline: string | null; neural: string | null }[] = [
  { label: "Macro F1, test", baseline: "0.765", neural: null },
  { label: "Weakest category F1", baseline: "0.545, data retention", neural: null },
  { label: "Per-category precision, recall and F1", baseline: "measured", neural: null },
  { label: "Expected calibration error", baseline: "n/a", neural: null },
  { label: "Reliability diagram", baseline: "n/a", neural: null },
]
export const OPP115_SETUP: string | null = null // Alex's architecture and training setup, when written up

// ---- question 10: the held-out test split (scored once) ----

// scored once on 2026-11-19 (ml.seeds --split test, data/imbroglio/runs/test-once.md), with the
// models fixed on 2026-11-11 in ml/gold/thresholds.json. RoBERTa is the mean over its 3 seeds, as on dev.
export const TEST: { name: string; r1: Fig; r5: Fig; mrr: Fig; auroc: Fig }[] = [
  { name: "BM25, both queries", r1: 0.463, r5: 0.802, mrr: 0.649, auroc: 0.862 },
  { name: "Logistic regression", r1: 0.601, r5: 0.911, mrr: 0.779, auroc: 0.954 },
  { name: "Linear SVM", r1: 0.6, r5: 0.905, mrr: 0.776, auroc: 0.952 },
  { name: "RoBERTa, fine-tuned, 512 tokens", r1: 0.623, r5: 0.889, mrr: 0.792, auroc: 0.96 },
]
// RoBERTa (seeds averaged) minus logistic regression on test, paired bootstrap
export const TEST_ROBERTA_VS_LOGREG = {
  r1: { d: 0.037, p: "0.09" },
  r5: { d: -0.015, p: "0.30" },
  mrr: { d: 0.026, p: "0.14" },
  auroc: { d: 0.008, p: "0.30" },
}
