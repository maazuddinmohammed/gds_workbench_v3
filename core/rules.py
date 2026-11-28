"""The rules a draft is checked against once its records are saved (docs/rules/), one function per rule ID.

`core/change_sets.py` saves a draft's records on the project, then calls `check`: each rule reads the project as it
would be after Apply and returns (part, row id, message) for every row that breaks it. A rule runs only when the draft
has records in one of the parts it is about (RULE_PARTS), so a draft that takes a table out of scope is stopped if a
subject area still uses it, while an enrichment draft is not held up by a model rule. A problem names the record that
touched the row, when one did.

The checks on the whole draft and on each record (CHANGE-SET-001, 002, 003, 005, 012 and 013) are in
core/change_sets.py, next to the code that reads the records.
"""

import re

import sqlglot
from sqlglot import exp

from core.catalog import is_scope_tenant, is_scope_zone
from core.problems import Problem

# Values that come from a fixed list (CHANGE-SET-012). Entity type codes come from reference.operational_entity_type.
LISTS = {
    "relationship_kind": ("foreign_key", "extension", "same_business_key", "same_code_list"),
    "inferred_cardinality": ("one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"),
    "dimensional_entity_type": ("fact", "dimension"),
    "validation_category_code": ("completeness", "referential", "transformation", "business_rule", "reconciliation"),
    "validation_severity": ("blocking", "warning", "informational"),
}

WARNINGS = {"SUBJECT-AREA-002", "OPERATIONAL-008", "OPERATIONAL-009", "DIMENSIONAL-008", "DIMENSIONAL-009",
            "DIMENSIONAL-010", "MAPPING-003", "CODE-001", "CODE-003", "CODE-004", "VALIDATION-002"}


def check(cur, project_id, parts, touched):
    """Every problem the rules find on the project as it is now, for a draft with records in `parts`.

    `touched` maps (part, row id) to the draft's record that saved that row.
    """
    problems = []
    for rule, rule_parts in RULE_PARTS.items():
        if not parts & set(rule_parts):
            continue
        rule_id = rule.__name__.upper().replace("_", "-")
        level = "warning" if rule_id in WARNINGS else "blocks_apply"
        for part, row_id, message in rule(cur, project_id):
            problems.append(Problem(rule_id, message, touched.get((part, row_id)), part, level))
    return problems


def _rows(cur, sql, project_id, **params):
    cur.execute(sql, {"project_id": project_id, **params})
    return cur.fetchall()


# --- Scope (docs/rules/scope.md) ------------------------------------------------------------------------------------

SCOPE_ROWS = """SELECT s.project_input_scope_id AS id, o.object_schema, o.object_name, o.object_id,
                       lower(btrim(z.zone_code)) AS zone_code, z.zone_name, st.tenant_id AS source_tenant_id,
                       st.tenant_name AS source_tenant_name, st.tenant_visibility, p.tenant_id AS project_tenant_id
                  FROM project.project_input_scope AS s JOIN project.project AS p USING (project_id)
                  JOIN core.object AS o ON o.object_id = s.object_id
                  JOIN reference.zone AS z ON z.zone_id = o.zone_id
                  JOIN core.tenant AS st ON st.tenant_id = o.source_tenant_id
                 WHERE s.project_id = %(project_id)s AND s.is_active"""


def scope_001(cur, project_id):
    """SCOPE-001: only Source and Bronze tables can be in scope."""
    return [("project_input_scope", r["id"], f"{r['object_schema']}.{r['object_name']} is in zone {r['zone_name']}; "
                                             "only Source and Bronze can be in scope.")
            for r in _rows(cur, SCOPE_ROWS, project_id) if not is_scope_zone(r["zone_code"])]


def scope_002(cur, project_id):
    """SCOPE-002: a scope table belongs to the project's tenant or to a global tenant."""
    return [("project_input_scope", r["id"], f"{r['object_schema']}.{r['object_name']} belongs to "
                                             f"{r['source_tenant_name']}, which is private to another tenant.")
            for r in _rows(cur, SCOPE_ROWS, project_id)
            if not is_scope_tenant(r["source_tenant_id"], r["tenant_visibility"], r["project_tenant_id"])]


def scope_005(cur, project_id):
    """SCOPE-005: no two scope tables share a schema and name, ignoring case."""
    seen, found = {}, []
    for r in _rows(cur, SCOPE_ROWS + " ORDER BY s.project_input_scope_id", project_id):
        name = (r["object_schema"].strip().lower(), r["object_name"].strip().lower())
        if name in seen:
            found.append(("project_input_scope", r["id"], f"{r['object_schema']}.{r['object_name']} is in scope "
                                                          "twice, from two connections. Keep one of them."))
        seen[name] = r["id"]
    return found


# --- Enrichment and relationships (docs/rules/analysis.md) ------------------------------------------------------

