# Imbroglio labels: training data for the classifier

Labels for every analyzed privacy policy and terms of service, made by Claude (Sonnet 5) under
rubric v0.1. Every quote was checked by our code against the stored document. Regenerate with
`python -m imbroglio.cli export-labels --out <dir>`.

**Keep this inside the team.** `documents.jsonl` contains companies' policy text, so don't post it
publicly or commit it to the repo.

## Files

**`rubric.yaml`**: the 14 checks (questions) across 7 categories. Each check lists its allowed
statuses with an `exposure` level (0 = LIMITED … 3 = SEVERE) and `evidence` keywords a supporting
quote must contain. Rubric v0.1 is a placeholder; Sam's v1 will replace it (see "Known label
issues").

**`documents.jsonl`**: one row per document version.

| field | meaning |
| --- | --- |
| `version_id` | join key to labels |
| `domain`, `doc_type` | site and `privacy` or `terms` |
| `url`, `content_hash` | where it came from; identical texts share a hash |
| `text` | the full normalized text, one paragraph or heading per line |

**`labels.jsonl`**: one row per (document, check). Every check is answered for every document.

| field | meaning |
| --- | --- |
| `check_id`, `category` | which rubric question |
| `status` | the answer, one of the check's statuses or `not_disclosed` (the document doesn't address it) |
| `exposure` | 0–3 from the rubric; null for `not_disclosed` |
| `quotes` | 0–3 passages Claude cited, meant to be verbatim |
| `quotes_verified` | per quote: found word for word in `text` **and** contains an evidence keyword |
| `verified` | at least one quote verified. **Only use rows where this is true**, plus `not_disclosed` rows |
| `explanation` | Claude's one-sentence reason |
| `labeler`, `provenance` | which model; `machine` until a human reviews it |

## Turning it into a training set

The natural unit is the paragraph. A small model can't read a 50-page policy, but it can classify
one paragraph.

1. Split `text` on newlines into paragraphs.
2. **Positives:** a paragraph that contains a verified quote gets that label (`check_id`, `status`).
   Quotes can use " ... " to skip words; match each piece in order.
3. **Negatives, carefully.** Claude cites at most 3 quotes per check, so a paragraph it didn't quote
   may still be relevant. **Don't treat unquoted paragraphs as negatives.** Clean negatives come from
   documents whose label for that check is `not_disclosed`: if the document never addresses the
   question, none of its paragraphs do. Treat everything else as unlabeled.
4. **Two tasks** work better than one:
   - **Relevance (multi-label):** which checks does this paragraph address?
   - **Status:** given a relevant paragraph, which answer?

   Some statuses are about the whole document, such as "retention is vague" or "deletion only in
   some states". They are hard from a single paragraph; expect weaker results there and report them
   separately.
5. **Split by site, not by row.** Keep all of a domain's documents in the same split, and keep
   documents with the same `content_hash` together. Several sites share identical policy text, and
   splitting them leaks answers into the test set.

## Size and balance

About 45 sites and 90 documents: enough to prototype a pipeline, not to train a strong model. Count
labels per status before training. Some statuses have only a handful of examples, for example
`retention_period: indefinite` and `notifies_users_of_requests: no`. More labels cost about $0.05 per
document through the same pipeline, so tell Gage how many you need.

## Known label issues

- **`sells_personal_data: yes` mostly means ad cookies.** 9 of 10 cases are the state-law meaning of
  "sale" (ad and tracking sharing counts as a sale), not selling data for money. Rubric v0.2 splits
  this check; expect these labels to change.
- `content_license` and several other checks are usually only answered in terms of service, and the
  privacy checks only in privacy policies. That's expected, not missing data.
- Labels are Claude's answers, not ground truth. Evaluate on a human-checked subset, using the
  prototype's audit page or our own review, and on OPP-115, the 115 human-annotated policies, where
  its categories overlap ours. Otherwise you're measuring how well the model copies Claude.

## How it's used later

The plan is: our classifier handles each paragraph; when it isn't confident, the paragraph goes to
Claude. A classifier label also comes with its receipt for free, because the evidence is the
paragraph itself. So per-check accuracy and confidence calibration matter more than one overall F1.

Questions → Gage.
