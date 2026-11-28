"""Silver and Gold code: the SQL for one code file of an entity, from its applied mappings (design/workflows/code.md).

Before the AI call, Python builds a starter SQL from every field of the file's mappings: one temporary view per
system with the column list in load order, the joins from the mapping's sample query, the row filter and the batch
filter, `SourceSystemID` last and a NOT MAPPED placeholder where there is no line. The AI completes it, reading only
the mappings and the names and types of the tables they use. The SQL only gives the final rows; the orchestrator
loads them.
"""

import re

from core import blocks, prompts
from core.mapping import Context, attributes_of
from core.models import GOLD, SILVER, low
from core.parts import PARTS
from core.runs import Step, run_005

BATCH = ":batch_id"


def sql_name(schema, name):
    """The one place that decides how SQL names a table or entity: schema.name (the orchestrator picks the catalog)."""
    return f"{schema}.{name}"


def snake(name):
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def file_name(model, e, systems):
    m = model.m
    base = snake(e[f"{m}_entity_name"])
    return f"{base}_{systems[0].lower()}.sql" if len(systems) == 1 else f"{base}.sql"


def picked_files(model):
    """Items: (entity key, file name, systems). From `request["code_files"]`, or one file per entity covering every
    system with an applied mapping."""
    m = model.m

    def items(cur, project_id, request):
        ctx = Context(cur, project_id, model)
        applied = {}
        for key, saved in ctx.mappings.items():
            if saved["is_active"]:
                applied.setdefault(key[:2], []).append(saved["system_code"])
        wanted = request.get("code_files")
        found = []
        if wanted:
            for w in wanted:
                e = ctx.ledger.get(w[f"{m}_entity_schema_name"], w[f"{m}_entity_name"])
                name = f"{w[f'{m}_entity_schema_name']}.{w[f'{m}_entity_name']}"
                run_005((e is None or not e["is_active"]) and f"{name} is not an active entity.")
                systems = sorted(w.get("system_codes") or applied.get(model.key(e), []))
                missing = [s for s in systems if s.upper() not in [a.upper() for a in applied.get(model.key(e), [])]]
                run_005(missing and f"{name} has no applied mapping for {', '.join(missing)}.")
                run_005(not systems and f"{name} has no applied mapping yet.")
                found.append((model.key(e), w.get("file_name") or file_name(model, e, systems), systems))
        else:
            for key, systems in sorted(applied.items()):
                e = ctx.ledger.entities.get(key)
                if e and e["is_active"]:
                    found.append((key, file_name(model, e, sorted(systems)), sorted(systems)))
        run_005(not found and "There is no applied mapping to write code from.")
        cur.execute(PARTS[f"{m}_code"].read, {"project_id": project_id})
        locked = {model.key(r) + low(r[f"{m}_file_name"]) for r in cur.fetchall() if r["is_locked"]}
        for key, name, _ in found:
            run_005(key + low(name) in locked and f"The code file {name} is locked.")
        return found

    return items


def starter(ctx, e, systems):
    """The starter SQL: every field of every mapping of the file, laid out as the SQL must be."""
    model, m = ctx.model, ctx.model.m
    attrs = [a for a in attributes_of(model, e) if not a["is_surrogate_key"]]
    names = [a[f"{m}_attribute_name"] for a in attrs] + ["SourceSystemID"]
    entity = e[f"{m}_entity_name"]
    out = [f"-- Entity: {sql_name(e[f'{m}_entity_schema_name'], entity)}",
           f"-- Grain: {e.get(f'{m}_entity_grain') or ''}",
           f"-- Merged: {'yes' if e.get('is_merged') else 'no'}. History: {ctx.config.get(f'{m}_entity_scd_type') or 'not set'}.",
           ""]
    views = []
    for system in systems:
        mapping = ctx.mappings[model.key(e) + low(system)]
        view = f"temp_{snake(entity)}_{system.lower()}"
        views.append(view)
        lines = mapping["lines"]
        select = []
        for a in attrs:
            name, kind = a[f"{m}_attribute_name"], a[f"{m}_attribute_data_type"]
            line = lines.get(low(name))
            if line and line["is_active"]:
                select.append(f"        [{line[f'{m}_attribute_mapping_transformation']}] AS {name}, -- {kind}")
            else:
                select.append(f"        CAST(NULL AS {kind}) AS {name}, -- NOT MAPPED: no mapping line")
        select.append(f"        sys.SystemID AS SourceSystemID")
        query = (mapping[f"{m}_object_mapping_sample_query"] or "FROM [the driving table]").strip()
        where = []
        if mapping[f"{m}_object_mapping_row_filter"]:
            where.append(f"[{mapping[f'{m}_object_mapping_row_filter']}]")
        driving = re.search(r"FROM\s+([\w.]+)\s+(?:AS\s+)?(\w+)", query, re.IGNORECASE)
        if driving:
            table = ctx.scope.get(low(*driving.group(1).split(".")[-2:]))
            if table and table["batch_attribute_name"]:
                where.append(f"{driving.group(2)}.{table['batch_attribute_name']} = {BATCH}")
        if "meta.system" not in query:
            query += f"\nLEFT JOIN meta.system AS sys ON sys.SystemCode = '{system}'"
        out += [f"CREATE OR REPLACE TEMPORARY VIEW {view} AS (",
                f"    -- {mapping[f'{m}_object_mapping_transformation'] or ''}",
                "    SELECT", *select,
                *["    " + q for q in query.splitlines()],
                *([f"    WHERE {' AND '.join(where)}"] if where else []),
                ");", ""]
    if len(views) == 1:
        final = f"SELECT {', '.join(names)}\nFROM {views[0]};"
    elif e.get("is_merged"):
        final = f"SELECT {', '.join(names)}\nFROM [combine the views as the mappings say: {', '.join(views)}];"
    else:
        final = "\nUNION ALL\n".join(f"SELECT {', '.join(names)} FROM {v}" for v in views) + ";"
    return "\n".join(out + [final])