IN_SCOPE = """EXISTS (SELECT 1 FROM project.project_input_scope AS s JOIN core.object AS o USING (object_id)
                       WHERE s.project_id = %(project_id)s AND s.object_id = {object} AND s.is_active AND o.is_active)"""
ACTIVE_COLUMN = "EXISTS (SELECT 1 FROM core.attribute AS a WHERE a.attribute_id = {column} AND a.is_active)"


def enrichment_001(cur, project_id):
    """ENRICHMENT-001: enrichment is for active scope tables and their active columns."""
    found = [("object_enrichment", r["id"], f"{r['name']} is not an active table in scope.") for r in _rows(cur, f"""
        SELECT e.object_enrichment_id AS id, o.object_schema || '.' || o.object_name AS name
          FROM workflow.object_enrichment AS e JOIN core.object AS o USING (object_id)
         WHERE e.project_id = %(project_id)s AND e.is_active AND NOT {IN_SCOPE.format(object="e.object_id")}""",
        project_id)]
    found += [("attribute_enrichment", r["id"], f"{r['name']} is not an active column of a table in scope.")
              for r in _rows(cur, f"""
        SELECT e.attribute_enrichment_id AS id, o.object_schema || '.' || o.object_name || '.' || a.attribute_name AS name
          FROM workflow.attribute_enrichment AS e JOIN core.object AS o USING (object_id)
          JOIN core.attribute AS a ON a.attribute_id = e.attribute_id
         WHERE e.project_id = %(project_id)s AND e.is_active
           AND NOT ({IN_SCOPE.format(object="e.object_id")} AND {ACTIVE_COLUMN.format(column="e.attribute_id")})""",
        project_id)]
    return found


LINKS = """SELECT r.analysis_result_id AS id, r.from_attribute_id, r.to_attribute_id, r.from_object_id, r.to_object_id,
                  fo.object_schema || '.' || fo.object_name || '.' || fa.attribute_name AS from_name,
                  tobj.object_schema || '.' || tobj.object_name || '.' || ta.attribute_name AS to_name
             FROM workflow.analysis_result AS r
             JOIN core.object AS fo ON fo.object_id = r.from_object_id
             JOIN core.attribute AS fa ON fa.attribute_id = r.from_attribute_id
             JOIN core.object AS tobj ON tobj.object_id = r.to_object_id
             JOIN core.attribute AS ta ON ta.attribute_id = r.to_attribute_id
            WHERE r.project_id = %(project_id)s AND r.is_active"""


def relationship_001(cur, project_id):
    """RELATIONSHIP-001: both ends of a link are active columns of active scope tables (and different columns, which
    the database already keeps: ck_analysis_result_different)."""
    return [("analysis_result", r["id"], f"{r['from_name']} -> {r['to_name']}: an end is not an active column of a "
                                         "table in scope.") for r in _rows(cur, f"""
        SELECT * FROM ({LINKS}) AS l
         WHERE NOT ({IN_SCOPE.format(object="l.from_object_id")} AND {IN_SCOPE.format(object="l.to_object_id")}
                    AND {ACTIVE_COLUMN.format(column="l.from_attribute_id")}
                    AND {ACTIVE_COLUMN.format(column="l.to_attribute_id")})""", project_id)]


def relationship_002(cur, project_id):
    """RELATIONSHIP-002: two columns are linked at most once, in either direction."""
    rows = _rows(cur, LINKS, project_id)
    pairs = {(r["from_attribute_id"], r["to_attribute_id"]) for r in rows}
    return [("analysis_result", r["id"], f"{r['from_name']} -> {r['to_name']} is also linked the other way round. "
                                         "Keep one of the two.")
            for r in rows if (r["to_attribute_id"], r["from_attribute_id"]) in pairs]


# --- Subject areas (docs/rules/subject-areas.md) -------------------------------------------------------------------


def subject_area_001(cur, project_id):
    """SUBJECT-AREA-001: every table of an active area is an active table in scope."""
    return [("subject_area_table", r["id"], f"{r['name']} is in area {r['subject_area_name']} but not in scope.")
            for r in _rows(cur, f"""
        SELECT t.subject_area_table_id AS id, a.subject_area_name, o.object_schema || '.' || o.object_name AS name
          FROM workflow.subject_area_table AS t JOIN workflow.subject_area AS a USING (subject_area_id)
          JOIN core.object AS o ON o.object_id = t.object_id
         WHERE a.project_id = %(project_id)s AND a.is_active AND t.is_active
           AND NOT {IN_SCOPE.format(object="t.object_id")}""", project_id)]


def subject_area_002(cur, project_id):
    """SUBJECT-AREA-002 (warning): every active scope table is in an active area; a table in no area is not modeled."""
    return [("project_input_scope", r["id"], f"{r['object_schema']}.{r['object_name']} is in no subject area, so no "
                                             "model Run will use it.")
            for r in _rows(cur, SCOPE_ROWS + """ AND NOT EXISTS (
                SELECT 1 FROM workflow.subject_area_table AS t JOIN workflow.subject_area AS a USING (subject_area_id)
                 WHERE a.project_id = s.project_id AND a.is_active AND t.is_active AND t.object_id = s.object_id)""",
                           project_id)]


