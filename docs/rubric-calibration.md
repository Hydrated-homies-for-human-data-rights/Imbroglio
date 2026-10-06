# Rubric calibration: why every site rates SEVERE, and what to do about it

*October 2026. Data: the 44 sites analyzed under rubric v0.1. Rerun any time with
`python -m imbroglio.cli calibrate --out runs/calibration.md` (read-only, no LLM cost).*

## The problem

Under the current scorer, 42 of 44 sites (95%) get the top two ratings: 22 SEVERE and 20 EXTENSIVE.
If almost every site is "bad", the rating no longer helps anyone choose.

There are three causes:

1. **The headline is the worst of 7 categories, and most categories have a trigger nearly every site
   hits.** A site has to be clean in all 7 to rate below EXTENSIVE.
2. **Several checks get the same answer on almost every site**, so they can't tell sites apart:

   | Check | Answers (sites) |
   | --- | --- |
   | collects_from_third_parties | yes 32, no 0 |
   | content_license | broad 27, limited 1 (any site that hosts user content needs this license) |
   | collects_sensitive_data | yes 28, no 3 (payment cards count, so every store says yes) |
   | shares_for_advertising | yes 30, no 5 |
   | discloses_to_government | broad 21, legal process 9 (standard "we comply with the law" wording) |
   | security_measures | generic 22, specific 12 |

3. **Two checks are almost never answered.** Notifying users of government requests goes unaddressed
   by 38 of 44 sites, and breach notification by 35 of 44. They add little.

## A bigger problem: 1 in 4 sites was rated on the wrong document

11 of 44 sites answered only 0–4 of the 14 questions. The cause is our document discovery, not the
rubric:

- Apple's "privacy policy" is a Safari marketing page.
- Reddit's is a "Privacy is your right" landing page.
- Proton's is a blog post.
- Dropbox stored its terms of service as the privacy policy.
- PayPal, Spotify, Twitch and Snapchat stored short "privacy center" hub pages instead of the policy
  they link to.
- Airbnb and Tumblr have no privacy policy stored at all.

Under the current scorer these sites still rate EXTENSIVE, from boilerplate. Under any fairer scheme
they would look clean, because silence reads as "nothing bad found." **This needs fixing before any
weighting decision is final, and before we use our data to train a model.** The coverage gate below
keeps it from producing misleading ratings in the meantime.

## Schemes compared

All five run on the same stored findings. Spread runs from 0 (every site gets the same tier) to 1
(evenly spread across the four tiers).

| Scheme | SEVERE | EXTENSIVE | MODERATE | LIMITED | Unclear | Spread |
| --- | --- | --- | --- | --- | --- | --- |
| Current (s1): worst category | 22 | 20 | 0 | 1 | 0 | 0.57 |
| Capped boilerplate | 7 | 24 | 11 | 1 | 0 | 0.76 |
| Red flags | 2 | 20 | 7 | 14 | 0 | 0.84 |
| **Red flags + coverage** | 2 | 20 | 7 | 3 | 11 | 0.74 |
| Concern points | 2 | 13 | 10 | 18 | 0 | 0.87 |

- **Capped boilerplate:** keeps the worst-category rule. Near-universal boilerplate is capped at
  MODERATE, government and security can't exceed MODERATE, and AI training tops out at EXTENSIVE.
- **Red flags:** counts practices a user would actually worry about.
  - **High concern:** sells your data, keeps it indefinitely, no deletion, no access, no opt-out,
    trains AI on your data or content.
  - **Medium concern:** shares with advertisers, rights only in some states or countries, limited
    opt-out, vague retention, disclaims breach notice.
  - **Rating:** 2+ high is SEVERE, 1 high is EXTENSIVE, 2+ medium is MODERATE, otherwise LIMITED.
  - **Informational only, never sets the rating:** government requests, generic security wording,
    the content license, third-party data, sensitive data (until we split payment data from health,
    biometric and location data).
- **Red flags + coverage:** the same, but a site with no red flag is only called clean if at least 4
  of the 6 high-concern questions were answered. Otherwise it is UNCLEAR, shown as "we couldn't
  confirm enough to rate this." Silence is never read as good.
- **Concern points:** bad practices add points and good ones subtract. **Rejected.** It is an average
  in disguise, which the design spec rules out. Khan Academy trains AI on user data yet lands at
  LIMITED, because credits elsewhere cancel it out.

Example under red flags:

- **Pinterest is SEVERE:** sells personal information and trains AI on user content.
- **Bitwarden is MODERATE:** three medium concerns, no red flags.
- **Wikipedia is LIMITED.**

Each rating comes with its reasons, so the receipts story carries straight through to the headline.

## ToS;DR agreement is not a usable target yet

37 of our sites are also graded by ToS;DR, but 30 of those are D or E. The narrow range makes the
correlation meaningless. Every scheme lands between −0.1 and 0.24. ToS;DR also grades things outside
privacy, such as arbitration and account termination. Their per-case verdicts ("this service sells
your data") would be a better check of our *answers* than their letter grade is of our *weights*.

## Recommendation

1. **Adopt "red flags + coverage" as scorer s2.** It is explainable ("SEVERE: sells your data, trains
   AI on your content"), keeps the spec's rule that the rating is never an average, and refuses to
   call a site clean on thin evidence.
2. **Fix discovery** (privacy hub pages, blog posts, sub-program terms), re-crawl the 11 sites, and
   rerun this comparison.
3. **Rubric v0.2 question changes (Sam):**
   - Split `collects_sensitive_data` into payment data (expected) and health, biometric or precise
     location data (high concern).
   - Replace `notifies_users_of_requests` and `breach_notification`, or fold them into one
     "security commitments" question.
   - Consider adding questions users care about: cross-site tracking, data from children, and how
     easy account deletion is.

   Weight changes cost nothing to try. New or changed questions need re-extraction, at about $0.05
   per document.

## Decisions needed from Sam

- Are the high-concern and medium-concern lists right? Two open calls in particular:
  - **AI training:** is it high concern, or medium when the site offers an opt-out?
  - **Sharing with advertisers:** 30 of 35 sites that answer say yes. Is it a red flag, or the norm
    to report without penalty?
- The thresholds: does SEVERE need 2 red flags, or should one of the worst (selling data, no
  deletion) be enough?
- Is the minimum of 4 of 6 high-concern questions the right bar for calling a site clean?
- Optional: a 10-minute class survey ranking these practices would give the weights a cited source
  instead of our judgment.
