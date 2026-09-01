# Spike B — classifier corpus + baseline (parallel ML track, weeks 1–2)

Prepares the OPP-115 corpus and trains the dumbest credible baseline
(TF-IDF + one-vs-rest logistic regression). Its numbers are the floor any
transformer fine-tune must beat, feeding the week-4 gate: per-category
P/R/F1 reported on a held-out split.

## Run

```bash
cd pipeline
.venv\Scripts\activate
pip install scikit-learn numpy
cd spike_b
python prepare.py    # downloads ~95 MB corpus, builds segments.csv + splits
python baseline.py   # trains, writes results/metrics.md
```

## Decisions baked in (revisit knowingly)

- **Labels = majority vote**: category applies when >= 2 of 3 annotators
  assigned it to the segment. Union labeling is the alternative (higher
  recall, noisier); Polisis used union — worth comparing at week 4.
- **Split by policy, not by segment** (80/10/10, seed 42): segments from one
  policy are stylistically correlated; splitting by segment would leak.
- **No tuning**: baseline is a measuring stick, not a candidate model.

## Data notes

- OPP-115: 115 policies, ~3.7k segments, 10 categories, multilabel.
  Research/teaching use with citation (Wilson et al., ACL 2016).
- Corpus lands in `pipeline/data/opp115/` — gitignored (large, licensed);
  `prepare.py` regenerates it deterministically on any machine.
- Known limitation for our rubric: corpus is 2016 — no "AI training"
  category exists. That rubric category will need whole-document extraction
  rather than classifier routing. Flagged in proposal review.
