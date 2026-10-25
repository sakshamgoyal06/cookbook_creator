"""Family dish requests wait for the buyer's OK (BUILD_PLAN module 12): dish status "requested".

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
OLD = ("wishlist", "in_progress", "done", "skipped")
NEW = ("requested", "wishlist", "in_progress", "done", "skipped")


def _in(column, values):
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade():
    # 0004 named this "ck_dishes_status" under the naming convention, so it exists as ck_dishes_ck_dishes_status.
    with op.batch_alter_table("dishes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("ck_dishes_status", type_="check")
        batch.create_check_constraint("status", _in("status", NEW))


def downgrade():
    op.execute("UPDATE dishes SET status = 'skipped' WHERE status = 'requested'")
    with op.batch_alter_table("dishes", naming_convention=NAMING_CONVENTION) as batch:
        batch.drop_constraint("status", type_="check")
        batch.create_check_constraint("ck_dishes_status", _in("status", OLD))
