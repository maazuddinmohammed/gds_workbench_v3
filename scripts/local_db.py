"""Rebuild the local throwaway database from scratch.

Drops the local database, creates it again, and runs every file in
database/install/ in name order, then every file in database/seed/.
00_preflight.sql runs first and 99_verify_install.sql runs last among the
install files, so every rebuild also checks the install.
It only works on this computer.

1. Start Postgres once (Docker):
       docker run -d --name gds-pg -p 5433:5432 -e POSTGRES_PASSWORD=local postgres:18
2. Rebuild the database whenever you like:
       uv run scripts/local_db.py

Settings (all optional): GDS_LOCAL_HOST, GDS_LOCAL_PORT, GDS_LOCAL_USER,
GDS_LOCAL_PASSWORD, GDS_LOCAL_DB.
"""

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
INSTALL_DIR = ROOT / "database" / "install"
SEED_DIR = ROOT / "database" / "seed"

HOST = os.environ.get("GDS_LOCAL_HOST", "localhost")
PORT = os.environ.get("GDS_LOCAL_PORT", "5433")
USER = os.environ.get("GDS_LOCAL_USER", "postgres")
PASSWORD = os.environ.get("GDS_LOCAL_PASSWORD", "local")
DB = os.environ.get("GDS_LOCAL_DB", "gds_local")


def connect(dbname):
    return psycopg.connect(
        host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=dbname, autocommit=True
    )


def main():
    if HOST not in ("localhost", "127.0.0.1"):
        sys.exit(f"Stopped: {HOST} is not this computer. This script only rebuilds a local database.")

    with connect("postgres") as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB}"')

    # Each file runs as one unit: if any statement fails, nothing from that file is kept.
    with connect(DB) as conn:
        for path in sorted(INSTALL_DIR.glob("*.sql")) + sorted(SEED_DIR.glob("*.sql")):
            print(f"running {path.relative_to(ROOT)}")
            conn.execute(path.read_text())

    print(f"done: database {DB} on {HOST}:{PORT}")


if __name__ == "__main__":
    main()