# --- Silver and Gold models (docs/rules/operational-model.md, dimensional-model.md, project-settings.md) -----------
# Silver and Gold have the same shape, so each pair of rules shares one check; `m` is the model's column prefix.

DATABRICKS_TYPE = re.compile(
    r"^(STRING|VARCHAR\(\d+\)|CHAR\(\d+\)|BOOLEAN|TINYINT|SMALLINT|INT|INTEGER|BIGINT|FLOAT|DOUBLE|DATE|TIMESTAMP|"
    r"TIMESTAMP_NTZ|BINARY|DECIMAL(\(\d+(,\s*\d+)?\))?|ARRAY<.+>|MAP<.+>|STRUCT<.+>)$", re.IGNORECASE)


def _entities(m):
    return f"""SELECT e.{m}_entity_id AS id, e.{m}_entity_schema_name || '.' || e.{m}_entity_name AS name,
                      e.{m}_entity_schema_name AS schema_name, e.{m}_entity_dependency_order AS load_order
                 FROM workflow.{m}_entity AS e WHERE e.project_id = %(project_id)s AND e.is_active"""


def _attributes(m):
    return f"""SELECT a.{m}_attribute_id AS id, e.{m}_entity_id AS entity_id, a.{m}_attribute_name AS attribute,
                      e.{m}_entity_schema_name || '.' || e.{m}_entity_name || '.' || a.{m}_attribute_name AS name,
                      a.{m}_attribute_data_type AS data_type, a.is_surrogate_key, a.is_natural_key
                 FROM workflow.{m}_attribute AS a JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                WHERE e.project_id = %(project_id)s AND e.is_active AND a.is_active"""


def _sources_in_scope(cur, project_id):
    return [("operational_entity_source", r["id"], f"{r['name']} is built from {r['source']}, which is not an active "
                                                   "table in scope.") for r in _rows(cur, f"""
        SELECT s.operational_entity_source_id AS id, e.name, o.object_schema || '.' || o.object_name AS source
          FROM workflow.operational_entity_source AS s JOIN ({_entities('operational')}) AS e ON e.id = s.operational_entity_id
          JOIN core.object AS o ON o.object_id = s.object_id
         WHERE s.is_active AND NOT {IN_SCOPE.format(object="s.object_id")}""", project_id)]


def _column_from_entity_sources(cur, project_id, m):
    if m == "operational":
        source_of_column = """(SELECT a.object_id FROM core.attribute AS a WHERE a.attribute_id = s.attribute_id)"""
        sources = "SELECT es.object_id FROM workflow.operational_entity_source AS es"
        column = "(SELECT c.attribute_name FROM core.attribute AS c WHERE c.attribute_id = s.attribute_id)"
    else:
        source_of_column = """(SELECT oa.operational_entity_id FROM workflow.operational_attribute AS oa
                                WHERE oa.operational_attribute_id = s.operational_attribute_id)"""
        sources = "SELECT es.operational_entity_id FROM workflow.dimensional_entity_source AS es"
        column = """(SELECT oa.operational_attribute_name FROM workflow.operational_attribute AS oa
                      WHERE oa.operational_attribute_id = s.operational_attribute_id)"""
    return [(f"{m}_attribute_source", r["id"], f"{r['name']} is fed by {r['column']}, which is not in one of its "
                                               "entity's sources.") for r in _rows(cur, f"""
        SELECT s.{m}_attribute_source_id AS id, a.name, {column} AS column
          FROM workflow.{m}_attribute_source AS s JOIN ({_attributes(m)}) AS a ON a.id = s.{m}_attribute_id
         WHERE s.is_active AND {source_of_column} NOT IN (
               {sources} WHERE es.{m}_entity_id = a.entity_id AND es.is_active)""", project_id)]


def _active_parents(cur, project_id, m):
    return [(f"{m}_link", r["id"], f"{r['name']} links to {r['parent']}, which is switched off.") for r in _rows(cur, f"""
        SELECT l.{m}_link_id AS id, a.name, p.{m}_entity_schema_name || '.' || p.{m}_entity_name AS parent
          FROM workflow.{m}_link AS l JOIN ({_attributes(m)}) AS a ON a.id = l.{m}_attribute_id
          JOIN workflow.{m}_entity AS p ON p.{m}_entity_id = l.parent_{m}_entity_id
         WHERE l.is_active AND NOT (p.is_active AND p.project_id = %(project_id)s)""", project_id)]


