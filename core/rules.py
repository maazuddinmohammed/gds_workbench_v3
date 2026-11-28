"""The rules a draft is checked against once its records are saved (docs/rules/), one function per rule ID.

`core/change_sets.py` saves a draft's records on the project, then calls `check`: each rule reads the project as it
would be after Apply and returns (part, row id, message) for every row that breaks it. A rule runs only when the draft
has records in one of the parts it is about (RULE_PARTS), so a draft that takes a table out of scope is stopped if a
subject area still uses it, while an enrichment draft is not held up by a model rule. A problem names the record that
touched the row, when one did.

The checks on the whole draft and on each record (CHANGE-SET-001, 002, 003, 005, 012 and 013) are in
core/change_sets.py, next to the code that reads the records.
"""

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
}
