"""Install GDS Workbench into an empty database you name, for example the new database on Azure Postgres (step 5d).

    PGPASSWORD='...' uv run scripts/db_install.py "host=<server>.postgres.database.azure.com dbname=<new database> user=<admin> sslmode=require"

Runs the install files and the seed files (never the demo data), the same files and order as scripts/local_db.py.
00_preflight.sql stops it unless the database is empty, and 99_verify_install.sql checks the result. It stops at the
first file that fails; that file leaves nothing behind.

The password comes from PGPASSWORD (or ~/.pgpass), so it is never in the command or in a file. Connect as the server's
admin: the install creates the schemas and the app logins (90_roles.sql). If a login is new, set its password
afterwards (see 90_roles.sql). Users, reference and other data are loaded by your own process, not here.
"""

import sys

import psycopg

import local_db  # scripts/local_db.py, next to this file: run_files


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with psycopg.connect(sys.argv[1], autocommit=True) as conn:
        local_db.run_files(conn, with_demo=False)
        print(f"done: installed into database {conn.info.dbname} on {conn.info.host}")


if __name__ == "__main__":
    main()