def _schemas(cur, project_id, m):
    cur.execute(f"SELECT {m}_schemas AS s FROM project.project_config WHERE project_id = %s", (project_id,))
    row = cur.fetchone()
    allowed = {s["schema_name"].strip().lower() for s in (row["s"] if row else [])}
    return [(f"{m}_entity", r["id"], f"{r['name']}: schema {r['schema_name']} is not one of the project's "
                                     f"{'Silver' if m == 'operational' else 'Gold'} schemas.")
            for r in _rows(cur, _entities(m), project_id) if r["schema_name"].strip().lower() not in allowed]


def _one_surrogate_key(cur, project_id, m):
    found = []
    for r in _rows(cur, f"""
        SELECT e.id, e.name, count(a.id) FILTER (WHERE a.is_surrogate_key) AS keys,
               count(a.id) FILTER (WHERE a.is_surrogate_key AND (
                   EXISTS (SELECT 1 FROM workflow.{m}_attribute_source AS s WHERE s.{m}_attribute_id = a.id AND s.is_active)
                   OR EXISTS (SELECT 1 FROM workflow.{m}_link AS l WHERE l.{m}_attribute_id = a.id AND l.is_active))) AS fed
          FROM ({_entities(m)}) AS e LEFT JOIN ({_attributes(m)}) AS a ON a.entity_id = e.id
         GROUP BY e.id, e.name""", project_id):
        if r["keys"] != 1:
            found.append((f"{m}_entity", r["id"], f"{r['name']} has {r['keys']} surrogate keys; it needs exactly one."))
        elif r["fed"]:
            found.append((f"{m}_entity", r["id"], f"{r['name']}'s surrogate key has a source or a link; the load "
                                                  "fills it, so it has neither."))
    return found


def _natural_key(cur, project_id, m):
    return [(f"{m}_entity", r["id"], f"{r['name']} has no natural key: mark the source's identifier.")
            for r in _rows(cur, f"""SELECT e.id, e.name FROM ({_entities(m)}) AS e WHERE NOT EXISTS (
                                     SELECT 1 FROM ({_attributes(m)}) AS a WHERE a.entity_id = e.id AND a.is_natural_key)""",
                           project_id)]


def _no_audit_names(cur, project_id, m):
    cur.execute(f"SELECT {m}_audit_columns AS c FROM project.project_config WHERE project_id = %s", (project_id,))
    row = cur.fetchone()
    audit = {c["name"].strip().lower() for c in ((row or {}).get("c") or [])}
    return [(f"{m}_attribute", r["id"], f"{r['name']} is named like an audit column the load adds.")
            for r in _rows(cur, _attributes(m), project_id) if r["attribute"].strip().lower() in audit]


def _databricks_types(cur, project_id, m):
    return [(f"{m}_attribute", r["id"], f"{r['name']}: {r['data_type']} is not a Databricks type.")
            for r in _rows(cur, _attributes(m), project_id) if not DATABRICKS_TYPE.match(r["data_type"].strip())]


def _parents_load_first(cur, project_id, m):
    return [(f"{m}_entity", r["id"], f"{r['name']} loads at {r['child_order']}, before its parent {r['parent']} "
                                     f"({r['parent_order']}).") for r in _rows(cur, f"""
        SELECT DISTINCT c.id, c.name, c.load_order AS child_order, p.name AS parent, p.load_order AS parent_order
          FROM workflow.{m}_link AS l JOIN ({_attributes(m)}) AS a ON a.id = l.{m}_attribute_id
          JOIN ({_entities(m)}) AS c ON c.id = a.entity_id
          JOIN ({_entities(m)}) AS p ON p.id = l.parent_{m}_entity_id
         WHERE l.is_active AND c.id <> p.id AND c.load_order IS NOT NULL AND p.load_order IS NOT NULL
           AND p.load_order > c.load_order""", project_id)]


def project_001(cur, project_id):
    """PROJECT-001: scope, Silver and Gold schemas never share a name (ignoring case)."""
    cur.execute("SELECT operational_schemas, dimensional_schemas FROM project.project_config WHERE project_id = %s",
                (project_id,))
    row = cur.fetchone() or {}
    silver = {s["schema_name"].strip().lower() for s in row.get("operational_schemas") or []}
    gold = {s["schema_name"].strip().lower() for s in row.get("dimensional_schemas") or []}
    found = [("operational_entity", None, f"Schema {s} is both a Silver and a Gold schema.") for s in sorted(silver & gold)]
    found += [("project_input_scope", r["id"], f"{r['object_schema']}.{r['object_name']} is in schema "
                                               f"{r['object_schema']}, which is also a Silver or Gold schema.")
              for r in _rows(cur, SCOPE_ROWS, project_id) if r["object_schema"].strip().lower() in silver | gold]
    return found


def operational_001(cur, project_id):
    """OPERATIONAL-001: an entity's source table is an active table in the project's scope."""
    return _sources_in_scope(cur, project_id)


def operational_002(cur, project_id):
    """OPERATIONAL-002: an attribute's source column comes from one of its entity's source tables."""
    return _column_from_entity_sources(cur, project_id, "operational")


