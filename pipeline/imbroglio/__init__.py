"""Imbroglio analysis pipeline (working codename).

Module map (mirrors proposal ownership):
    fetch.py      HTTP layer: static fetch + Playwright fallback   (Jaiden)
    locate.py     document discovery escalation ladder             (Jaiden)
    extract.py    HTML -> clean text                               (Jaiden)
    normalize.py  text canonicalization + content hashing          (Jaiden)
    db.py         Postgres storage layer                           (shared)
    analyze.py    orchestrator: domain -> stored document version  (shared)
    cli.py        command-line entrypoint                          (shared)

Later modules plug into analyze.py's pipeline:
    classifier    segment -> OPP-115 categories                    (Gage)
    llm_extract   rubric questions + quote verification            (Gage/Alex)
    scorer        deterministic findings -> category scores        (Sam)
"""

__version__ = "0.1.0"
