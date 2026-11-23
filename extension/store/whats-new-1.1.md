# What's new in 1.1

For the store submission (the dashboard's notes for this version). Plain
text, paste as written.

---

Imbroglio 1.1 fixes the policy change alert and sends less when you browse subdomains.

• Policy change alerts now work for every rated site you visit. Before, a site with no change on record when you first visited it never alerted you, even after its policy changed.
• Fewer lookups on subdomains. A subdomain is looked up as itself, and only if it has no rating of its own does the extension ask about its main domain. That is two three-character prefixes at most, down from three.
• An unrated subdomain no longer hides the main site's rating.
• Names on your own network, like nas.local or router.lan, are no longer looked up. For those, localhost and IP addresses, the popup now says there is nothing to rate instead of offering a "request it" button.
• Lookups give up after eight seconds, and when imbroglio.io asks the extension to slow down, it waits as long as asked before trying again.
• The toolbar icon no longer shows a rating for a page you have already left.
• Recent results are kept in memory while the browser is open, so the icon doesn't look up the same site again after Chrome pauses the extension.

No new permissions.