def operational_003(cur, project_id):
    """OPERATIONAL-003: a link's parent is an active entity of the same project."""
    return _active_parents(cur, project_id, "operational")


def operational_004(cur, project_id):
    """OPERATIONAL-004: an entity's schema is one of the project's Silver schemas."""
    return _schemas(cur, project_id, "operational")


def operational_005(cur, project_id):
    """OPERATIONAL-005: an entity has exactly one surrogate key, with no source and no link."""
    return _one_surrogate_key(cur, project_id, "operational")


def operational_006(cur, project_id):
    """OPERATIONAL-006: an entity has a natural key."""
    return _natural_key(cur, project_id, "operational")


def operational_007(cur, project_id):
    """OPERATIONAL-007: no attribute has an audit column's name."""
    return _no_audit_names(cur, project_id, "operational")


def operational_008(cur, project_id):
    """OPERATIONAL-008 (warning): an attribute's type is a valid Databricks type."""
    return _databricks_types(cur, project_id, "operational")


def operational_009(cur, project_id):
    """OPERATIONAL-009 (warning): a parent entity loads before its children."""
    return _parents_load_first(cur, project_id, "operational")


def dimensional_001(cur, project_id):
    """DIMENSIONAL-001: an entity's source is an operational entity of the same project."""
    return [("dimensional_entity_source", r["id"], f"{r['name']} is built from an entity of another project.")
            for r in _rows(cur, f"""
        SELECT s.dimensional_entity_source_id AS id, e.name
          FROM workflow.dimensional_entity_source AS s JOIN ({_entities('dimensional')}) AS e ON e.id = s.dimensional_entity_id
          JOIN workflow.operational_entity AS o USING (operational_entity_id)
         WHERE s.is_active AND o.project_id <> %(project_id)s""", project_id)]


def dimensional_002(cur, project_id):
    """DIMENSIONAL-002: an attribute's source comes from one of its entity's source entities."""
    return _column_from_entity_sources(cur, project_id, "dimensional")


def dimensional_003(cur, project_id):
    """DIMENSIONAL-003: a link's parent is an active entity of the same project."""
    return _active_parents(cur, project_id, "dimensional")


def dimensional_004(cur, project_id):
    """DIMENSIONAL-004: an entity's schema is one of the project's Gold schemas."""
    return _schemas(cur, project_id, "dimensional")


def dimensional_005(cur, project_id):
    """DIMENSIONAL-005: an entity has exactly one surrogate key, with no source and no link."""
    return _one_surrogate_key(cur, project_id, "dimensional")


def dimensional_006(cur, project_id):
    """DIMENSIONAL-006: an entity has a natural key."""
    return _natural_key(cur, project_id, "dimensional")


def dimensional_007(cur, project_id):
    """DIMENSIONAL-007: no attribute has an audit column's name (history columns included)."""
    return _no_audit_names(cur, project_id, "dimensional")


def dimensional_008(cur, project_id):
    """DIMENSIONAL-008 (warning): a Gold source points at active Silver rows."""
    found = [("dimensional_entity_source", r["id"], f"{r['name']} is built from {r['source']}, which is switched off.")
             for r in _rows(cur, f"""
        SELECT s.dimensional_entity_source_id AS id, e.name, o.operational_entity_name AS source
          FROM workflow.dimensional_entity_source AS s JOIN ({_entities('dimensional')}) AS e ON e.id = s.dimensional_entity_id
          JOIN workflow.operational_entity AS o USING (operational_entity_id)
         WHERE s.is_active AND NOT o.is_active""", project_id)]
    found += [("dimensional_attribute_source", r["id"], f"{r['name']} is fed by {r['source']}, which is switched off.")
              for r in _rows(cur, f"""
        SELECT s.dimensional_attribute_source_id AS id, a.name, o.operational_attribute_name AS source
          FROM workflow.dimensional_attribute_source AS s JOIN ({_attributes('dimensional')}) AS a ON a.id = s.dimensional_attribute_id
          JOIN workflow.operational_attribute AS o USING (operational_attribute_id)
          JOIN workflow.operational_entity AS oe ON oe.operational_entity_id = o.operational_entity_id
         WHERE s.is_active AND NOT (o.is_active AND oe.is_active)""", project_id)]
    return found


def dimensional_009(cur, project_id):
    """DIMENSIONAL-009 (warning): an attribute's type is a valid Databricks type."""
    return _databricks_types(cur, project_id, "dimensional")


def dimensional_010(cur, project_id):
    """DIMENSIONAL-010 (warning): a dimension loads before the facts that point at it."""
    return _parents_load_first(cur, project_id, "dimensional")


def _model_parts(m):
    return tuple(f"{m}_{p}" for p in ("entity", "attribute", "entity_source", "attribute_source", "link"))


# --- Mapping, code and validation (docs/rules/mapping.md, code.md, validation.md) --------------------------------


