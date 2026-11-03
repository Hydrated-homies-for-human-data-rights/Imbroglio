"""The site's own opt-out and settings pages (links.py), harvested from the
homepage and policy pages the pipeline fetches, so the website and the
extension can put the site's own page next to a finding instead of a
generic step. Replaced whole on every harvest of a site.

Revision ID: 0009
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UP = r"""
CREATE TABLE site_links (
    id          SERIAL PRIMARY KEY,
    service_id  INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,      -- privacy_choices | ad_preferences | cookie_settings | ...
    category    TEXT NOT NULL,      -- rubric category the link answers
    url         TEXT NOT NULL,
    text        TEXT NOT NULL,      -- the link's own words, as found
    source      TEXT NOT NULL,      -- homepage | privacy | terms
    seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (service_id, url)
);

CREATE INDEX idx_site_links_service ON site_links (service_id);
"""

DOWN = "DROP TABLE IF EXISTS site_links;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWN)
