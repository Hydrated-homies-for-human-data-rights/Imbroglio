"""Chrome Web Store images, made from the real popup with live ratings.

    pipeline/.venv/Scripts/python.exe extension/store/make_assets.py

Loads extension/popup.html in a headless browser with the chrome.* calls it
makes stubbed out, feeds it the same data background.js would build from a
real imbroglio.io lookup, and photographs its three screens. Writes:

    store/screenshot-1-overview.png       1280x800 (popup at 360x540, shown 1.4x)
    store/screenshot-2-breakdown.png      1280x800
    store/screenshot-3-actions.png        1280x800
    store/screenshot-4-moderate.png       1280x800
    store/promo-small-440x280.png         the store's small promo tile
    store/promo-marquee-1400x560.png      the store's marquee promo tile
    store/store-icon-128.png              icons/icon128.png at 96x96 with the 16px
                                          transparent margin the store asks for

Not part of the extension package (see store/README.md).
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

STORE = Path(__file__).resolve().parent
EXT = STORE.parent
API = "https://imbroglio.io/api/v1/lookup/"


def site_data(domain: str) -> dict:
    """What background.js's toSiteData() hands the popup, from a live lookup."""
    h = hashlib.sha256(domain.encode()).hexdigest()
    req = urllib.request.Request(API + h[:5], headers={"Accept": "application/json",
                                                       "User-Agent": "imbroglio-store-assets"})
    entry = next(s for s in json.load(urllib.request.urlopen(req))["sites"] if s["hash"] == h)
    s = entry["scores"]
    return {
        "status": "ready", "domain": domain, "hash": h, "headline": s["headline"], "score": s.get("score"),
        "categories": [{"key": c["key"], "name": c["name"], "tier": c["tier"], "findings": c["findings"]}
                       for c in s["categories"]],
        "analyzedAt": s["analyzed_at"], "changedAt": entry.get("changed_at"), "rubric": s["rubric_version"],
        "scorer": s["scorer_version"], "documents": entry["documents"], "links": entry.get("links") or [],
    }


STUB = """
window.chrome = {
  runtime: { lastError: undefined, sendMessage: (msg, cb) => setTimeout(() => cb({ data: window.__DATA__ }), 0) },
  tabs: { query: async () => [{ url: "https://www." + window.__DATA__.domain + "/", favIconUrl: "" }],
          create: () => {} },
  storage: { local: { get: async () => ({ warnExtensive: true, policyChanges: true }), set: async () => {} } },
};
"""

