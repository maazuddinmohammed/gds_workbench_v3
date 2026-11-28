"""Object and attribute enrichment: the AI defines each scope table, then its columns (design/workflows/analysis.md).

Two one shot steps with one AI call per table. Object enrichment writes a table's definition and Grain; attribute
enrichment then defines each column, works out its real data type and marks its keys, nullability and personal data.
An answer becomes draft records holding only what differs from what is saved; `null` keeps the saved value.
"""

from core import blocks, prompts
from core.runs import Step, run_005

SYSTEMS = "the tenant and the table's system, such as a CRM product: it says what the table's objects mean"
NOTES = "Notes of the tenant about this system (source_information) and how it wants things defined (enrichment_requirement)"


def picked_tables(cur, project_id, request):
    """The scope tables the person picked (`request["tables"]`: schema and name of each), or every one."""
    tables = blocks.scope_tables(cur, project_id)
    wanted = request.get("tables")
    if wanted:
        by_name = {(t["object_schema"].lower(), t["object_name"].lower()): t for t in tables}
        missing = [f"{w['object_schema']}.{w['object_name']}" for w in wanted
                   if (w["object_schema"].lower(), w["object_name"].lower()) not in by_name]
        run_005(missing and f"Not active tables in scope: {', '.join(missing)}.")
        tables = [by_name[(w["object_schema"].lower(), w["object_name"].lower())] for w in wanted]
    run_005(not tables and "The project has no active tables in scope.")
    return tables


def label(table):
    return f"{table['object_schema']}.{table['object_name']}"


def _common(cur, run, table):
    return {"systems": blocks.systems(cur, run["project_id"], [table["system_code"]]),
            "context_records": prompts.context_records(cur, run["project_id"], run["project_workflow"],
                                                       [table["system_code"]])}


# --- Object enrichment -------------------------------------------------------------------------------------------

OBJECT_COLUMNS = ("attribute_name", "attribute_data_type", "null_count", "blank_count", "distinct_count",
                  "attribute_definition", "sample_values")


def prepare_objects(cur, run, tables):
    prepared, lines, run["tables"] = {}, [], {}
    for table in tables:
        if table["enrichment_is_locked"]:
            lines.append(f"{label(table)}: locked, skipped.")
            continue
        cols = [c for c in blocks.columns(cur, run["project_id"], table["object_id"]) if not c["is_meta_data"]]
        head = {k: table[k] for k in ("object_schema", "object_name", "system_code", "row_count",
                                      "object_definition", "object_grain")}
        run["tables"][label(table)] = table
        prepared[label(table)] = _common(cur, run, table) | {"table": blocks.block("table", head, cols, OBJECT_COLUMNS)}
    return prepared, lines


def object_records(cur, run, name, answer):
    table = run["tables"][name]
    record = {f: answer[f] for f in ("object_definition", "object_grain") if answer[f] and answer[f] != table[f]}
    if not any(answer.values()):
        return {}, ["nothing proposed."]
    if not record:
        return {}, []
    return {"object_enrichment": [{"object_schema": table["object_schema"], "object_name": table["object_name"],
                                   **record}]}, []


OBJECT = Step(
    workflow="object_enrichment",
    title="Object enrichment",
    inputs={"systems": SYSTEMS, "context_records": NOTES,
            "table": "the table (block): its saved definition and Grain, if any, then its business columns with "
                     "counts, the project's column definitions and samples"},
    answer={"name": "object_enrichment", "schema": {
        "type": "object", "additionalProperties": False, "required": ["object_definition", "object_grain"],
        "properties": {"object_definition": {"type": ["string", "null"], "description": prompts.FIELDS["object_definition"]},
                       "object_grain": {"type": ["string", "null"], "description": prompts.FIELDS["object_grain"]}}}},
    items=picked_tables,
    prepare=prepare_objects,
    records=object_records,
)


# --- Attribute enrichment ----------------------------------------------------------------------------------------

MARKS = ("is_natural_key", "is_surrogate_key", "is_foreign_key_candidate", "is_nullable", "is_pii")
ANSWER_FIELDS = ("attribute_definition", "attribute_inferred_data_type") + MARKS
ATTRIBUTE_COLUMNS = ("attribute_name", "attribute_data_type", "is_meta_data", "null_count", "blank_count",
                     "distinct_count", "min_data_length", "max_data_length") + ANSWER_FIELDS + ("is_locked", "sample_values")


def prepare_attributes(cur, run, tables):
    prepared, lines, run["tables"] = {}, [], {}
    for table in tables:
        cols = blocks.columns(cur, run["project_id"], table["object_id"])
        if cols and all(c["is_locked"] for c in cols):
            lines.append(f"{label(table)}: every column is locked, skipped.")
            continue
        head = {k: table[k] for k in ("object_schema", "object_name", "system_code", "row_count",
                                      "object_definition", "object_grain")}
        run["tables"][label(table)] = table | {"columns": {c["attribute_name"].lower(): c for c in cols}}
        prepared[label(table)] = _common(cur, run, table) | {
            "table": blocks.block("table", head, cols, ATTRIBUTE_COLUMNS)}
    return prepared, lines


def attribute_records(cur, run, name, answer):
    table = run["tables"][name]
    records, notes = [], []
    for col in answer["columns"]:
        saved = table["columns"].get(col["attribute_name"].lower())
        if saved and saved["is_locked"]:
            notes.append(f"{col['attribute_name']} is locked, left out (RUN-007).")
            continue
        changed = {f: col[f] for f in ANSWER_FIELDS if col[f] is not None and (saved is None or col[f] != saved[f])}
        if changed:
            records.append({"object_schema": table["object_schema"], "object_name": table["object_name"],
                            "attribute_name": saved["attribute_name"] if saved else col["attribute_name"], **changed})
    return ({"attribute_enrichment": records} if records else {}), notes


def _nullable(kind, field):
    return {"type": [kind, "null"], "description": prompts.FIELDS[field]}


ATTRIBUTE = Step(
    workflow="attribute_enrichment",
    title="Attribute enrichment",
    inputs={"systems": SYSTEMS, "context_records": NOTES,
            "table": "the table (block): its reviewed definition and Grain, then every column with its counts, "
                     "lengths, samples and what is saved for it now; technical columns are marked is_meta_data"},
    answer={"name": "attribute_enrichment", "schema": {
        "type": "object", "additionalProperties": False, "required": ["columns"],
        "properties": {"columns": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["attribute_name", *ANSWER_FIELDS],
            "properties": {"attribute_name": {"type": "string"},
                           "attribute_definition": _nullable("string", "attribute_definition"),
                           "attribute_inferred_data_type": _nullable("string", "attribute_inferred_data_type"),
                           **{m: _nullable("boolean", m) for m in MARKS}}}}}}},
    items=picked_tables,
    prepare=prepare_attributes,
    records=attribute_records,
)

STEPS = (OBJECT, ATTRIBUTE)
