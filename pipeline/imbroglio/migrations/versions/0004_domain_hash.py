"""Domain hash for privacy-preserving lookups.

Clients (the browser extension) look sites up by a short prefix of
sha256(domain) instead of the domain itself, so the server never learns which
site someone is visiting. The hash is a generated column, so it can never
drift from the domain, and the pattern index makes prefix search fast.
(domain::bytea, not convert_to(): generated columns need an immutable
expression, and the text->bytea cast is; it hashes the UTF-8 bytes, matching
hashlib.sha256(domain.encode()) on the client side.)

Revision ID: 0004
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE services
    ADD COLUMN domain_hash TEXT
    GENERATED ALWAYS AS (encode(sha256(domain::bytea), 'hex')) STORED;
CREATE INDEX idx_services_domain_hash ON services (domain_hash text_pattern_ops);
"""

DOWN = r"""
DROP INDEX IF EXISTS idx_services_domain_hash;
ALTER TABLE services DROP COLUMN domain_hash;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