def sql_tables(ctx, e, systems):
    """Every table and entity the file's mappings use, by alias within each system, with the SQL name and types."""
    model, out = ctx.model, []
    for system in systems:
        for item in ctx.plan(e, system):
            row = item["row"]
            if "object_id" in row:
                cols = ctx.columns(row)
                head = {"system_code": system, "alias": item["alias"], "sql_name": sql_name(row["object_schema"], row["object_name"]),
                        "batch_column": row["batch_attribute_name"]}
                out.append(blocks.block("table", head, cols, ("attribute_name", "attribute_data_type")))
            else:
                em = SILVER if "operational_entity_name" in row else GOLD
                head = {"system_code": system, "alias": item["alias"],
                        "sql_name": sql_name(row[f"{em.m}_entity_schema_name"], row[f"{em.m}_entity_name"])}
                out.append(blocks.block("entity", head, attributes_of(em, row) + [{f"{em.m}_attribute_name": "SourceSystemID",
                                                                                   f"{em.m}_attribute_data_type": "BIGINT"}],
                                        (f"{em.m}_attribute_name", f"{em.m}_attribute_data_type")))
    return "\n\n".join(out)


def prepare(model):
    m = model.m

    def run(cur, run_row, items):
        ctx = Context(cur, run_row["project_id"], model)
        cur.execute(PARTS[f"{m}_code"].read, {"project_id": run_row["project_id"]})
        saved = {model.key(r) + low(r[f"{m}_file_name"]): r for r in cur.fetchall()}
        run_row["ctx"], run_row["files"], prepared = ctx, {}, {}
        for key, name, systems in items:
            e = ctx.ledger.entities[key]
            existing = saved.get(key + low(name))
            run_row["files"][name] = (key, systems, existing)
            prepared[name] = {
                "context_records": prompts.context_records(cur, run_row["project_id"], f"{m}_code", systems),
                "systems": blocks.systems(cur, run_row["project_id"], systems),
                "starter_sql": starter(ctx, e, systems),
                "sql_tables": sql_tables(ctx, e, systems),
                "existing_code": existing[f"{m}_code_text"] if existing and existing["is_active"] else blocks.NONE,
            }
        return prepared, []

    return run


def records(model):
    m = model.m

    def run(cur, run_row, name, answer):
        key, systems, existing = run_row["files"][name]
        e = run_row["ctx"].ledger.entities[key]
        owner = {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
                 f"{m}_file_name": name}
        documents = {}
        if not existing or existing[f"{m}_code_text"] != answer["sql"] or not existing["is_active"]:
            documents[f"{m}_code"] = [owner | {f"{m}_code_text": answer["sql"], "is_active": True}]
        documents[f"{m}_code_system"] = [owner | {"system_code": s, "is_active": True} for s in systems]
        return documents, []

    return run


INPUTS = {
    "context_records": "the tenant's code Notes: layout and house standards",
    "systems": "the tenant and the systems this file covers: one view per system, each with its meta.system lookup",
    "starter_sql": "the SQL to complete: every field of the mappings in place; text in [brackets] is a mapping's words",
    "sql_tables": "every table and entity the mappings use (blocks), by alias within each system, with the name SQL "
                  "uses, each column's type and the batch column",
    "existing_code": "the file's saved SQL, or none: a rerun updates it to match the starter",
}


def step(model):
    m = model.m
    return Step(workflow=f"{m}_code", title=f"{'Silver' if model is SILVER else 'Gold'} code", inputs=INPUTS,
                answer={"name": f"{m}_code", "schema": {
                    "type": "object", "additionalProperties": False, "required": ["sql"],
                    "properties": {"sql": {"type": "string", "description": "the complete SQL of the file"}}}},
                items=picked_files(model), prepare=prepare(model), records=records(model))


STEPS = (step(SILVER), step(GOLD))
