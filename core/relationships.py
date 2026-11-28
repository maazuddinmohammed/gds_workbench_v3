"""Relationships (`analysis`): the AI finds the links between scope tables, table by table
(design/workflows/analysis.md).

One one shot call per table, which proposes only the links that start in that table. Every call is given every scope
table's key and pointing columns (`to_tables`), so batches find the same links as one big Run. An answer gives only
the links it adds, changes or switches off.
"""

from core import blocks, prompts
from core.enrichment import label, picked_tables
from core.parts import PARTS
from core.rules import LISTS
from core.runs import Step, run_005

TO_COLUMNS = ("attribute_name", "attribute_inferred_data_type", "is_natural_key", "is_surrogate_key",
              "is_foreign_key_candidate", "distinct_count", "sample_values")
FROM_COLUMNS = ("attribute_name", "attribute_data_type", "attribute_inferred_data_type", "is_natural_key",
                "is_surrogate_key", "is_foreign_key_candidate", "null_count", "distinct_count", "attribute_definition",
                "sample_values")
LINK_FIELDS = ("from_attribute_name", "to_object_schema", "to_object_name", "to_attribute_name", "relationship_kind",
               "inferred_cardinality", "validation_result", "validation_source_missing_target_count",
               "validation_duplicate_target_key_count", "is_active", "is_locked")
SAMPLES = 3  # stored samples per key column in to_tables


def saved_links(cur, project_id):
    """The project's relationships as records, switched-off ones included."""
    cur.execute(PARTS["analysis_result"].read, {"project_id": project_id})
    return cur.fetchall()


def items(cur, project_id, request):
    tables = picked_tables(cur, project_id, request)
    cur.execute(
        """SELECT 1 FROM workflow.attribute_enrichment
            WHERE project_id = %s AND is_active AND (is_natural_key OR is_surrogate_key) LIMIT 1""",
        (project_id,),
    )
    run_005(cur.fetchone() is None and "No column in scope is marked as a natural or surrogate key, so there is "
                                      "nothing to point at. Run column enrichment first.")
    return tables


def prepare(cur, run, tables):
    project_id = run["project_id"]
    scope = blocks.scope_tables(cur, project_id)
    to_tables, lines, columns = [], [], {}
    for table in scope:
        cols = blocks.columns(cur, project_id, table["object_id"])
        columns[label(table)] = cols
        keys = [c | {"sample_values": c["sample_values"][:SAMPLES]} for c in cols
                if c["is_natural_key"] or c["is_surrogate_key"] or c["is_foreign_key_candidate"]]
        if not any(c["is_natural_key"] or c["is_surrogate_key"] for c in keys):
            lines.append(f"{label(table)} has no key marked, so no link can point at it.")
        head = {k: table[k] for k in ("object_schema", "object_name", "system_code", "row_count")}
        to_tables.append(blocks.block("table", head, keys, TO_COLUMNS))
    links = saved_links(cur, project_id)
    shared = {"systems": blocks.systems(cur, project_id, [t["system_code"] for t in scope]),
              "context_records": prompts.context_records(cur, project_id, "analysis", [t["system_code"] for t in scope]),
              "to_tables": "\n\n".join(to_tables)}
    prepared, run["tables"] = {}, {}
    for table in tables:
        name = label(table)
        mine = [link for link in links if f"{link['from_object_schema']}.{link['from_object_name']}" == name]
        theirs = [link for link in links if f"{link['to_object_schema']}.{link['to_object_name']}" == name
                  and link["is_active"] and link not in mine]
        run["tables"][name] = table | {"links": mine}
        head = {k: table[k] for k in ("object_schema", "object_name", "system_code", "row_count", "object_definition",
                                      "object_grain")}
        prepared[name] = shared | {
            "from_table": blocks.block("table", head, [c for c in columns[name] if not c["is_meta_data"]], FROM_COLUMNS),
            "relationships_from_this_table": blocks.rows(mine, LINK_FIELDS),
            "relationships_to_this_table": blocks.rows(theirs, ("from_object_schema", "from_object_name",
                                                                "from_attribute_name", "to_attribute_name",
                                                                "relationship_kind")),
        }
    return prepared, lines


def records(cur, run, name, answer):
    table = run["tables"][name]
    saved = {(link["from_attribute_name"].lower(), link["to_object_schema"].lower(), link["to_object_name"].lower(),
              link["to_attribute_name"].lower()): link for link in table["links"]}
    found, notes = [], []
    for given in answer["relationships"]:
        key = (given["from_attribute_name"].lower(), given["to_object_schema"].lower(), given["to_object_name"].lower(),
               given["to_attribute_name"].lower())
        link = saved.get(key)
        if link and link["is_locked"]:
            notes.append(f"the link from {given['from_attribute_name']} is locked, left out (RUN-007).")
            continue
        if link and not link["is_active"] and given["is_active"]:
            notes.append(f"the link from {given['from_attribute_name']} was switched off by a person, left out.")
            continue
        fields = ("relationship_kind", "inferred_cardinality", "is_active")
        if link and all(link[f] == given[f] for f in fields):
            continue
        if not link and not given["is_active"]:
            continue
        found.append({"from_object_schema": table["object_schema"], "from_object_name": table["object_name"],
                      **{k: given[k] for k in ("from_attribute_name", "to_object_schema", "to_object_name",
                                               "to_attribute_name")},
                      **{f: given[f] for f in fields}})
    return ({"analysis_result": found} if found else {}), notes


STEP = Step(
    workflow="analysis",
    title="Relationships",
    inputs={
        "systems": "the tenant and every system in scope; a link can cross systems",
        "context_records": "the tenant's Notes: facts about the systems and rules for finding links",
        "to_tables": "every scope table (blocks), this one included, with only the columns marked as natural key, "
                     "surrogate key or pointing elsewhere: the columns a link may point at",
        "from_table": "the table the links start in (block): its business columns with counts and samples",
        "relationships_from_this_table": "the saved links that start in this table (rows), switched-off ones "
                                         "included; you may keep, change or switch these off",
        "relationships_to_this_table": "the saved links from other tables that point at this table (rows), for "
                                       "reading only, so you do not add the same pair the other way round",
    },
    answer={"name": "relationships", "schema": {
        "type": "object", "additionalProperties": False, "required": ["relationships"],
        "properties": {"relationships": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["from_attribute_name", "to_object_schema", "to_object_name", "to_attribute_name",
                         "relationship_kind", "inferred_cardinality", "is_active"],
            "properties": {
                "from_attribute_name": {"type": "string", "description": "the column in this table"},
                "to_object_schema": {"type": "string"}, "to_object_name": {"type": "string"},
                "to_attribute_name": {"type": "string", "description": "the column it points at"},
                "relationship_kind": {"type": "string", "enum": list(LISTS["relationship_kind"])},
                "inferred_cardinality": {"type": "string", "enum": list(LISTS["inferred_cardinality"])},
                "is_active": {"type": "boolean", "description": "false only to switch a saved link off"}}}}}}},
    items=items,
    prepare=prepare,
    records=records,
)
