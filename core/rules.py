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


# Which parts each rule is about: it runs when a draft has records in one of them.
RULE_PARTS = {
    scope_001: ("project_input_scope",),
    scope_002: ("project_input_scope",),
    scope_005: ("project_input_scope",),
}
