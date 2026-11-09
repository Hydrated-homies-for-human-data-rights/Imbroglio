# Rubric v1.0 (draft, for review)

**Status:** draft. The questions are in `pipeline/imbroglio/rubric/v1.0.yaml` and pass every check the
loader runs, but nothing uses them yet: the live site stays on v0.2 until v1.0 is reviewed, run on every
document, and meets the launch bar below. Sam owns the rubric; this page is the proposal to review.

The goal is a rating people can trust when the site launches publicly at the end of the semester.

## What is wrong with v0.2, measured

| Problem | Evidence | Where it hurts |
| --- | --- | --- |
| One answer decides most bad ratings | 65 of 79 EXTENSIVE sites are there only for "trains AI on user data", whether the site tunes a spam filter on usage data or trains models on private messages | Ratings don't tell sites apart |
| Real quotes are thrown out | Only 51% of real quotes count for data from third parties, 67% for sensitive data, 71% for access and export; the rest lack an evidence word | 118 of 550 sites (21%) are UNCLEAR |
| Common boilerplate costs points | "Kept as long as necessary" and ad sharing are in most policies; with AI training they push the score below 40, where EXTENSIVE's range holds it | Many sites score exactly 40 |
| Some answers aren't steady | Access and export gives the same answer in all three runs only 72% of the time | Overall rating repeats only 66% of the time |
| Terms of service go mostly unread | Only the content license question is about the terms | Arbitration and changing terms without notice aren't rated |
| Answers are written for the model | "The document states personal information is not sold" | The report reads like a spec |

## What v1.0 changes

23 questions, up from 14, in the same seven categories. Every v0.2 question is kept, so v0.2 and v1.0
results can be compared question by question.

**Every answer gets a `plain` line,** the answer in the reader's words ("They can sell your personal
information for money."). The report, the score breakdown and link previews show it. `meaning` stays
the precise wording the model answers against, and the "How we score" page keeps showing it.

**AI training is rated by what is trained on:**

| Answer | Concern | Plain line |
| --- | --- | --- |
| `private_content` | high | They can use your private content, like messages, files or AI chats, to train AI. |
| `private_content_opt_out` | medium | They can use your private content to train AI unless you opt out. |
| `other_data` | medium | They can use your public posts or how you use the service to train AI. |
| `other_data_opt_out` | info | They can use your public posts or usage to train AI unless you opt out. |
| `opt_in` | none | They only use your data to train AI if you agree to it. |
| `no` | none | They say they don't use your data to train AI. |

**New questions:**

| Question | Category | Concern answers | Why |
| --- | --- | --- | --- |
| `third_party_trackers` | Selling and sharing | advertising (medium, counts once with ad sharing) | Cookies and pixels are how most sharing happens |
| `precise_location` | Collection | yes (medium); with permission is info | Split out of sensitive data, since most apps ask permission |
| `childrens_data` | Collection | collected without parental consent (high) | Required reading for any service kids use |
| `kept_after_deletion` | Retention | kept for other purposes with no limit (medium) | "Delete your account" often doesn't delete everything |
| `policy_change_notice` | User rights | changes take effect when posted (medium) | Fits the change monitor: can they change the deal without telling you? |
| `forced_arbitration` | User rights | yes (medium) | A terms-of-service staple that limits how users enforce their rights |
| `shares_with_ai_providers` | AI | may train (high), unspecified (medium) | Data sent to outside AI companies is the newest gap in most policies |
| `human_review` | AI | private content or AI chats (medium) | People reading AI conversations is a common surprise |
| `transparency_report` | Government | none (protective only) | Rewards publishing request statistics |

**Sharper guidance:** access and export now has a tie-break rule (offered to everyone, with extra rights
in some places, is `all_users`). `collects_sensitive_data` no longer covers precise location.

**Scoring is unchanged:** scorer s2 and the score out of 100 apply as they are. The coverage gate now
counts 8 questions with a high or severe answer (up from 6) and still needs 4 answered, so fewer sites
should be UNCLEAR.

## Open decisions for Sam

1. **Evidence words.** Settle them from `cli rejected-quotes` on production before the v1.0 run, starting
   with data from third parties, sensitive data, and access and export. v1.0 already adds "other users".
2. **"As long as necessary" retention:** keep it a medium concern or make it info. `cli score-spread`
   shows how many sites it holds at 40. This can be tested on stored v0.2 findings at no cost.
3. **Forced arbitration:** medium or info. It limits legal options rather than exposing data.
4. **Security has 2 questions,** the design spec planned 3. Policies rarely say more than encryption and
   breach notice; a third question would mostly come back "not disclosed".
5. **Human review in the AI category,** or in collection. It is there because AI chats are the main case.

## The launch bar

What "accurate" should mean before the site goes public. Each one is measured by a command that
already exists, or by the answer key.

| Measure | Bar | How |
| --- | --- | --- |
| Agreement with hand-labeled answers | 85% of answers | Answer key: 30 to 50 policies labeled on the `feature/gold-set` labeling page |
| Real quotes that count | 90% | `cli rejected-quotes` |
| Same answer across runs | 90% | `cli consistency --rubric v1.0` |
| UNCLEAR sites | under 10% | `cli score-spread` |
| Largest pile on one score | under 15% of sites | `cli score-spread` |

## Plan to the end of the semester

1. **First, rubric v0.3:** the calibration of v0.2 from the first production reports (evidence words,
   "as long as necessary", the AI training split, plain lines). See the end of `docs/rubric.md`. Its
   evidence words and decisions carry into v1.0.
2. **Answer key:** merge the `feature/gold-set` tooling and label 30 to 50 policies.
3. **Trial:** run v1.0 on 20 to 30 sites (about $1) and read the answers against the documents. Running it
   writes v1.0 findings next to the v0.2 ones; the live site keeps showing v0.2:

   ```
   RUBRIC_VERSION=v1.0 python -m imbroglio.cli extract tiktok.com reddit.com discord.com --force
   ```

4. **Full run:** every stored document under v1.0 (about $35 to $40 at $0.036 a document), then the launch
   bar measurements.
5. **Switch:** set `RUBRIC_VERSION=v1.0` on Railway, update `docs/rubric.md` and the "How we score" page.
6. **Launch.**
