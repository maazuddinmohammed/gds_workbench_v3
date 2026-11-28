"""Subject areas: the AI groups the scope tables into business areas (design/workflows/subject-areas.md).

One one shot call for the whole scope, without samples. An area the AI gives back carries its complete table list:
a saved table missing from it is switched off, unless locked. Areas it leaves out stay as they are.
"""

from core import blocks, prompts
from core.enrichment import label
from core.parts import PARTS
from core.relationships import saved_links
from core.runs import Step, run_005

SCOPE_FIELDS = ("object_schema", "object_name", "system_code", "object_definition", "object_grain", "row_count",
                "column_count", "subject_area_names")
WHOLE_SCOPE = "the whole scope"


def items(cur, project_id, request):
    run_005(not blocks.scope_tables(cur, project_id) and "The project has no active tables in scope.")
    return [WHOLE_SCOPE]


def _saved(cur, project_id):
    cur.execute(PARTS["subject_area"].read, {"project_id": project_id})
    areas = {a["subject_area_name"].lower(): a | {"tables": []} for a in cur.fetchall()}
    cur.execute(PARTS["subject_area_table"].read, {"project_id": project_id})
    for row in cur.fetchall():
        areas[row["subject_area_name"].lower()]["tables"].append(row)
    return areas


def prepare(cur, run, _items):
    project_id = run["project_id"]
    scope = blocks.scope_tables(cur, project_id)
    areas = _saved(cur, project_id)
    in_area = {}
    for area in areas.values():
        for t in area["tables"]:
            if area["is_active"] and t["is_active"]:
                in_area.setdefault(f"{t['object_schema']}.{t['object_name']}", []).append(area["subject_area_name"])
    rows = [t | {"subject_area_names": in_area.get(label(t), [])} for t in scope]
    pairs = {}
    for link in saved_links(cur, project_id):
        if link["is_active"] and link["relationship_kind"] != "same_code_list":
            key = (link["from_object_schema"], link["from_object_name"], link["to_object_schema"], link["to_object_name"])
            pairs.setdefault(key, []).append(
                f"{link['from_attribute_name']}->{link['to_attribute_name']} ({link['relationship_kind']})")
    links = [{"from_object_schema": k[0], "from_object_name": k[1], "to_object_schema": k[2], "to_object_name": k[3],
              "links": v} for k, v in sorted(pairs.items())]
    existing = [{"subject_area_name": a["subject_area_name"], "subject_area_definition": a["subject_area_definition"],
                 "is_locked": a["is_locked"], "is_active": a["is_active"],
                 "tables": [{"object_schema": t["object_schema"], "object_name": t["object_name"]}
                            for t in a["tables"] if t["is_active"]],
                 "locked_out_tables": [{"object_schema": t["object_schema"], "object_name": t["object_name"]}
                                       for t in a["tables"] if not t["is_active"]]}
                for a in areas.values()]
    cur.execute("SELECT subject_area_target_column_count FROM project.project_config WHERE project_id = %s",
                (project_id,))
    target = (cur.fetchone() or {}).get("subject_area_target_column_count") or 800
    run["areas"], run["scope"] = areas, {label(t).lower(): t for t in scope}
    systems = [t["system_code"] for t in scope]
    return {WHOLE_SCOPE: {
        "systems": blocks.systems(cur, project_id, systems),
        "context_records": prompts.context_records(cur, project_id, "subject_area", systems),
        "scope_tables": blocks.rows(rows, SCOPE_FIELDS),
        "subject_area_target_column_count": str(target),
        "table_relationships": blocks.rows(links, ("from_object_schema", "from_object_name", "to_object_schema",
                                                   "to_object_name", "links")),
        "existing_subject_areas": blocks.as_json(existing) if existing else blocks.NONE,
    }}, []


def records(cur, run, _name, answer):
    areas, scope = run["areas"], run["scope"]
    found_areas, found_tables, notes = [], [], []
    for given in answer["subject_areas"]:
        name = given["subject_area_name"].strip()
        saved = areas.get(name.lower())
        if saved and saved["is_locked"]:
            notes.append(f"{name} is locked, left out (RUN-007).")
            continue
        area = {"subject_area_name": saved["subject_area_name"] if saved else name}
        changed = {f: given[f] for f in ("subject_area_definition", "is_active") if not saved or saved[f] != given[f]}
        if changed:
            found_areas.append(area | changed)
        if not given["is_active"]:
            continue
        listed = {f"{t['object_schema']}.{t['object_name']}".lower(): t for t in given["tables"]}
        old = {f"{t['object_schema']}.{t['object_name']}".lower(): t for t in (saved["tables"] if saved else [])}
        for key, t in listed.items():
            table = scope.get(key)
            names = {"object_schema": table["object_schema"], "object_name": table["object_name"]} if table else \
                {"object_schema": t["object_schema"], "object_name": t["object_name"]}
            if key in old and not old[key]["is_active"]:
                notes.append(f"{key} was taken out of {name} by a person, left out.")
            elif key not in old:
                found_tables.append(area | names | {"is_active": True})
        for key, t in old.items():  # an area's list is complete: a saved table missing from it is switched off
            if key not in listed and t["is_active"] and not t["is_locked"]:
                found_tables.append(area | {"object_schema": t["object_schema"], "object_name": t["object_name"],
                                            "is_active": False})
    documents = {"subject_area": found_areas, "subject_area_table": found_tables}
    return {k: v for k, v in documents.items() if v}, notes


STEP = Step(
    workflow="subject_area",
    title="Subject areas",
    inputs={
        "systems": "the tenant and every system in scope",
        "context_records": "the tenant's Notes: facts about the systems and how it wants tables grouped",
        "scope_tables": "every scope table (rows) with its definition, Grain, row count, column count and the areas "
                        "it is in now",
        "subject_area_target_column_count": "about how many columns one area should hold in total: a guide, not a limit",
        "table_relationships": "one row per pair of linked tables, with the linking columns and the kind of link "
                               "(shared code lists left out)",
        "existing_subject_areas": "the saved areas (JSON) with their tables and locks, and the tables a person took "
                                  "out of each (locked_out_tables)",
    },
    answer={"name": "subject_areas", "schema": {
        "type": "object", "additionalProperties": False, "required": ["subject_areas"],
        "properties": {"subject_areas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["subject_area_name", "subject_area_definition", "tables", "is_active"],
            "properties": {
                "subject_area_name": {"type": "string"},
                "subject_area_definition": {"type": "string",
                                            "description": "the area's boundary: what is in it and what is not"},
                "tables": {"type": "array", "description": "the area's complete list of tables", "items": {
                    "type": "object", "additionalProperties": False, "required": ["object_schema", "object_name"],
                    "properties": {"object_schema": {"type": "string"}, "object_name": {"type": "string"}}}},
                "is_active": {"type": "boolean", "description": "false only to switch a saved area off"}}}}}}},
    items=items,
    prepare=prepare,
    records=records,
)