def _mappings(m):
    return f"""SELECT x.{m}_object_mapping_id AS id, e.{m}_entity_id AS entity_id,
                      e.{m}_entity_schema_name || '.' || e.{m}_entity_name || ' / ' || s.system_code AS name,
                      x.{m}_object_mapping_tables AS tables
                 FROM workflow.{m}_object_mapping AS x JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                 JOIN core.system AS s ON s.system_id = x.system_id
                WHERE e.project_id = %(project_id)s AND e.is_active AND x.is_active"""


def _line_for_own_attribute(cur, project_id, m):
    return [(f"{m}_attribute_mapping", r["id"], f"{r['name']}: the line is for an attribute of another entity.")
            for r in _rows(cur, f"""
        SELECT l.{m}_attribute_mapping_id AS id, x.name FROM workflow.{m}_attribute_mapping AS l
          JOIN ({_mappings(m)}) AS x ON x.id = l.{m}_object_mapping_id
          JOIN workflow.{m}_attribute AS a ON a.{m}_attribute_id = l.{m}_attribute_id
         WHERE l.is_active AND a.{m}_entity_id <> x.entity_id""", project_id)]


def _table_list(cur, project_id, m):
    scope = {(r["object_schema"].lower(), r["object_name"].lower()) for r in _rows(cur, SCOPE_ROWS, project_id)}
    entities = {em: {tuple(n.lower() for n in r["name"].split(".", 1)) for r in _rows(cur, _entities(em), project_id)}
                for em in ("operational", "dimensional")}
    found = []
    for r in _rows(cur, _mappings(m), project_id):
        aliases = [i.get("alias") for i in r["tables"] or []]
        for i in r["tables"] or []:
            if "object_name" in i:
                ok = (i["object_schema"].lower(), i["object_name"].lower()) in scope
            else:
                em = "operational" if "operational_entity_name" in i else "dimensional"
                ok = (i[f"{em}_entity_schema_name"].lower(), i[f"{em}_entity_name"].lower()) in entities[em]
            if not ok:
                found.append((f"{m}_object_mapping", r["id"], f"{r['name']}: {i} is not an active table in scope or "
                                                              "an active entity."))
        doubles = sorted({a for a in aliases if aliases.count(a) > 1})
        if doubles:
            found.append((f"{m}_object_mapping", r["id"], f"{r['name']}: alias {', '.join(map(str, doubles))} is used twice."))
    return found


def _every_attribute_has_a_line(cur, project_id, m):
    return [(f"{m}_object_mapping", r["id"], f"{r['name']}: {r['attribute']} has no mapping line.")
            for r in _rows(cur, f"""
        SELECT x.id, x.name, a.{m}_attribute_name AS attribute
          FROM ({_mappings(m)}) AS x JOIN workflow.{m}_attribute AS a ON a.{m}_entity_id = x.entity_id
         WHERE a.is_active AND NOT a.is_surrogate_key AND NOT EXISTS (
               SELECT 1 FROM workflow.{m}_attribute_mapping AS l
                WHERE l.{m}_object_mapping_id = x.id AND l.{m}_attribute_id = a.{m}_attribute_id AND l.is_active)""",
                           project_id)]


def _code_files(m):
    return f"""SELECT c.{m}_code_id AS id, e.{m}_entity_id AS entity_id, c.{m}_file_name AS file_name,
                      e.{m}_entity_schema_name || '.' || e.{m}_entity_name || ' ' || c.{m}_file_name AS name,
                      c.{m}_code_text AS sql
                 FROM workflow.{m}_code AS c JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                WHERE e.project_id = %(project_id)s AND e.is_active AND c.is_active"""


def _one_file_per_system(cur, project_id, m):
    return [(f"{m}_code_system", r["id"], f"{r['entity']}: {r['system_code']} is in {r['files']} code files.")
            for r in _rows(cur, f"""
        SELECT min(cs.{m}_code_system_id) AS id, e.{m}_entity_name AS entity, s.system_code, count(*) AS files
          FROM workflow.{m}_code_system AS cs JOIN ({_code_files(m)}) AS c ON c.id = cs.{m}_code_id
          JOIN workflow.{m}_entity AS e ON e.{m}_entity_id = c.entity_id JOIN core.system AS s USING (system_id)
         WHERE cs.is_active GROUP BY e.{m}_entity_name, s.system_code HAVING count(*) > 1""", project_id)]


