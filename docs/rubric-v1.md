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
| Terms of service go mostly unread | Terms are read for 438 sites but no v0.2 question is about them; 129 of 569 sites (23%) have no terms on file at all, and the report didn't say so | Steam scores 100 on its privacy policy alone; its Subscriber Agreement was never found |
| Answers are written for the model | "The document states personal information is not sold" | The report reads like a spec |

## What v1.0 changes

28 questions, up from 14, in eight categories: v0.2's seven and a new **Terms of service** category.
Every v0.2 question is kept, so v0.2 and v1.0 results can be compared question by question.

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
| `shares_with_ai_providers` | AI | may train (high), unspecified (medium) | Data sent to outside AI companies is the newest gap in most policies |
| `human_review` | AI | private content or AI chats (medium) | People reading AI conversations is a common surprise |
| `transparency_report` | Government | none (protective only) | Rewards publishing request statistics |
| `combines_across_products` | Collection | yes (info) | One profile across a company's products; from the coverage check |
| `honors_gpc` | User rights | says it ignores Global Privacy Control (info) | The browser opt-out several state laws require businesses to honor |

**Carried in from v0.3:** lenient evidence matching and v0.3's wider evidence words, "as long as necessary"
retention as info, and v0.3's guidance for opt-outs and AI training. Location words stay out of sensitive
data's list, since `precise_location` asks about them.

**Terms of service** (added Nov 14, after a test user asked about Steam's Subscriber Agreement):

| Question | Concern answers | Why |
| --- | --- | --- |
| `policy_change_notice` | changes take effect when posted (medium) | Can they change the deal without telling you? Fits the change monitor |
| `forced_arbitration` | yes, with or without an opt-out (medium) | Arbitration favors the company, and the opt-out is a letter within 30 days that almost nobody sends |
| `account_termination` | any reason, at their discretion (medium) | Closing accounts only for breaking the rules is normal; "for any reason" is not |
| `purchases_on_termination` | lost without a refund (medium) | Games, media and credits are licenses tied to the account |
| `subscription_changes` | prices or terms change without notice (medium) | ToS;DR's most heavily weighted bad case we didn't cover |
| `content_license` | broad and lasting after you delete it (medium); broad but ending on deletion is info | Moved from AI: it's a terms clause, and ToS;DR rates a license that outlives deletion as bad |

Every terms answer is at most a medium concern, so terms alone can make a site MODERATE but never
EXTENSIVE: losing legal options isn't the same as having your data sold. Boilerplate nearly every site has
("as is", liability capped at what you paid) is left out because it wouldn't tell sites apart.

**No LIMITED without the terms.** A site needs at least one answer from the terms category to be rated
LIMITED (`limited_requires: [terms]` in the rubric file). A site whose terms we couldn't find, or whose terms
say nothing we ask about, is MODERATE at best, with its score kept at 89. It's the same principle as the
coverage gate: silence never earns the best rating. The report and the extension now say when a document
wasn't found, and the crawler now recognizes subscriber, customer and license agreements.

Steam under v1.0, from its current agreement: disputes go to court (good), 30 days' email notice of
changes (good), accounts closed only for breaking the rules (good), but purchases are lost without a
refund when that happens, and the license to what you post lasts as long as its copyright. Two medium
concerns: MODERATE, 76.

**Sharper guidance:** access and export now has a tie-break rule (offered to everyone, with extra rights
in some places, is `all_users`). `collects_sensitive_data` no longer covers precise location.

**Scoring:** scorer s3 from v0.3 (any medium concern makes a site MODERATE; LIMITED scores 90 to 100), plus
the terms rule above. The coverage gate now counts 8 questions with a high or severe answer (up from 6)
and still needs 4 answered, so fewer sites should be UNCLEAR.

## Open decisions for Sam

1. **Evidence words.** Settle them from `cli rejected-quotes` on production before the v1.0 run, starting
   with data from third parties, sensitive data, and access and export. v1.0 already adds "other users".
2. **"As long as necessary" retention:** keep it a medium concern or make it info. `cli score-spread`
   shows how many sites it holds at 40. Decided in v0.3: info.
3. ~~Forced arbitration: medium or info.~~ Decided Nov 14: medium, with or without an opt-out.
4. **Security has 2 questions,** the design spec planned 3. Policies rarely say more than encryption and
   breach notice; a third question would mostly come back "not disclosed".
5. **Human review in the AI category,** or in collection. It is there because AI chats are the main case.
6. ~~Carry v0.3 into v1.0.~~ Done Nov 15.
7. ~~The gap check below.~~ Decided Nov 15: price and subscription changes, Global Privacy Control, and
   combining data across products joined v1.0; the rest stay out.

## Coverage check against ToS;DR (Nov 14)

To find what else we miss, every active case in ToS;DR's public list (`api.tosdr.org/case/v3`: 234 cases,
58 bad and 17 blockers) was compared with v1.0's questions.

**Covered.** Most bad and blocker cases map to a v1.0 question: selling and sharing for ads, tracking
cookies, pixels and fingerprinting, location, sensitive and voice data, data from third parties, retention
and deletion, data kept after deletion, access, opt-outs, AI training, people reading private content,
government requests, changing terms without notice, closing accounts without a reason, the license to
your content, forced arbitration and class-action waivers. Their blocker "the policy refers to documents
that are missing or unfindable" is what the missing-document notice and the terms rule handle.

**Added to v1.0 from this check (Nov 15):**

| Gap | ToS;DR | In v1.0 |
| --- | --- | --- |
| Prices or subscription terms change without notice | bad (80) | `subscription_changes`, medium |
| Data combined across the company's products and affiliates | bad | `combines_across_products`, info |
| Global Privacy Control honored | (not a case) | `honors_gpc`; ignoring it is info |

**Still out, could join later:**

| Gap | ToS;DR | Proposal |
| --- | --- | --- |
| Automated decisions or profiling with real effects (credit, pricing, hiring) | blocker (50, with AI training) | Info; rare for consumer sites |
| Shorter deadline to sue (often one year) | bad | Fold into `forced_arbitration`'s guidance, or info |
| Data transferred if the company is sold or goes bankrupt | bad | Info at most: nearly every policy says it |
| Your name and photo used in ads shown to others | blocker (90) | Rare outside social networks; info |

**Left out on purpose:** liability caps, "as is" and no-guarantee clauses, and indemnity (boilerplate on
almost every site); moderation and conduct rules (about speech, not your data or money); legal-name
and identity requirements; where data is stored; app permissions (not in the documents).

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

4. **Full run:** every stored document under v1.0 (about $40 to $50: $0.036 a document for 23 questions, more for 28 and the extra terms documents), then the launch
   bar measurements. Before it, look again for the terms of the 129 sites that have none, from a
   computer whose network Steam doesn't block, then analyze what's new:

   ```
   python -m imbroglio.cli batch --missing terms
   python -m imbroglio.cli extract --all --limit 200
   ```
5. **Switch:** set `RUBRIC_VERSION=v1.0` on Railway, update `docs/rubric.md` and the "How we score" page.
6. **Launch.**
