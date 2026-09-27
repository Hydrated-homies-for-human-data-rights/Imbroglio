# Spike A — Extraction Feasibility Report

**Result: 19/20 privacy policies extracted and validated — gate PASS**
(gate: >= 80% per proposal objective 1)

| Domain | Privacy policy | Terms of service |
| --- | --- | --- |
| google.com | PASS (64,768 chars, link-text, static) | PASS (28,380 chars, link-text, static) |
| facebook.com | PASS (48,232 chars, link-text, playwright) | PASS (32,169 chars, common-path, playwright) |
| amazon.com | PASS (27,219 chars, link-text, static) | PASS (31,900 chars, link-text, static) |
| apple.com | PASS (11,915 chars, link-text, static) | PASS (20,360 chars, link-text, static) |
| microsoft.com | PASS (4,634 chars, link-text, playwright) | PASS (21,247 chars, link-text, playwright) |
| notion.so | PASS (33,375 chars, link-text, static) | FAIL (too short (0 chars < 1500); too short (0 chars < 1500)) |
| ticktick.com | PASS (8,020 chars, link-text, static) | PASS (7,083 chars, link-text, static) |
| duolingo.com | PASS (30,571 chars, link-text, playwright) | PASS (32,875 chars, link-text, playwright) |
| canva.com | FAIL (too short (61 chars < 1500); too short (61 chars < 1500)) | FAIL (too short (61 chars < 1500); too short (61 chars < 1500)) |
| spotify.com | PASS (4,246 chars, link-text, playwright) | FAIL (too short (0 chars < 1500); too short (0 chars < 1500)) |
| dropbox.com | PASS (25,330 chars, link-text, static) | PASS (25,330 chars, link-text, static) |
| figma.com | PASS (55,148 chars, common-path, static) | PASS (36,483 chars, common-path, static) |
| discord.com | PASS (2,081 chars, link-text, static) | PASS (59,424 chars, link-text, static) |
| reddit.com | PASS (5,930 chars, common-path, static) | FAIL (too short (143 chars < 1500); too short (143 chars < 1500)) |
| zoom.us | PASS (53,915 chars, link-text, static) | PASS (87,399 chars, link-text, static) |
| todoist.com | PASS (27,187 chars, link-text, static) | PASS (55,022 chars, link-text, static) |
| obsidian.md | PASS (14,520 chars, link-text, static) | PASS (41,222 chars, link-text, static) |
| raindrop.io | PASS (3,363 chars, link-text, static) | PASS (11,218 chars, link-text, static) |
| standardnotes.com | PASS (3,444 chars, link-text, static) | PASS (8,127 chars, link-text, static) |
| bear.app | PASS (15,403 chars, iframe, static) | PASS (8,459 chars, common-path, static) |

Extracted text is in `results/<domain>/` — manually verify a sample
against the live page (proposal requires manual verification).