def read_only(sql, views_allowed):
    """What is wrong with SQL that must only read: None when it is temporary views (if allowed) and one final SELECT
    that parse as Databricks SQL."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="databricks") if s is not None]
    except sqlglot.errors.ParseError as error:
        return f"it does not parse as Databricks SQL ({str(error).splitlines()[0]})"
    if not statements or not isinstance(statements[-1], (exp.Select, exp.Union)):
        return "it does not end with one SELECT"
    for s in statements[:-1]:
        temporary = isinstance(s, exp.Create) and s.args.get("kind") == "VIEW" and s.find(exp.TemporaryProperty)
        if not (views_allowed and temporary):
            return "it holds a statement that is not a temporary view"
    return None


def _code_reads(cur, project_id, m):
    found = [(f"{m}_code", r["id"], f"{r['name']}: {problem}.") for r in _rows(cur, _code_files(m), project_id)
             if (problem := read_only(r["sql"], views_allowed=True))]
    found += [(f"{m}_validation_check", r["id"], f"{r['name']}: {problem}.") for r in _rows(cur, _checks(m), project_id)
              if (problem := read_only(r["validation_query_sql"], views_allowed=False))]
    return found


def _final_select_columns(cur, project_id, m):
    found = []
    for r in _rows(cur, _code_files(m), project_id):
        if read_only(r["sql"], views_allowed=True):
            continue  # CODE-002 says what is wrong
        final = sqlglot.parse(r["sql"], read="databricks")[-1]
        names = [s.lower() for s in final.named_selects]
        cur.execute(f"""SELECT {m}_attribute_name AS name FROM workflow.{m}_attribute
                         WHERE {m}_entity_id = %s AND is_active AND NOT is_surrogate_key""", (r["entity_id"],))
        missing = [a["name"] for a in cur.fetchall() if a["name"].lower() not in names]
        if missing:
            found.append((f"{m}_code", r["id"], f"{r['name']}: the final SELECT leaves out {', '.join(missing)}."))
        if not names or names[-1] != "sourcesystemid":
            found.append((f"{m}_code", r["id"], f"{r['name']}: SourceSystemID is not the last column."))
    return found


def _not_mapped(cur, project_id, m):
    return [(f"{m}_code", r["id"], f"{r['name']}: {', '.join(cols)} left as NOT MAPPED.")
            for r in _rows(cur, _code_files(m), project_id)
            if (cols := re.findall(r"AS\s+(\w+),?\s*--\s*NOT MAPPED", r["sql"], re.IGNORECASE))]


def _checks(m):
    return f"""SELECT c.{m}_validation_check_id AS id, g.{m}_entity_id AS entity_id, g.system_id,
                      e.{m}_entity_name || ' / ' || c.{m}_validation_check_name AS name, c.validation_query_sql,
                      c.validation_comparison_query_sql, c.validation_result_data_type, c.validation_comparison_operator,
                      c.validation_comparison_value_type, c.validation_comparison_value
                 FROM workflow.{m}_validation_check AS c JOIN workflow.{m}_validation_group AS g USING ({m}_validation_group_id)
                 JOIN workflow.{m}_entity AS e ON e.{m}_entity_id = g.{m}_entity_id
                WHERE g.project_id = %(project_id)s AND g.is_active AND c.is_active"""


NO_VALUE = ("executes_successfully", "is_null", "is_not_null", "is_true", "is_false")


def _pass_condition(cur, project_id, m):
    found = []
    for r in _rows(cur, _checks(m), project_id):
        op, kind, value = r["validation_comparison_operator"], r["validation_comparison_value_type"], r["validation_comparison_value"]
        wrong = None
        if op in NO_VALUE and kind != "none":
            wrong = f"{op} needs no value"
        elif op not in NO_VALUE and kind == "none":
            wrong = f"{op} needs a value"
        elif op in ("in", "not_in") and kind not in ("literal_list", "query"):
            wrong = f"{op} needs a list of values"
        elif kind == "literal_list" and not isinstance(value, list):
            wrong = "a literal_list needs a list"
        elif kind == "literal" and (value is None or isinstance(value, list)):
            wrong = "a literal needs one value"
        elif kind == "query" and not r["validation_comparison_query_sql"]:
            wrong = "value type query needs a comparison query"
        if wrong:
            found.append((f"{m}_validation_check", r["id"], f"{r['name']}: {wrong}."))
    return found


def _reads_its_tables(cur, project_id, m):
    found = []
    for r in _rows(cur, _checks(m), project_id):
        try:
            tables = {t.sql(dialect="databricks").split(" ")[0].lower()
                      for t in sqlglot.parse_one(r["validation_query_sql"], read="databricks").find_all(exp.Table)}
        except sqlglot.errors.ParseError:
            continue  # CODE-002 says it
        cur.execute(f"""SELECT x.{m}_object_mapping_tables AS tables, e.{m}_entity_schema_name AS s, e.{m}_entity_name AS n
                          FROM workflow.{m}_object_mapping AS x JOIN workflow.{m}_entity AS e USING ({m}_entity_id)
                         WHERE x.{m}_entity_id = %s AND x.system_id = %s""", (r["entity_id"], r["system_id"]))
        mapping = cur.fetchone()
        if mapping is None:
            continue
        target = f"{mapping['s']}.{mapping['n']}".lower()
        allowed = {target, "meta.system"}
        for i in mapping["tables"] or []:
            schema = i.get("object_schema") or i.get("operational_entity_schema_name") or i.get("dimensional_entity_schema_name")
            name = i.get("object_name") or i.get("operational_entity_name") or i.get("dimensional_entity_name")
            allowed.add(f"{schema}.{name}".lower())
        named = {t for t in tables if "." in t}
        if target not in named:
            found.append((f"{m}_validation_check", r["id"], f"{r['name']}: the query does not read the loaded table {target}."))
        if named - allowed:
            found.append((f"{m}_validation_check", r["id"], f"{r['name']}: the query reads {', '.join(sorted(named - allowed))}, "
                                                            "outside the mapping's tables."))
    return found


def mapping_001(cur, project_id):
    """MAPPING-001: a mapping line is for an attribute of the mapping's own entity."""
    return _line_for_own_attribute(cur, project_id, "operational") + _line_for_own_attribute(cur, project_id, "dimensional")


