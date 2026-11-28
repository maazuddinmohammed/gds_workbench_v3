"""How things go into a prompt, and the one piece of code that describes a table (design/shared/table-details.md).

Four formats (design/overview/run.md): **rows** (a line of field names, then one line per row, fields split by `|`),
**blocks** (a `table` or `entity` line in JSON, then its columns or attributes as rows), **JSON** and **text**.
Lists are always sorted the same way, so the provider can cache the part of a prompt that repeats. An empty input is
the word `none`. Things are named by the database's column names, never by id.
"""

import json

SAMPLE_CHARS = 60  # samples are cut at 60 characters
NONE = "none"


def value(v):
    """One field in a row: text as it is (JSON-quoted when it holds a | or a line break), the rest as JSON."""
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False) if "|" in v or "\n" in v else v
    return json.dumps(v, ensure_ascii=False, default=str)


def rows(records, fields):
    if not records:
        return NONE
    return "\n".join(["|".join(fields)] + ["|".join(value(r.get(f)) for f in fields) for r in records])


def block(kind, head, records, fields):
    """One table or entity: its `kind` line in JSON, then its columns or attributes as rows."""
    line = f"{kind} {json.dumps(head, ensure_ascii=False, default=str)}"
    return line + "\n" + rows(records, fields) if records else line


def as_json(data):
    return json.dumps(data, ensure_ascii=False, default=str) if data else NONE


def samples(sample_values, is_pii):
    """Most common first, cut at 60 characters, never for a column marked as personal data."""
    if is_pii or not sample_values:
        return []
    return [str(s)[:SAMPLE_CHARS] for s in sample_values]


# --- The project's scope tables, with what the prompts need to know about each --------------------------------------

SCOPE_TABLES = """
SELECT o.object_id, o.object_schema, o.object_name, o.batch_attribute_name,
       coalesce(src_sys.system_code, sys.system_code) AS system_code,
       (SELECT max(p.row_count) FROM workflow.attribute_profile AS p
         WHERE p.project_id = s.project_id AND p.object_id = o.object_id AND p.is_active) AS row_count,
       (SELECT count(*) FROM core.attribute AS a WHERE a.object_id = o.object_id AND a.is_active) AS column_count,
       e.object_definition, e.object_grain, coalesce(e.is_locked, FALSE) AS enrichment_is_locked
  FROM project.project_input_scope AS s
  JOIN core.object AS o USING (object_id)
  JOIN core.connection AS c ON c.connection_id = o.connection_id
  JOIN core.system AS sys ON sys.system_id = c.system_id
  LEFT JOIN LATERAL (  -- a Bronze copy takes its source's system (ingestion lineage), as Python only uses it for that
       SELECT ss.system_code FROM core.ingestion_object_mapping AS m
         JOIN core.object AS so ON so.object_id = m.source_object_id
         JOIN core.connection AS sc ON sc.connection_id = so.connection_id
         JOIN core.system AS ss ON ss.system_id = sc.system_id
        WHERE m.target_object_id = o.object_id AND m.is_active
        ORDER BY m.ingestion_object_mapping_id LIMIT 1) AS src_sys ON TRUE
  LEFT JOIN workflow.object_enrichment AS e ON e.project_id = s.project_id AND e.object_id = o.object_id AND e.is_active
 WHERE s.project_id = %(project_id)s AND s.is_active AND o.is_active
 ORDER BY lower(o.object_schema), lower(o.object_name)"""


def scope_tables(cur, project_id):
    """The project's active scope tables, by schema and name, each with its system, row count, column count, and the
    project's definition and Grain."""
    cur.execute(SCOPE_TABLES, {"project_id": project_id})
    return cur.fetchall()


COLUMNS = """
SELECT a.attribute_id, a.attribute_name, a.attribute_data_type, a.attribute_ordinal_position, a.is_meta_data,
       p.row_count, p.null_count, p.blank_count, p.distinct_count, p.min_data_length, p.max_data_length,
       p.sample_values, e.attribute_definition, e.attribute_inferred_data_type, e.is_natural_key, e.is_surrogate_key,
       e.is_foreign_key_candidate, e.is_nullable, e.is_pii, coalesce(e.is_locked, FALSE) AS is_locked
  FROM core.attribute AS a
  LEFT JOIN workflow.attribute_profile AS p
    ON p.project_id = %(project_id)s AND p.attribute_id = a.attribute_id AND p.is_active
  LEFT JOIN workflow.attribute_enrichment AS e
    ON e.project_id = %(project_id)s AND e.attribute_id = a.attribute_id AND e.is_active
 WHERE a.object_id = %(object_id)s AND a.is_active
 ORDER BY a.attribute_ordinal_position"""


def columns(cur, project_id, object_id):
    """A table's active columns with their profile, the project's enrichment and samples (cut, never for is_pii)."""
    cur.execute(COLUMNS, {"project_id": project_id, "object_id": object_id})
    found = cur.fetchall()
    for col in found:
        col["sample_values"] = samples(col["sample_values"], col["is_pii"])
    return found


def systems(cur, project_id, system_codes):
    """The `systems` input: the project's tenant, and the systems named."""
    cur.execute(
        """SELECT t.tenant_code, t.tenant_name, t.tenant_description FROM project.project AS p
             JOIN core.tenant AS t USING (tenant_id) WHERE p.project_id = %s""",
        (project_id,),
    )
    tenant = cur.fetchone()
    cur.execute(
        """SELECT system_code, system_name, system_description FROM core.system
            WHERE system_code = ANY(%s) ORDER BY system_code""",
        (sorted(set(system_codes)),),
    )
    return as_json({"tenant": dict(tenant), "systems": [dict(s) for s in cur.fetchall()]})
