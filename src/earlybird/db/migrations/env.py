"""Alembic environment. The URL is always supplied by earlybird.db.engine.upgrade."""

from alembic import context
from sqlalchemy import create_engine

from earlybird.db.schema import metadata

url = context.config.get_main_option("sqlalchemy.url")
if url is None:
    raise RuntimeError("sqlalchemy.url must be set; use `earlybird db upgrade`")

connectable = create_engine(url)
with connectable.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()
connectable.dispose()
