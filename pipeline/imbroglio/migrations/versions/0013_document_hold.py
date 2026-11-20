"""A hold on a stored document that is the wrong page.

Discovery sometimes stores the wrong page as a site's policy or terms (a
promo help article as Coinbase's terms, a copyright page as usu.edu's). Until
now the only fix was deleting it. held_reason marks it instead: the text
stays, but a held document is left out of every public answer, is never
rated, and isn't rechecked. NULL is a normal document; text is why a person
held it (cli hold / unhold / held).

valid_from is set when a hold is lifted by storing a different page: versions
fetched before it are the wrong page, so they never count again, even the
ones that were rated.

Revision ID: 0013
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE documents ADD COLUMN held_reason TEXT;
ALTER TABLE documents ADD COLUMN valid_from TIMESTAMPTZ;
"""

DOWN = """
ALTER TABLE documents DROP COLUMN IF EXISTS held_reason;
ALTER TABLE documents DROP COLUMN IF EXISTS valid_from;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
