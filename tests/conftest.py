from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.app.config import Settings
from apps.api.app.db import Database, seed_database


@pytest.fixture()
def database(tmp_path: Path) -> Database:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    db = Database(settings=settings, path=tmp_path / "test.db")
    seed_database(db)
    return db

