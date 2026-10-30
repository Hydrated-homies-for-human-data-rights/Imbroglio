# Rubric and scoring rules

This is the published spec for how Imbroglio rates a site (requirement F5). The same content is
served by `GET /v1/rubric` and shown on the website's "How we score" page.

- **Live now:** rubric v0.1 (14 questions, 2 per category), scorer s1
- **Built, switching on next:** scorer s2, "red flags + coverage", with rubric v0.2 (see the end of
  this page). It goes live once the documents have been analyzed under v0.2, by setting
  `RUBRIC_VERSION=v0.2`; the scorer version follows the rubric.
- **Source files:** `pipeline/imbroglio/rubric/v0.1.yaml` and `v0.2.yaml` (the questions) and
  `pipeline/imbroglio/scorer.py` (the rules)

## How a rating is made

1. An AI model reads a site's privacy policy or terms of service and answers every question below,
   choosing only from that question's allowed answers. For each answer it must quote the document.
2. Code checks every quote against the stored text. A quote counts only if it is in the document
   word for word and contains one of the question's evidence words, so it is actually about the
   question. A finding with no quote that passes is stored but never shown or scored.
3. Code turns the verified answers into ratings with the rules below. No model ever assigns a rating.

## Ratings

Every category is rated on one scale, read in one direction: how exposed the user is.

| Rating | Meaning |
| --- | --- |
| SEVERE | The practice is present at its broadest, with no meaningful limit or choice disclosed |
| EXTENSIVE | The practice is present and broad, with some limit or choice disclosed |
| MODERATE | The practice is present with clear limits, or a choice the user can exercise |
| LIMITED | The practice is narrow, absent, or the user is protected by a specific commitment |
| NOT DISCLOSED | The documents say nothing about the practice |

On screen each rating is a shape, a word and a color together, so it never relies on color alone (N3).

## Scorer s1 (live)

1. Only verified findings count.
2. A category's rating is the highest exposure among its verified findings.
3. A category the documents don't address is NOT DISCLOSED. Silence is reported, never filled in.
4. With both a privacy policy and terms of service, each category takes the worse of the two.
5. The overall rating is the worst category, never an average.

## The questions (rubric v0.1)

### Data selling and sharing

**`sells_personal_data`**: Does the company sell users' personal information?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | SEVERE | Personal information is sold |
| `no` | LIMITED | The document states personal information is not sold |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `sell`, `sale`, `sold`

**`shares_for_advertising`**: Is personal information shared with third parties for advertising or marketing?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | EXTENSIVE | Shared with third parties for advertising or marketing |
| `service_providers_only` | MODERATE | Shared only with service providers acting on the company's behalf |
| `no` | LIMITED | The document states it is not shared for advertising |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `advertis`, `marketing`, `ad network`, `ads`, `partner`, `third part`

### Collection scope

**`collects_sensitive_data`**: Does the company collect sensitive categories of data (precise location, biometrics, health, financial, or government ID)?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | EXTENSIVE | One or more sensitive categories are collected |
| `no` | LIMITED | The document states no sensitive categories are collected |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `location`, `biometric`, `health`, `medical`, `financial`, `bank`, `credit card`, `payment card`, `government`, `social security`, `passport`, `driver`, `fingerprint`, `face`, `precise`, `genetic`, `sexual`, `racial`, `religio`

**`collects_from_third_parties`**: Does the company obtain information about users from other companies (data brokers, partners, social networks)?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | EXTENSIVE | Information about users is obtained from third parties |
| `no` | LIMITED | Information is collected only from the user and their use of the service |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `third part`, `partner`, `data broker`, `other sources`, `other companies`, `social media`, `social network`, `publicly available`, `affiliate`, `service provider`

### Retention and deletion

**`retention_period`**: How long is personal information kept?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `specific` | LIMITED | A concrete retention period or deletion trigger is stated |
| `vague` | EXTENSIVE | Retention is described only in open-ended terms |
| `indefinite` | SEVERE | Information may be kept indefinitely |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `retain`, `retention`, `store`, `keep`, `kept`, `delete`, `period`, `days`, `months`, `years`

