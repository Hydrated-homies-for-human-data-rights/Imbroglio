# Rubric calibration: why every site rates SEVERE, and what to do about it

*October 2026. Data: the 45 sites analyzed under rubric v0.1, after the discovery fix
(Oct 20). Rerun any time with `python -m imbroglio.cli calibrate --out runs/calibration.md`
(read-only, no LLM cost).*

## The problem

Under the current scorer, **all 45 sites get one of the top two ratings: 29 SEVERE and 16 EXTENSIVE.**
Not one site rates MODERATE or LIMITED. If every site is "bad", the rating doesn't help anyone choose.

There are three causes:

1. **The headline is the worst of 7 categories, and most categories have a trigger nearly every site
   hits.** A site has to be clean in all 7 to rate below EXTENSIVE.
2. **Several checks get the same answer on almost every site**, so they can't tell sites apart:

   | Check | Answers (sites) |
   | --- | --- |
   | collects_from_third_parties | yes 39, no 0 |
   | shares_for_advertising | yes 38, no 6 |
   | collects_sensitive_data | yes 35, no 4 (payment cards count, so every store says yes) |
   | content_license | broad 31, limited 1 (any site that hosts user content needs this license) |
   | discloses_to_government | broad 24, legal process 14 (standard "we comply with the law" wording) |

3. **Two checks are almost never answered.** Breach notification goes unaddressed by 36 of 45 sites,
   and notifying users of government requests by 37 of 45. They add little.

## "Sells your data" mostly means ad cookies

10 sites answer "yes" to `sells_personal_data`. Reading the quotes, 9 of them use the **legal**
meaning of "sale" from California and other state privacy laws: sharing data with ad and tracking
partners counts as a "sale" even when no money changes hands. For example:

- Grammarly: *"These disclosures may be considered 'sales', 'sharing', or use of personal
  information for 'targeted advertising' under State Privacy Laws."*
- Tumblr: *"In some US states, this data sharing may be considered a 'sale.'"*

The tenth, Chipotle, says it sells data "not for monetary consideration". None of the 10 describe
selling data for money, the way a user reads "sells your data". Today that legal wording triggers our
harshest red flag, and it overlaps with `shares_for_advertising`. **The check needs separate answers
for "sold for money" and "ad sharing that state law calls a sale".** It's the biggest single fix
available.

## Fixed: 1 in 4 sites was rated on the wrong document

The first version of this report (Oct 6) found 11 of 44 sites answering only 0–4 of the 14 questions,
because discovery had stored the wrong page:

- a Safari marketing page for Apple
- a blog post for Proton
- privacy "hub" pages for PayPal, Spotify, Twitch and Snapchat
- side-program terms for PayPal (Rewards) and Snapchat (Geofilters)

Discovery now follows hub pages through to the real policy and skips side programs and articles.
The sites were re-crawled on Oct 19–20, for $0.96 of LLM cost:

- **Real policies now:** all except reddit, answering 7–11 of 14 questions.
- **reddit:** blocks our crawler and is honestly reported as "no policy found".
- **Coverage:** sites the coverage gate marks as unclear dropped from 11 to 3.

## Schemes compared

All five run on the same stored findings. Spread runs from 0 (every site gets the same tier) to 1
(evenly spread across the four tiers).

| Scheme | SEVERE | EXTENSIVE | MODERATE | LIMITED | Unclear | Spread |
| --- | --- | --- | --- | --- | --- | --- |
| Current (s1): worst category | 29 | 16 | 0 | 0 | 0 | 0.47 |
| Capped boilerplate | 10 | 29 | 6 | 0 | 0 | 0.64 |
| Red flags | 3 | 26 | 9 | 7 | 0 | 0.80 |
| **Red flags + coverage** | 3 | 26 | 7 | 6 | 3 | 0.77 |
| Concern points | 2 | 16 | 14 | 13 | 0 | 0.89 |

- **Capped boilerplate:** keeps the worst-category rule. Near-universal boilerplate is capped at
  MODERATE, government and security can't exceed MODERATE, and AI training tops out at EXTENSIVE.
  Still no site below MODERATE.
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
  in disguise, which the design spec rules out. Khan Academy trains AI on user data, yet good
  practices elsewhere pull it down to LIMITED.

Examples under red flags + coverage:

- **SEVERE:** Pinterest (sells, in the state-law sense; trains AI on user content), Grammarly, Spotify.
- **LIMITED:** Apple, Proton, Wikipedia, Dropbox and Coursera, the sites most people would expect to
  come out cleanest.
- **MODERATE:** Bitwarden, Obsidian, Zoom: no red flags, a few medium concerns.

Each rating comes with its reasons, so the receipts story carries straight through to the headline.
Once "sells" is split, most of the 26 EXTENSIVE sites will move: right now many reach EXTENSIVE only
through the ad-cookie sense of "sale".

## ToS;DR agreement is not a usable target yet

From the first run: 37 of our sites are also graded by ToS;DR, but 30 of those are D or E. The narrow
range makes the correlation meaningless (every scheme landed between −0.1 and 0.24). ToS;DR also
grades things outside privacy, such as arbitration and account termination. Their per-case verdicts
("this service sells your data") would be a better check of our *answers* than their letter grade is
of our *weights*.

## Recommendation

1. **Adopt "red flags + coverage" as scorer s2.** It is explainable ("SEVERE: sells your data, trains
   AI on your content"), keeps the spec's rule that the rating is never an average, and refuses to
   call a site clean on thin evidence.
2. **Rubric v0.2 question changes (Sam):**
   - **Split `sells_personal_data`:** `sold_for_money` (high concern), `state_law_sale` (ad sharing
     that state law calls a sale: medium concern, since it's the same thing as
     `shares_for_advertising`), and `no`.
   - **Split `collects_sensitive_data`:** payment data (expected) versus health, biometric or precise
     location data (high concern).
   - **Replace `notifies_users_of_requests` and `breach_notification`**, or fold them into one
     "security commitments" question.
   - Consider adding questions users care about: cross-site tracking, data from children, and how
     easy account deletion is.

   Weight changes cost nothing to try. New or changed questions need re-extraction for every analyzed
   document: about $5 for the current 45 sites.

## Decisions needed from Sam

- Agree with the split of "sells"? It moves more sites than any weighting choice.
- Are the high-concern and medium-concern lists right? Two open calls in particular:
  - **AI training:** is it high concern, or medium when the site offers an opt-out?
  - **Sharing with advertisers:** 38 of the 45 sites say yes. Is it a red flag, or the norm
    to report without penalty?
- The thresholds: does SEVERE need 2 red flags, or should one of the worst (selling data for money,
  no deletion) be enough?
- Is the minimum of 4 of 6 high-concern questions the right bar for calling a site clean?
- Optional: a 10-minute class survey ranking these practices would give the weights a cited source
  instead of our judgment.
