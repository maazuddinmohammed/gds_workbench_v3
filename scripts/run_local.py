"""Run the web app on this computer against the local database (step 4a3).

    uv run scripts/run_local.py           # use gds_local as it is (builds it first if it does not exist yet)
    uv run scripts/run_local.py --fresh   # rebuild gds_local first: install, seed and demo data

Then open http://127.0.0.1:8000/health. Sign in by sending a demo user's email in the X-Forwarded-Email header,
the way Databricks Apps do; the page (step 4a4) will let you pick one. The server restarts itself when you change
a Python file. Stop it with Ctrl+C.

It listens on 127.0.0.1 only, never on the network: locally anyone who can reach it can claim to be any user by
setting that header, so nobody else may reach it.

Needs the local Postgres running (see scripts/local_db.py). Uses the same GDS_LOCAL_* settings as local_db.py.
"""

import argparse
import os
import subprocess
import sys

import psycopg

import local_db  # scripts/local_db.py, next to this file

DEMO_USERS = ["asha@demo.local (Viewer)", "ben@demo.local (Developer)", "cara@demo.local (Tenant Admin)",
              "sam@demo.local (Super Admin)"]


def database_exists():
    try:
        with local_db.connect("postgres") as conn:
            return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (local_db.DB,)).fetchone() is not None
    except psycopg.OperationalError as error:
        sys.exit(
            f"Cannot reach Postgres on {local_db.HOST}:{local_db.PORT} ({error}).\n"
            "Start it with:  colima start  and then  docker start gds-pg"
        )


def main():
    parser = argparse.ArgumentParser(description="Run the web app locally against gds_local.")
    parser.add_argument("--fresh", action="store_true", help="rebuild the local database first")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.fresh or not database_exists():
        local_db.main()

    env = dict(
        os.environ,
        GDS_WEB_DATABASE_DSN=(
            f"postgresql://{local_db.USER}:{local_db.PASSWORD}@{local_db.HOST}:{local_db.PORT}/{local_db.DB}"
        ),
        GDS_WEB_ENVIRONMENT="local",
    )
    print(f"Web app: http://127.0.0.1:{args.port}  (database {local_db.DB})", flush=True)
    print("Demo users for the X-Forwarded-Email header: " + ", ".join(DEMO_USERS), flush=True)
    command = [sys.executable, "-m", "uvicorn", "web_app.backend.app:app",
               "--host", "127.0.0.1", "--port", str(args.port), "--reload"]
    try:
        subprocess.run(command, env=env, cwd=local_db.ROOT, check=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