def mapping_002(cur, project_id):
    """MAPPING-002: a mapping's table list names active scope tables or active entities, each alias once."""
    return _table_list(cur, project_id, "operational") + _table_list(cur, project_id, "dimensional")


def mapping_003(cur, project_id):
    """MAPPING-003 (warning): every active attribute except the surrogate key has a mapping line."""
    return _every_attribute_has_a_line(cur, project_id, "operational") + _every_attribute_has_a_line(cur, project_id, "dimensional")


def code_001(cur, project_id):
    """CODE-001 (warning): a source system is usually in only one code file of an entity."""
    return _one_file_per_system(cur, project_id, "operational") + _one_file_per_system(cur, project_id, "dimensional")


def code_002(cur, project_id):
    """CODE-002: the SQL of a code file or a check only reads (temporary views and one final SELECT), and parses."""
    return _code_reads(cur, project_id, "operational") + _code_reads(cur, project_id, "dimensional")


def code_003(cur, project_id):
    """CODE-003 (warning): the final SELECT returns every attribute but the surrogate key, SourceSystemID last."""
    return _final_select_columns(cur, project_id, "operational") + _final_select_columns(cur, project_id, "dimensional")


def code_004(cur, project_id):
    """CODE-004 (warning): a column is left as a NOT MAPPED placeholder."""
    return _not_mapped(cur, project_id, "operational") + _not_mapped(cur, project_id, "dimensional")


def validation_001(cur, project_id):
    """VALIDATION-001: a check's result type, operator, value type and value fit together."""
    return _pass_condition(cur, project_id, "operational") + _pass_condition(cur, project_id, "dimensional")


def validation_002(cur, project_id):
    """VALIDATION-002 (warning): a check reads the loaded table, and no table outside its mapping's tables and
    meta.system."""
    return _reads_its_tables(cur, project_id, "operational") + _reads_its_tables(cur, project_id, "dimensional")


def _parts(*names):
    return tuple(f"{m}_{n}" for m in ("operational", "dimensional") for n in names)


# Which parts each rule is about: it runs when a draft has records in one of them.
RULE_PARTS = {
    scope_001: ("project_input_scope",),
    scope_002: ("project_input_scope",),
    scope_005: ("project_input_scope",),
    enrichment_001: ("object_enrichment", "attribute_enrichment"),
    relationship_001: ("analysis_result",),
    relationship_002: ("analysis_result",),
    subject_area_001: ("subject_area", "subject_area_table", "project_input_scope"),
    subject_area_002: ("subject_area", "subject_area_table"),
    project_001: ("project_input_scope", "operational_entity", "dimensional_entity"),
    operational_001: ("operational_entity_source", "operational_entity", "project_input_scope"),
    operational_002: _model_parts("operational"),
    operational_003: _model_parts("operational"),
    operational_004: ("operational_entity",),
    operational_005: _model_parts("operational"),
    operational_006: ("operational_entity", "operational_attribute"),
    operational_007: ("operational_attribute",),
    operational_008: ("operational_attribute",),
    operational_009: ("operational_entity", "operational_link"),
    dimensional_001: ("dimensional_entity_source",),
    dimensional_002: _model_parts("dimensional"),
    dimensional_003: _model_parts("dimensional"),
    dimensional_004: ("dimensional_entity",),
    dimensional_005: _model_parts("dimensional"),
    dimensional_006: ("dimensional_entity", "dimensional_attribute"),
    dimensional_007: ("dimensional_attribute",),
    dimensional_008: _model_parts("dimensional") + _model_parts("operational"),
    dimensional_009: ("dimensional_attribute",),
    dimensional_010: ("dimensional_entity", "dimensional_link"),
    mapping_001: _parts("attribute_mapping"),
    mapping_002: _parts("object_mapping"),
    mapping_003: _parts("object_mapping", "attribute_mapping"),
    code_001: _parts("code", "code_system"),
    code_002: _parts("code", "validation_check"),
    code_003: _parts("code"),
    code_004: _parts("code"),
    validation_001: _parts("validation_check"),
    validation_002: _parts("validation_check"),
}