**`deletion_on_request`**: Can users have their personal information deleted?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `all_users` | LIMITED | Any user can request deletion |
| `some_jurisdictions` | EXTENSIVE | Deletion is offered only to residents of certain jurisdictions |
| `no` | SEVERE | Deletion is not offered |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `delete`, `deletion`, `erase`, `erasure`, `remove`

### User rights

**`access_and_export`**: Can users access or export the personal information held about them?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `all_users` | LIMITED | Any user can access or export their information |
| `some_jurisdictions` | EXTENSIVE | Offered only to residents of certain jurisdictions |
| `no` | SEVERE | Access or export is not offered |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `access`, `copy`, `export`, `portab`, `download`

**`opt_out_of_tracking`**: Can users opt out of tracking, targeted advertising, or the sale or sharing of their information?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | LIMITED | An opt-out is offered to users |
| `limited` | MODERATE | An opt-out exists but is narrow or only for some users |
| `no` | SEVERE | The document indicates no opt-out is offered |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `opt out`, `opt-out`, `unsubscribe`, `do not sell`, `do not track`, `preference`, `choice`, `settings`, `withdraw`, `disable`, `cookie`, `object`

### Security

**`security_measures`**: Does the document describe specific security measures (such as encryption, access controls, or audits)?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `specific` | LIMITED | Specific security measures are described |
| `generic` | EXTENSIVE | Only a generic security commitment is made |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `secur`, `encrypt`, `safeguard`, `protect`, `access control`, `audit`

**`breach_notification`**: Does the company commit to notifying users of a data breach?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | LIMITED | The company commits to notifying users of breaches |
| `no` | EXTENSIVE | The document disclaims or does not commit to notification |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `breach`, `incident`, `unauthori`, `notify`, `notif`

### AI and model training

**`trains_ai_on_user_data`**: Does the company use users' data or content to train AI or machine-learning models?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | SEVERE | User data or content is used to train AI models |
| `opt_in` | MODERATE | Used for training only with the user's opt-in consent |
| `no` | LIMITED | The document states user data is not used to train AI models |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `train`, `machine learning`, `artificial intelligence`, `ai`, `ai,`, `ai model`, `model`, `generative`

**`content_license`**: Do users grant the company a broad license to their content (for example worldwide, royalty-free, sublicensable)?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `broad` | EXTENSIVE | A broad, sublicensable license to user content is granted |
| `limited` | LIMITED | The license is limited to operating the service |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `licen`, `royalty`, `sublicens`, `worldwide`, `right to use`

### Government requests

**`discloses_to_government`**: Under what conditions does the company disclose information to governments or law enforcement?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `legal_process_required` | MODERATE | Disclosure only to comply with law or legal process |
| `broad` | EXTENSIVE | Disclosure to authorities is permitted without requiring legal process |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `government`, `law enforcement`, `subpoena`, `court`, `legal process`, `authorit`, `police`, `regulator`, `warrant`, `lawful request`, `legal request`, `public agenc`, `national security`, `legal obligation`, `applicable law`

**`notifies_users_of_requests`**: Does the company commit to notifying users about government requests for their data?

| Answer | Rating | Meaning |
| --- | --- | --- |
| `yes` | LIMITED | Users are notified of government requests where legally allowed |
| `no` | EXTENSIVE | The document states users are not notified, or disclaims notification |
| `not_disclosed` | NOT DISCLOSED | The document does not address this |

A supporting quote must contain one of: `notify`, `notice`, `inform`, `tell`, `notif`

## Next: scorer s2 and rubric v0.2 (chosen Oct 25, 2026, built Oct 27)

Under s1, all 45 analyzed sites rated SEVERE or EXTENSIVE, so the rating didn't help anyone choose.
[rubric-calibration.md](rubric-calibration.md) compared five schemes on the same findings. The team
chose **red flags + coverage**:

