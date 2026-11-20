"""The policy link a visitor gave with a request.

The website asks people to paste a link to a site's policy when we couldn't
find one, but the request only kept the domain, so the link was thrown away.
It is now kept on the request and handed to discovery as the first page to
try (locate.same_site_link checks it is on the same site). Requests without
a link leave it empty.

Revision ID: 0012
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE analysis_requests ADD COLUMN policy_url TEXT;
"""

DOWN = """
ALTER TABLE analysis_requests DROP COLUMN IF EXISTS policy_url;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
