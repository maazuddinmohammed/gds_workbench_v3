"""Rebuild the local throwaway database from scratch.

Drops the local database, creates it again, and runs every file in
database/install/ in name order, then every file in database/seed/ and the
starter prompts in database/seed/prompts/, then the demo data in database/demo/ (demo tenants, users, catalog and project, for
trying the apps locally; never sent to Azure).
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
DEMO_DIR = ROOT / "database" / "demo"
PROMPTS_DIR = SEED_DIR / "prompts"

HOST = os.environ.get("GDS_LOCAL_HOST", "localhost")
PORT = os.environ.get("GDS_LOCAL_PORT", "5433")
USER = os.environ.get("GDS_LOCAL_USER", "postgres")
PASSWORD = os.environ.get("GDS_LOCAL_PASSWORD", "local")
DB = os.environ.get("GDS_LOCAL_DB", "gds_local")


def connect(dbname):
    return psycopg.connect(
        host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=dbname, autocommit=True
    )


def run_files(conn, with_demo):
    """Run the install files, then the seed files, then (only if asked) the demo files, in name order.

    Each file runs as one unit: if any statement fails, nothing from that file is kept, and the run stops there.
    scripts/db_install.py uses this too, always without demo data.
    """
    for path in sorted(INSTALL_DIR.glob("*.sql")) + sorted(SEED_DIR.glob("*.sql")):
        print(f"running {path.relative_to(ROOT)}")
        conn.execute(path.read_text())
    load_starter_prompts(conn)
    if with_demo:
        for path in sorted(DEMO_DIR.glob("*.sql")):
            print(f"running {path.relative_to(ROOT)}")
            conn.execute(path.read_text())


def load_starter_prompts(conn):
    """Add the starter prompts in database/seed/prompts/ (see its README): a missing prompt becomes the global
    default, and a text that differs from a prompt's latest version becomes its next version. Safe to run again."""
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        lines = path.read_text().splitlines()
        name, mode = lines[0].removeprefix("# ").strip(), lines[1].removeprefix("mode:").strip()
        text = "\n".join(lines[2:])
        system = text.split("## System", 1)[1].split("## Instruction", 1)[0].strip()
        instruction = text.split("## Instruction", 1)[1].strip()
        conn.execute(
            """INSERT INTO application.prompt (project_workflow, workflow_execution_mode, prompt_name, is_default)
               SELECT %s, %s, %s, NOT EXISTS (SELECT 1 FROM application.prompt WHERE tenant_id IS NULL
                                               AND project_workflow = %s AND workflow_execution_mode = %s AND is_default)
                WHERE NOT EXISTS (SELECT 1 FROM application.prompt
                                   WHERE tenant_id IS NULL AND lower(btrim(prompt_name)) = lower(btrim(%s)))""",
            (path.stem, mode, name, path.stem, mode, name),
        )
        prompt_id, number, *texts = conn.execute(
            """SELECT p.prompt_id, coalesce(v.prompt_version_number, 0), v.system_prompt, v.instruction_prompt
                 FROM application.prompt AS p LEFT JOIN application.prompt_version AS v USING (prompt_id)
                WHERE p.tenant_id IS NULL AND lower(btrim(p.prompt_name)) = lower(btrim(%s))
                ORDER BY v.prompt_version_number DESC NULLS LAST LIMIT 1""",
            (name,),
        ).fetchone()
        if texts != [system, instruction]:
            conn.execute(
                """INSERT INTO application.prompt_version
                       (prompt_id, prompt_version_number, system_prompt, instruction_prompt)
                   VALUES (%s, %s, %s, %s)""",
                (prompt_id, number + 1, system, instruction),
            )
        print(f"prompt {path.relative_to(ROOT)}")


def main(with_demo=True):
    """Rebuild the database. The tests pass with_demo=False: they make their own rows, and a test that needs the
    demo data loads it inside its own transaction."""
    if HOST not in ("localhost", "127.0.0.1"):
        sys.exit(f"Stopped: {HOST} is not this computer. This script only rebuilds a local database.")

    with connect("postgres") as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB}"')

    with connect(DB) as conn:
        run_files(conn, with_demo)

    print(f"done: database {DB} on {HOST}:{PORT}")


if __name__ == "__main__":
    main()
