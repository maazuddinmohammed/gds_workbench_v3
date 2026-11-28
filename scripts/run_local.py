"""Run the web app and the MCP server on this computer against the local database (steps 4a3, 4a4 and 4b3).

    uv run scripts/run_local.py                 # use gds_local as it is (builds it first if it does not exist yet)
    uv run scripts/run_local.py --fresh         # rebuild gds_local first: install, seed and demo data
    uv run scripts/run_local.py --mcp-user asha # the MCP server signs you in as Asha (default: Ben)

Then open http://127.0.0.1:5173 and pick a demo user in "Signed in as". Three servers run: the web backend on
127.0.0.1:8000, the page's dev server (Vite) on 127.0.0.1:5173, which passes /api calls to the backend, and the MCP
server on 127.0.0.1:8001. All three restart or refresh by themselves when you change a file. Stop them with Ctrl+C.
The first run installs the page's packages (npm ci).

The MCP server runs on http://127.0.0.1:8001/mcp (health: /health/live and /health/ready), signed in as one demo user for every call
(GDS_LOCAL_PRINCIPAL_OBJECT_ID, the made-up IDs in database/demo/01_access.sql).

All listen on 127.0.0.1 only, never on the network: locally anyone who can reach them can claim to be any user, so
nobody else may reach them.

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
MCP_USERS = {"sam": 1, "asha": 2, "ben": 3, "cara": 4}  # the last digit of each demo user's made-up object ID


def openai_key():
    """The OpenAI test key from .env (OPEN_AI_KEY, git-ignored), for Runs on the OpenAI API; empty if there is none."""
    env_file = local_db.ROOT / ".env"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    return next((line.split("=", 1)[1].strip().strip("'\"") for line in lines if line.startswith("OPEN_AI_KEY=")), "")


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
    parser = argparse.ArgumentParser(description="Run the web app and the MCP server locally against gds_local.")
    parser.add_argument("--fresh", action="store_true", help="rebuild the local database first")
    parser.add_argument("--mcp-user", choices=MCP_USERS, default="ben", help="who the MCP server signs you in as")
    args = parser.parse_args()

    if args.fresh or not database_exists():
        local_db.main()
    if not (FRONTEND / "node_modules").exists():
        subprocess.run(["npm", "ci"], cwd=FRONTEND, check=True)

    dsn = f"postgresql://{local_db.USER}:{local_db.PASSWORD}@{local_db.HOST}:{local_db.PORT}/{local_db.DB}"
    env = dict(os.environ, GDS_WEB_DATABASE_DSN=dsn, GDS_WEB_ENVIRONMENT="local", GDS_WEB_OPENAI_API_KEY=openai_key())
    mcp_env = dict(
        os.environ,
        GDS_ENVIRONMENT="local",
        GDS_DATABASE_DSN=dsn,
        GDS_MCP_PUBLIC_URL="http://127.0.0.1:8001/mcp",
        GDS_LOCAL_PRINCIPAL_OBJECT_ID=f"00000000-0000-4000-8000-00000000000{MCP_USERS[args.mcp_user]}",
    )
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "web_app.backend.app:app", "--host", "127.0.0.1", "--port", "8000",
         "--reload", "--reload-dir", "core", "--reload-dir", "web_app/backend"],
        env=env, cwd=local_db.ROOT,
    )
    mcp = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mcp_server.app:app", "--host", "127.0.0.1", "--port", "8001",
         "--reload", "--reload-dir", "core", "--reload-dir", "mcp_server"],
        env=mcp_env, cwd=local_db.ROOT,
    )
    frontend = subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND)
    servers = (backend, mcp, frontend)
    print(f"Open http://127.0.0.1:5173  (database {local_db.DB}). MCP: http://127.0.0.1:8001/mcp as "
          f"{args.mcp_user.title()}. Ctrl+C stops all three servers.", flush=True)
    try:
        while all(server.poll() is None for server in servers):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            if server.poll() is None:
                server.terminate()
        for server in servers:
            server.wait()


if __name__ == "__main__":
    main()