- Each answer is a **high concern**, a **medium concern**, or informational.
- **SEVERE:** two or more high concerns, or one of the two worst on its own: selling data for money,
  or no way to delete your data.
- **EXTENSIVE:** one high concern.
- **MODERATE:** two or more medium concerns.
- **LIMITED:** otherwise, but only if at least 4 of the 6 high concern questions were answered.
  Without that, the site is **UNCLEAR** ("we couldn't confirm enough to rate this"), so silence is
  never read as good.

Decisions on the open questions:

| Question | Decision | Why |
| --- | --- | --- |
| "Sells data" | Split into `sold_for_money` (high) and `state_law_sale` (medium) | 9 of 10 sites flagged for selling only meant the state-law sense, where ad sharing counts as a "sale" |
| AI training | High concern, but medium when the user can opt out (new answer `yes_with_opt_out`). Opt-in only is not a concern | An opt-out is a choice the user can exercise, which is the spec's meaning of MODERATE |
| Sharing with advertisers | Medium concern | 38 of 45 sites do it. A red flag nearly every site gets can't tell sites apart |
| SEVERE threshold | Two red flags, or selling for money or no deletion alone | Those two match the spec's SEVERE: broadest, with no limit or choice |
| Coverage gate | Keep, at 4 of 6 high concern questions | A site isn't called clean on thin evidence |

Informational only, never setting the rating: government requests, generic security wording, the
content license, data from third parties, and sensitive data until payment data is split from
health, biometric and location data.

Built on Oct 27, 2026:

- **Rubric v0.2** (`v0.2.yaml`) adds the two new answers and gives every answer a concern level:
  `severe`, `high`, `medium`, `info` (the practice is present but not rated), or none
  (protective). Selling for money and no deletion are `severe`. Each answer's rating follows its
  concern (severe SEVERE, high EXTENSIVE, medium MODERATE, info INFO, none LIMITED), so a
  category's rating is its most concerning answer. Changing a concern level later is a calibration
  change: no new AI run.
- **Scorer s2** applies the rules above, with one addition the team chose: the overall rating is
  never below an EXTENSIVE or SEVERE category (design goal 5), so two high concerns make a site
  SEVERE even when no single category is. A lone medium concern shows in its category but doesn't
  stop a site being LIMITED.
- **UNCLEAR** is an overall rating only. The API, website and extension show it as a grey "?"
  until the UX team designs it.
- **Preview** on the 52 sites rated under v0.1, treating their "sells data" answers as the
  state-law sense: s1 gave 33 SEVERE and 19 EXTENSIVE; s2 gives 26 EXTENSIVE, 14 MODERATE,
  10 LIMITED and 2 UNCLEAR. The real numbers come from the v0.2 analysis.

Changed the same day, after checking the first build against those 52 sites:

| Problem | Change |
| --- | --- |
| The floor made one medium concern enough for MODERATE, so the "two or more" rule never applied. "Kept as long as necessary" alone (31 of 52 sites) blocked LIMITED | The floor only counts EXTENSIVE and SEVERE categories |
| Informational answers rated their category LIMITED ("narrow, absent, or protected"): 37 sites that collect sensitive data showed Collection as LIMITED | New category rating **INFO** ("reported, not rated"), shown as a grey "i"; a category is LIMITED only when every answer is protective |
| UNCLEAR replaced ratings backed by confirmed concerns (otsutilities.com had three) | The coverage gate only applies to LIMITED |
| `state_law_sale` and ad sharing are the same practice, counted twice | `same_concern_as: shares_for_advertising` counts them once |
| Breach notification `no` read "does not commit", inviting the model to read silence as `no` | `no` now needs a refusal or disclaimer; silence is `not_disclosed` |
| AI training `yes` was given for content licenses that only allow training (khanacademy.org) | Guidance: the document has to say the data is used for models, and only the company's own use counts |

Every one of the 26 EXTENSIVE sites gets there on AI training alone. Whether training on user data
should stay a high concern is a team decision to revisit after the v0.2 analysis.
