"""Running read-only SQL on Databricks, for profiling and samples (design/operations/databricks.md).

One piece of calling code, like core/ai.py: the Databricks SQL Statement Execution API over HTTPS, with Python's own
urllib, so no package is needed. The connection values come from the tenant's data lake connection for an
environment (`core.connection_value`): `databricks_host_name`, `databricks_http_path` and `databricks_token`, as in
v2. A parameter marked `is_key_vault` holds a secret's name, never the secret: the app passes `secret(name)`, which
reads it from its own settings (App Service and Databricks Apps put Key Vault secrets there). core/ never reads
settings itself.

Not tried against a real workspace yet (Nov 28): there is no Databricks locally.
"""

import json
import time
import urllib.request

from psycopg.rows import dict_row

from core.problems import Refused

PARAMETERS = ("databricks_host_name", "databricks_http_path", "databricks_token")
WAIT_SECONDS = 600


def lake_values(conn, tenant_id, environment_code):
    """The Databricks values of the tenant's data lake connection for an environment ({parameter: (value, is_secret)})."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.connection_parameter_code, v.connection_value, p.is_key_vault
                 FROM core.tenant AS t
                 JOIN core.connection_value AS v ON v.connection_id = t.data_lake_connection_id
                 JOIN reference.connection_parameter AS p USING (connection_parameter_id)
                 JOIN reference.environment AS e USING (environment_id)
                WHERE t.tenant_id = %s AND lower(e.environment_code) = lower(%s)""",
            (tenant_id, environment_code),
        )
        values = {r["connection_parameter_code"]: (r["connection_value"], r["is_key_vault"]) for r in cur.fetchall()}
    missing = [p for p in PARAMETERS if not (values.get(p) or (None,))[0]]
    if missing:
        raise Refused("RUN-005", f"The tenant's data lake connection has no {', '.join(missing)} for {environment_code}.")
    return values


def run(values, secret, sql, parameters=None):
    """Run one statement and return its rows as dicts. `parameters` are named (`:b0` in the SQL)."""
    def value(name):
        raw, is_secret = values[name]
        return secret(raw) if is_secret else raw

    host, token = value("databricks_host_name"), value("databricks_token")
    warehouse = value("databricks_http_path").rstrip("/").rsplit("/", 1)[-1]
    body = {"warehouse_id": warehouse, "statement": sql, "wait_timeout": "30s", "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY", "disposition": "INLINE",
            "parameters": [{"name": k, "value": str(v)} for k, v in (parameters or {}).items()]}
    answer = _call(host, token, "POST", "/api/2.0/sql/statements", body)
    waited = 0
    while answer["status"]["state"] in ("PENDING", "RUNNING") and waited < WAIT_SECONDS:
        time.sleep(2)
        waited += 2
        answer = _call(host, token, "GET", f"/api/2.0/sql/statements/{answer['statement_id']}")
    if answer["status"]["state"] != "SUCCEEDED":
        error = answer["status"].get("error", {}).get("message", answer["status"]["state"])
        raise RuntimeError(f"Databricks: {error}")
    names = [c["name"] for c in answer["manifest"]["schema"]["columns"]]
    return [dict(zip(names, row)) for row in answer.get("result", {}).get("data_array") or []]


def _call(host, token, method, path, body=None):
    request = urllib.request.Request(f"https://{host}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())
