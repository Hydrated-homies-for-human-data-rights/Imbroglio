"""Why a site couldn't be rated, in words a reader can act on.

Every miss used to read "We couldn't find a privacy policy or terms". The
crawl already records what happened at each step (Located.notes, stored in
crawl_attempts.notes and in a request's result), so the reason is read back
from those notes rather than tracked separately:

    unreachable  the host didn't answer, or doesn't exist
    blocked      a bot challenge, a CAPTCHA, or "403 Forbidden" turned us away
    pdf_only     the only policy we found is a PDF, which we can't read yet
    timed_out    the time budget ran out before anything usable turned up
    no_policy    we got in and looked, and there was nothing at the usual places
    error        something broke on our side (a failed job, not the site)

Production, Nov 2026: of 652 requested sites, 269 never got a rating; 72 had
no policy at the usual addresses, 68 were behind bot protection, 21 were
unreachable or didn't exist.

A host that doesn't resolve and one that resolves to a private address both
read "unreachable" here, as netguard intends: the public status must not tell
the two apart.
"""

from __future__ import annotations

import re
from typing import Iterable

MESSAGES = {
    "unreachable": "We couldn't reach this site. Check the spelling.",
    "blocked": "This site blocks automated visitors, so we couldn't read its policy.",
    "pdf_only": "This site's policy is a PDF, and we can only read web pages for now.",
    "timed_out": "This site was too slow, and we ran out of time before we found its policy.",
    "no_policy": "We couldn't find a privacy policy or terms on this site.",
    "error": "Something went wrong on our side while we were reading this site.",
}

MAX_TRIED = 8

_BLOCK_STATUS = r"(401|403|429|blocked: bot challenge)"
_CHALLENGE = re.compile(r"bot challenge|captcha", re.I)
# The whole site turned us away: its home page, or a wall that ended the search.
_SITE_BLOCKED = re.compile(rf"^((www )?homepage (static|render) -> {_BLOCK_STATUS}|blocked: (bot challenge|captcha wall))$")
_PDF = re.compile(r"non-html: application/pdf", re.I)
# "<via> <url> -> <status>": one probe and what came of it
_PROBE = re.compile(r"^(?P<via>[\w-]+) (?P<url>https?://\S+) -> (?P<status>.+)$")
_HOME = re.compile(r"^(?P<which>www homepage|homepage) (static|render) -> (?P<status>.+)$")


def split_notes(notes: str | Iterable[str] | None) -> list[str]:
    """Notes as stored (one string joined with '; ') or as a list."""
    if not notes:
        return []
    if isinstance(notes, str):
        return [n.strip() for n in notes.split("; ") if n.strip()]
    out: list[str] = []
    for n in notes:
        out += split_notes(n)
    return out


def classify(notes: str | Iterable[str] | None) -> str:
    """The reason code for a crawl that found nothing, from its notes."""
    lines = split_notes(notes)
    if any(n == "host unreachable" for n in lines):
        return "unreachable"
    if any(_SITE_BLOCKED.match(n) for n in lines):
        return "blocked"
    # Or most of the pages we asked for did, even though the home page loaded.
    probes = [m.group("status") for m in map(_PROBE.match, lines) if m]
    if probes and 2 * sum(1 for s in probes if re.fullmatch(_BLOCK_STATUS, s)) >= len(probes):
        return "blocked"
    if any(_PDF.search(n) for n in lines):
        return "pdf_only"
    if any(n == "time budget exceeded" for n in lines):
        return "timed_out"
    return "no_policy"


def _plain_status(status: str) -> str:
    s = status.strip()
    if s in ("404", "410"):
        return "page not found"
    if s in ("401", "403"):
        return "the site turned us away"
    if s == "429":
        return "the site asked us to slow down"
    if s.isdigit() and s.startswith("5"):
        return "the site had a server error"
    if _CHALLENGE.search(s):
        return "blocked by a bot check"
    if _PDF.search(s):
        return "a PDF, which we can't read yet"
    if s.startswith("200 (non-html"):
        return "not a web page"
    if s.startswith("blocked") or "Connection" in s or "SSL" in s:
        return "couldn't connect"
    if "Timeout" in s:
        return "didn't answer in time"
    if s.startswith("too large"):
        return "too large to read"
    if s.startswith("too short"):
        return "too short to be a policy"
    if s.startswith("no privacy signals"):
        return "didn't read like a privacy policy"
    if s.startswith("no terms signals"):
        return "didn't read like terms of service"
    if s.startswith("another site's document"):
        return "another site's document"
    if s.startswith("summary page"):
        return "a summary that links to the full document"
    if s.startswith("about a side program"):
        return "about a side program, not the main document"
    if s.startswith("isn't the"):
        return s
    if s.startswith("playwright"):
        return "couldn't load it in a browser"
    return "couldn't use it"


def tried(notes: str | Iterable[str] | None, domain: str) -> list[str]:
    """A short plain list of what we tried: 'https://x.com/privacy: page not found'."""
    out: list[str] = []
    seen: set[str] = set()
    for n in split_notes(notes):
        home, probe = _HOME.match(n), _PROBE.match(n)
        if home:
            where = f"https://www.{domain}" if home.group("which") == "www homepage" else f"https://{domain}"
            key, line = where, f"{where} (home page): {_plain_status(home.group('status'))}"
        elif probe:
            key = probe.group("url")
            line = f"{key}: {_plain_status(probe.group('status'))}"
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= MAX_TRIED:
            break
    return out


def describe(notes: str | Iterable[str] | None, domain: str) -> dict:
    reason = classify(notes)
    return {"reason": reason, "message": MESSAGES[reason], "tried": tried(notes, domain)}


def for_request(status: str, result: dict | None, domain: str) -> dict | None:
    """Why a finished request found nothing, or None if it found something
    (or is still running)."""
    if status == "failed":
        return {"reason": "error", "message": MESSAGES["error"], "tried": []}
    if status != "done":
        return None
    docs = (result or {}).get("documents") or []
    if not docs or any(d.get("found") for d in docs):
        return None
    return describe([d.get("notes") or "" for d in docs], domain)


def for_site(conn, domain: str) -> dict | None:
    """Why the site's latest crawl found nothing, from its crawl attempts
    (one row per document type, written together)."""
    rows = conn.execute(
        """SELECT notes FROM crawl_attempts WHERE domain = %s
           ORDER BY attempted_at DESC, id DESC LIMIT 2""", (domain,)).fetchall()
    if not rows:
        return None
    return describe([r[0] or "" for r in rows], domain)
