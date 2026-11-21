"""Test setup: a throwaway database just for tests, rebuilt once per test run.

The tests use their own database, `gds_test`, on the same local Postgres as `scripts/local_db.py`, so running
them never touches your `gds_local` database. Each test runs inside a transaction that is rolled back at the
end, so tests never see each other's rows.
"""

import importlib.util
import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent

os.environ["GDS_LOCAL_DB"] = "gds_test"
_spec = importlib.util.spec_from_file_location("local_db", ROOT / "scripts" / "local_db.py")
local_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(local_db)


@pytest.fixture(scope="session")
def test_database():
    """Rebuild the test database (install + seed) once for the whole run."""
    local_db.main()
    return local_db.DB


@pytest.fixture
def conn(test_database):
    """A connection whose changes are thrown away after the test."""
    with psycopg.connect(
        host=local_db.HOST,
        port=local_db.PORT,
        user=local_db.USER,
        password=local_db.PASSWORD,
        dbname=test_database,
    ) as connection:
        yield connection
        connection.rollback()
