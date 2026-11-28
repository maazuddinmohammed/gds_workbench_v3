"""Profiling: measuring the scope tables' columns on Databricks with queries the server writes, no AI
(design/operations/databricks.md, as in v2).

A profiling Run measures each picked table (every active scope table if none is picked): one aggregate query per 50
columns (row count, non-null, distinct, blank, lengths), and when the project may store samples, one query for the
most common values of every column. A table with a batch column is measured only on the Run's batch IDs, and the Run
is refused when such a table is picked without them. The profiles go into a draft that the Run applies itself:
they are measurements, not proposals. If that Apply is refused, the Run fails with the reason and keeps the draft.
"""

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core import blocks, change_sets, databricks
from core.access import CHANGE, require
from core.enrichment import picked_tables
from core.problems import NotFound, Refused
from core.runs import finish, log, run_003, run_005

COLUMNS_PER_QUERY = 50
STRING = ("string", "varchar", "char", "text")
NO_DISTINCT = ("array", "map", "struct", "binary", "variant")


def quote(name):
    return f"`{name.replace('`', '``')}`"


def relation(catalog, table):
    return ".".join(quote(p) for p in (catalog, table["object_schema"], table["object_name"]))


def batch_filter(table, batch_ids):
    """The WHERE of a batched table, with named parameters :b0, :b1, ..., or "" for a table measured whole."""
    if not table["batch_attribute_name"]:
        return "", {}
    params = {f"b{i}": b for i, b in enumerate(batch_ids)}
    return f" WHERE {quote(table['batch_attribute_name'])} IN ({', '.join(':' + k for k in params)})", params


def aggregate_queries(catalog, table, columns, batch_ids):
    """One query per 50 columns, each giving one row: the row count and every column's counts and lengths."""
    where, params = batch_filter(table, batch_ids)
    for start in range(0, len(columns), COLUMNS_PER_QUERY):
        parts, chunk = ["COUNT(*) AS row_count"], columns[start:start + COLUMNS_PER_QUERY]
        for i, c in enumerate(chunk):
            q, kind = quote(c["attribute_name"]), c["attribute_data_type"].lower()
            parts.append(f"COUNT({q}) AS c{i}_non_null")
            if not kind.startswith(NO_DISTINCT):
                parts.append(f"COUNT(DISTINCT {q}) AS c{i}_distinct")
            if kind.startswith(STRING):
                parts += [f"SUM(CASE WHEN TRIM({q}) = '' THEN 1 ELSE 0 END) AS c{i}_blank",
                          f"MIN(LENGTH({q})) AS c{i}_min_length", f"MAX(LENGTH({q})) AS c{i}_max_length",
                          f"AVG(LENGTH({q})) AS c{i}_avg_length"]
        yield chunk, f"SELECT {', '.join(parts)} FROM {relation(catalog, table)}{where}", params


def sample_query(catalog, table, columns, batch_ids, size):
    """The most common non-empty values of every column, `size` each, most common first."""
    where, params = batch_filter(table, batch_ids)
    picks = " UNION ALL ".join(
        f"SELECT {i} AS c, CAST({quote(c['attribute_name'])} AS STRING) AS v FROM scoped" for i, c in enumerate(columns))
    sql = (f"WITH scoped AS (SELECT * FROM {relation(catalog, table)}{where}) "
           f"SELECT c, v, count(*) AS n FROM ({picks}) WHERE v IS NOT NULL AND TRIM(v) <> '' GROUP BY c, v "
           f"QUALIFY ROW_NUMBER() OVER (PARTITION BY c ORDER BY count(*) DESC, v) <= {int(size)} ORDER BY c, n DESC")
    return sql, params


def profile_records(table, columns, rows_by_chunk, samples):
    """The attribute_profile records of one table, from the aggregate rows (and samples, if any)."""
    records = []
    for chunk, row in rows_by_chunk:
        total = int(row["row_count"])
        for i, c in enumerate(chunk):
            non_null = int(row[f"c{i}_non_null"])
            distinct = row.get(f"c{i}_distinct")
            blank = row.get(f"c{i}_blank")
            pct = lambda part, whole: round(100.0 * part / whole, 4) if whole else 0.0  # noqa: E731
            record = {"object_schema": table["object_schema"], "object_name": table["object_name"],
                      "attribute_name": c["attribute_name"], "row_count": total, "non_null_count": non_null,
                      "null_count": total - non_null, "blank_count": None if blank is None else int(blank),
                      "distinct_count": None if distinct is None else int(distinct),
                      "min_data_length": row.get(f"c{i}_min_length"), "max_data_length": row.get(f"c{i}_max_length"),
                      "avg_data_length": row.get(f"c{i}_avg_length"),
                      "percent_populated": pct(non_null, total), "percent_null": pct(total - non_null, total),
                      "percent_blank": None if blank is None else pct(int(blank), non_null),
                      "percent_distinct": None if distinct is None else pct(int(distinct), non_null),
                      "percent_duplicates": None if distinct is None else pct(non_null - int(distinct), non_null),
                      "is_active": True}
            if samples is not None:
                record["sample_values"] = samples.get(c["attribute_name"], [])
            records.append(record)
    return records