FRAME = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:1280px;height:800px;overflow:hidden}
body{background:#f79ac0;font-family:Inter,system-ui,"Segoe UI",sans-serif;color:#321e28;display:flex;align-items:center;gap:72px;padding:0 96px;box-sizing:border-box}
.copy{flex:1}
.copy h1{font-size:52px;line-height:1.05;letter-spacing:-.02em;margin:0 0 20px}
.copy p{font-size:22px;line-height:1.45;margin:0;max-width:20em;color:#3d2833}
.shot{width:504px;height:756px;border-radius:22px;overflow:hidden;box-shadow:0 30px 70px -30px rgba(50,30,40,.55);background:#fff;flex:none}
.shot img{width:504px;height:756px;display:block}
</style></head><body><div class="copy"><h1>{title}</h1><p>{text}</p></div>
<div class="shot"><img src="{img}"></div></body></html>"""

PROMO = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:440px;height:280px;overflow:hidden}
body{background:#f79ac0;color:#321e28;font-family:Inter,system-ui,"Segoe UI",sans-serif;display:flex;flex-direction:column;justify-content:center;padding:0 36px;box-sizing:border-box}
.word{display:flex;align-items:flex-end;font-size:50px;font-weight:800;letter-spacing:-.02em;line-height:1;margin:0 0 14px}
.word svg{height:52px;width:auto;margin-right:1px;color:#321e28}
.word b{color:#c0392b}
p{font-size:19px;line-height:1.35;margin:0;max-width:15em}
</style></head><body><div class="word"><svg viewBox="380 160 270 670" aria-hidden="true"><circle cx="544" cy="260" r="92" fill="#c0392b"/><path fill="currentColor" d="M450 398C478 382 530 378 560 402C588 425 585 465 565 505L492 632C478 658 485 690 510 705C527 715 545 715 560 710L583 795C555 815 525 823 497 822C450 821 410 800 393 760C378 723 385 670 405 630L478 492C492 465 485 448 470 440C460 434 446 432 436 433Z"/></svg><span>mbroglio<b>.</b></span></div>
<p>The privacy rating for the site you’re on, from its own policy.</p></body></html>"""

MARQUEE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:1400px;height:560px;overflow:hidden}
body{background:#f79ac0;color:#321e28;font-family:Inter,system-ui,"Segoe UI",sans-serif;display:flex;align-items:center;gap:80px;padding:0 120px;box-sizing:border-box}
.copy{flex:1}
.word{display:flex;align-items:flex-end;font-size:96px;font-weight:800;letter-spacing:-.02em;line-height:1;margin:0 0 28px}
.word svg{height:100px;width:auto;margin-right:2px;color:#321e28}
.word b{color:#c0392b}
p{font-size:30px;line-height:1.35;margin:0;max-width:17em;color:#3d2833}
.shot{width:336px;height:504px;border-radius:18px;overflow:hidden;box-shadow:0 26px 60px -26px rgba(50,30,40,.55);background:#fff;flex:none}
.shot img{width:336px;height:504px;display:block}
</style></head><body><div class="copy"><div class="word"><svg viewBox="380 160 270 670" aria-hidden="true"><circle cx="544" cy="260" r="92" fill="#c0392b"/><path fill="currentColor" d="M450 398C478 382 530 378 560 402C588 425 585 465 565 505L492 632C478 658 485 690 510 705C527 715 545 715 560 710L583 795C555 815 525 823 497 822C450 821 410 800 393 760C378 723 385 670 405 630L478 492C492 465 485 448 470 440C460 434 446 432 436 433Z"/></svg><span>mbroglio<b>.</b></span></div>
<p>The privacy rating for the site you’re on, read from its own privacy policy and terms of service.</p></div>
<div class="shot"><img src="{img}"></div></body></html>"""

SHOTS = [
    ("screenshot-1-overview.png", "spotify.com", [],
     "Know what you’re agreeing to.",
     "The rating for the site you’re on, read from its own privacy policy and terms of service."),
    ("screenshot-2-breakdown.png", "spotify.com", ["#see-all"],
     "The same seven categories, every site.",
     "Data selling, collection, retention, your rights, security, AI training and government requests."),
    ("screenshot-3-actions.png", "spotify.com", ["#see-all", "[data-go=actions]"],
     "Then decide what to do.",
     "Where a site offers its own opt-out or settings page, the button takes you straight there."),
    ("screenshot-4-moderate.png", "duckduckgo.com", [],
     "It never sends where you are.",
     "Only three characters of a scrambled site name per lookup leave your browser. No account, no tracking."),
]


def main():
    data = {d: site_data(d) for d in {s[1] for s in SHOTS}}
    shots = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, domain, clicks, title, text in SHOTS:
            pg = b.new_page(viewport={"width": 360, "height": 540}, device_scale_factor=1.4)  # popup.css --width/--height
            pg.add_init_script(f"window.__DATA__ = {json.dumps(data[domain])};" + STUB)
            pg.goto((EXT / "popup.html").as_uri())
            pg.wait_for_timeout(800)
            for sel in clicks:
                pg.click(sel)
                pg.wait_for_timeout(1200)  # let the slide transition finish
            pg.evaluate("for (const el of [document.scrollingElement, ...document.querySelectorAll('*')]) "
                        "if (el && el.scrollTop) el.scrollTop = 0")
            pg.wait_for_timeout(300)
            png = pg.screenshot()
            pg.close()
            uri = "data:image/png;base64," + base64.b64encode(png).decode()
            shots[name] = uri
            fr = b.new_page(viewport={"width": 1280, "height": 800})
            fr.set_content(FRAME.replace("{title}", title).replace("{text}", text).replace("{img}", uri))
            fr.wait_for_timeout(300)
            fr.screenshot(path=str(STORE / name))
            fr.close()
            print("wrote", name)
        pr = b.new_page(viewport={"width": 440, "height": 280})
        pr.set_content(PROMO)
        pr.screenshot(path=str(STORE / "promo-small-440x280.png"))
        print("wrote promo-small-440x280.png")
        mq = b.new_page(viewport={"width": 1400, "height": 560})
        mq.set_content(MARQUEE.replace("{img}", shots["screenshot-1-overview.png"]))
        mq.wait_for_timeout(300)
        mq.screenshot(path=str(STORE / "promo-marquee-1400x560.png"))
        print("wrote promo-marquee-1400x560.png")
        icon = "data:image/png;base64," + base64.b64encode((EXT / "icons" / "icon128.png").read_bytes()).decode()
        ic = b.new_page(viewport={"width": 128, "height": 128})
        ic.set_content('<html><body style="margin:0;background:transparent">'
                       f'<img src="{icon}" style="display:block;width:96px;height:96px;margin:16px"></body></html>')
        ic.screenshot(path=str(STORE / "store-icon-128.png"), omit_background=True)
        print("wrote store-icon-128.png")
        b.close()


if __name__ == "__main__":
    main()
