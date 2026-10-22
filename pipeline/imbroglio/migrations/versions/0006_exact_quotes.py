"""Data fix: store the document's own words for every verified quote.

Quote verification tolerates a dropped character in long quotes, and until
now the model's copy was stored and shown as-is (facebook.com displayed
"publly perform" for the document's "publicly perform"). New findings store
the exact document text (llm_extract.check_findings); this rewrites the
verified quotes already stored. Unverified quotes are left untouched. No LLM
calls, and only quote text changes, so statuses and scores stay the same.

Revision ID: 0006
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from imbroglio.verify import exact_quotes

    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        """SELECT f.id, f.quotes, f.quotes_verified, v.normalized_text
           FROM findings f JOIN document_versions v ON v.id = f.version_id
           WHERE true = ANY(f.quotes_verified)""").fetchall()
    for fid, quotes, flags, text in rows:
        exact = exact_quotes(list(quotes), text)
        fixed = [e if ok and e is not None else q for q, ok, e in zip(quotes, flags, exact)]
        if fixed != list(quotes):
            conn.exec_driver_sql("UPDATE findings SET quotes = %(q)s WHERE id = %(id)s", {"q": fixed, "id": fid})


def downgrade() -> None:
    pass  # the model's near-miss copies aren't kept; nothing to restore