def start_run(conn, principal_id, project_id, request, via_mcp=False):
    """Check and save a profiling Run (RUN-003, RUN-005): `request` has `tables` (optional), `batch_ids` and
    `environment_code` (dev if left out). Returns the Run's id; `execute` does the work."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM project.project WHERE project_id = %s AND is_active", (project_id,))
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        require(conn, principal_id, project["tenant_id"], CHANGE, project_id=project_id, via_mcp=via_mcp)
        request = {"environment_code": "dev", "batch_ids": []} | (request or {})
        with conn.transaction():
            run_003(cur, project["tenant_id"])
            tables = picked_tables(cur, project_id, request)
            batched = [f"{t['object_schema']}.{t['object_name']}" for t in tables if t["batch_attribute_name"]]
            run_005(batched and not request["batch_ids"] and f"{', '.join(batched[:5])} have a batch column: give the "
                                                              "batch IDs to measure.")
            run_005(len(request["batch_ids"]) > 2000 and "Give at most 2000 batch IDs.")
            cur.execute(
                """INSERT INTO application.run (tenant_id, project_id, project_workflow, base_project_version,
                                                run_request_document, started_by_principal_id)
                   SELECT tenant_id, project_id, 'profiling', project_version, %s, %s FROM project.project
                    WHERE project_id = %s RETURNING run_id""",
                (Jsonb(request), principal_id, project_id),
            )
            run_id = cur.fetchone()["run_id"]
            log(cur, run_id, "start", "completed", f"Profiling {len(tables)} tables in {request['environment_code']}.")
    return run_id


def execute(conn, run_id, secret):
    """Measure every picked table, then save the profiles as a draft and apply it."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT r.*, t.tenant_catalog FROM application.run AS r JOIN core.tenant AS t USING (tenant_id) "
                    "WHERE r.run_id = %s", (run_id,))
        run = cur.fetchone()
        request = run["run_request_document"]
        try:
            values = databricks.lake_values(conn, run["tenant_id"], request["environment_code"])
            cur.execute("SELECT is_sample_storage_allowed, sample_size FROM project.project_config WHERE project_id = %s",
                        (run["project_id"],))
            config = cur.fetchone() or {"is_sample_storage_allowed": False, "sample_size": 5}
            tables = picked_tables(cur, run["project_id"], request)
            records = []
            for done, table in enumerate(tables, 1):
                columns = blocks.columns(cur, run["project_id"], table["object_id"])
                rows = [(chunk, databricks.run(values, secret, sql, params)[0])
                        for chunk, sql, params in aggregate_queries(run["tenant_catalog"], table, columns, request["batch_ids"])]
                samples = None
                if config["is_sample_storage_allowed"]:
                    sql, params = sample_query(run["tenant_catalog"], table, columns, request["batch_ids"], config["sample_size"])
                    samples = {}
                    for r in databricks.run(values, secret, sql, params):
                        samples.setdefault(columns[int(r["c"])]["attribute_name"], []).append(r["v"])
                records += profile_records(table, columns, rows, samples)
                log(cur, run_id, "profile", "completed", f"Profiled {done} of {len(tables)} tables.")
        except (Refused, RuntimeError, OSError, ValueError) as error:
            finish(cur, run_id, "failed", message=str(error))
            return
        change_set_id = change_sets.save_draft(conn, run["project_id"], run["started_by_principal_id"],
                                               {"attribute_profile": records}, f"Profiling: run {run_id}", "ai_run",
                                               run["base_project_version"])
        try:
            problems = change_sets.apply(conn, run["started_by_principal_id"], change_set_id)
        except Refused as refusal:
            problems = [refusal]
        if problems:
            finish(cur, run_id, "failed", message=f"Draft {change_set_id} was not applied: {problems[0]}. Apply or "
                                                   "reject it by hand.")
            return
        finish(cur, run_id, "completed", change_set_id)
