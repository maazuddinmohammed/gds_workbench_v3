"""Run the web app on this computer against the local database (steps 4a3 and 4a4).

    uv run scripts/run_local.py           # use gds_local as it is (builds it first if it does not exist yet)
    uv run scripts/run_local.py --fresh   # rebuild gds_local first: install, seed and demo data

Then open http://127.0.0.1:5173 and pick a demo user in "Signed in as". Two servers run: the web backend on
127.0.0.1:8000 and the page's dev server (Vite) on 127.0.0.1:5173, which passes /api calls to the backend. Both
restart or refresh by themselves when you change a file. Stop them with Ctrl+C. The first run installs the page's
packages (npm ci).

Both listen on 127.0.0.1 only, never on the network: locally anyone who can reach them can claim to be any user by
setting the sign-in header, so nobody else may reach them.

Needs the local Postgres running (see scripts/local_db.py). Uses the same GDS_LOCAL_* settings as local_db.py.
"""

import argparse
import os
import subprocess
import sys
import time

import psycopg

import local_db  # scripts/local_db.py, next to this file

FRONTEND = local_db.ROOT / "web_app" / "frontend"


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
    args = parser.parse_args()

    if args.fresh or not database_exists():
        local_db.main()
    if not (FRONTEND / "node_modules").exists():
        subprocess.run(["npm", "ci"], cwd=FRONTEND, check=True)

    env = dict(
        os.environ,
        GDS_WEB_DATABASE_DSN=(
            f"postgresql://{local_db.USER}:{local_db.PASSWORD}@{local_db.HOST}:{local_db.PORT}/{local_db.DB}"
        ),
        GDS_WEB_ENVIRONMENT="local",
    )
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web_app.backend.app:app", "--host", "127.0.0.1", "--port", "8000",
         "--reload", "--reload-dir", "core", "--reload-dir", "web_app/backend"],
        env=env, cwd=local_db.ROOT,
    )
    frontend = subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND)
    print(f"Open http://127.0.0.1:5173  (database {local_db.DB}). Ctrl+C stops both servers.", flush=True)
    try:
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for server in (backend, frontend):
            if server.poll() is None:
                server.terminate()
        for server in (backend, frontend):
            server.wait()


if __name__ == "__main__":
    main()
