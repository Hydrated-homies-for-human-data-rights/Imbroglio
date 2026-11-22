# Chrome Web Store listing

Everything the developer dashboard asks for, in the order it asks. Paste as
written; keep it in step with `extension/README.md` and imbroglio.io/privacy.

## Package

- Upload: `imbroglio-1.1.zip` (build it with `python extension/store/package.py`)
- What's new in this version: `whats-new-1.1.md`

## Store listing

**Name:** Imbroglio (from the manifest)

**Summary** (from the manifest, 132 characters at most):
The privacy rating for the site you're on, from its own privacy policy and terms.

**Description:**

Nobody reads privacy policies. Imbroglio reads them for you.

Click the Imbroglio icon on any website to see how its own privacy policy and terms of service treat your data, rated in seven categories:

• Data selling and sharing
• Collection scope
• Retention and deletion
• User rights
• Security
• AI and model training
• Government requests

Every rating comes from the site's own documents. Each finding is backed by an exact quote from the policy, and our code checks every quote word for word against the stored document before it can count. A model reads the policy and answers fixed questions; published rules, not the model, turn those answers into a rating. The method is open: imbroglio.io/how-we-score.

What you get:
• The site's overall rating on the toolbar icon as you browse, and its score out of 100 in the popup
• The biggest flags, and all seven categories at a glance
• What you can do about each flag, with a button straight to the site's own opt-out or settings page when it has one
• An optional one-time warning on sites rated Extensive or Severe
• An optional alert when a site you've visited changes its policy

Private by design:
• No account, no sign-in
• No ads, no analytics, no tracking
• The extension never sends the name of the site you're on. It sends only the first three characters of a SHA-256 hash of it, which many sites share, and finds the right answer on your own computer
• On a subdomain we haven't rated, such as mail.example.com, it sends one more three-character prefix, for example.com, so the main site's rating can show. Never more than two
• Nothing is sent for localhost, IP addresses or names on your own network
• What it remembers stays in your browser, filed under a key only your browser holds. Recent lookups are kept in memory for up to ten minutes and cleared when the browser closes

Imbroglio is free and open source, built as a senior capstone project at Metropolitan State University of Denver. Ratings describe what the documents say, not a company's intentions, and are not legal advice.

**Category:** Privacy & Security (if offered; otherwise Tools)

**Language:** English

**Graphic assets** (all in this folder, made by `make_assets.py`):
- Store icon 128x128: `store-icon-128.png` (the toolbar icon with the 16px transparent margin Google asks for)
- Screenshots 1280x800, in this order: `screenshot-1-overview.png`, `screenshot-2-breakdown.png`, `screenshot-3-actions.png`, `screenshot-4-moderate.png`
- Small promo tile 440x280: `promo-small-440x280.png`
- Marquee promo tile 1400x560: `promo-marquee-1400x560.png` (optional; only shown if Google features the extension)

**Official URL:** None (it lists only sites verified in Google Search Console; can be added later)

**Homepage URL:** https://imbroglio.io

**Support URL:** https://imbroglio.io/report

## Privacy practices

**Single purpose:**
Show the privacy rating of the website in the current tab, made from that website's own privacy policy and terms of service, and link to the full report on imbroglio.io.

**Permission justifications:**

- `tabs`: To know which website each tab is showing, so the toolbar icon can show that site's rating as you browse and the popup can show the rating for the site you're on. The extension reads only the tab's address (its host name), never page content.
- `notifications`: For two optional, one-time alerts the user can turn off in the popup: a warning the first time they visit a site rated Extensive or Severe, and a notice when a site they have visited changes its privacy policy or terms.
- `storage`: To remember the user's two alert settings and, for those alerts, when it last warned about a site and the last policy change it saw there. Stored locally under a keyed hash, never the site's name. Recent lookup results are also kept in session storage (memory only, cleared when the browser closes) so switching tabs doesn't repeat them.
- Host permission `https://imbroglio.io/*`: The extension's only server. It fetches ratings from imbroglio.io's read-only lookup endpoint, sending a 3-character hash prefix, not the site's name. A subdomain with no rating of its own takes a second 3-character prefix, for its main domain; never more than two per site.

**Remote code:** No, I am not using remote code. (All JavaScript is in the package; the extension only fetches JSON data.)

**Data usage** (check what applies):
- Web history: **Yes, check it.** To rate the current tab the extension reads its host name and sends a 3-character prefix of the name's SHA-256 hash to imbroglio.io (and, for an unrated subdomain, a second one for its main domain). That is far coarser than the address, but it is derived from the sites you visit, so declare it rather than argue the point with a reviewer.
- Everything else (personally identifiable information, health, financial, authentication, personal communications, location, user activity, website content): **No.**

**Certifications** (all three are true; check them):
- I do not sell or transfer user data to third parties, apart from the approved use cases
- I do not use or transfer user data for purposes that are unrelated to my item's single purpose
- I do not use or transfer user data to determine creditworthiness or for lending purposes

**Privacy policy URL:** https://imbroglio.io/privacy

## Distribution

- Visibility: Public (or Unlisted for a quiet first week; anyone with the link can still install it)
- Regions: all
- Price: free

## After approval

- Opera: users can install it from the Chrome Web Store (Opera's "Install Chrome Extensions" add-on).
- Edge: the same zip can go to Microsoft Edge Add-ons (free developer account).
