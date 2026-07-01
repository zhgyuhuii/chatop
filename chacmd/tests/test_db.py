import pytest
from sqlalchemy import text

from chacmd.interfaces.db import Database


@pytest.mark.asyncio
async def test_database_runs_query_on_any_dialect():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    async with db.session() as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await db.dispose()


def test_dialect_name_is_not_hardcoded():
    # I2 must expose the dialect so callers never assume postgres.
    db = Database(url="sqlite+aiosqlite:///:memory:")
    assert db.dialect == "sqlite"
