"""Silver and Gold validation: checks on one entity's loaded table for one system, written from the applied mapping,
never from the code (design/workflows/validation.md).

One one shot call per applied mapping. Each check is one SELECT that counts the rows breaking it, and passes at 0:
Python sets its pass condition. The standard checks (natural key unique, required attributes filled, links that
hold a real parent key) are run by a separate framework, so the AI never writes them.
"""

from core import blocks, prompts
from core.code import sql_name
from core.mapping import Context, mapping_tables, target_entity
from core.models import GOLD, SILVER, low
from core.parts import PARTS
from core.rules import LISTS
from core.runs import Step, run_005

PASS_CONDITION = {"validation_result_data_type": "integer", "validation_comparison_operator": "equal",
                  "validation_comparison_value_type": "literal", "validation_comparison_value": 0}


def picked(model):
    """Items: (entity key, system) of applied mappings, from `request["mappings"]` or every applied one."""
    m = model.m

    def items(cur, project_id, request):
        ctx = Context(cur, project_id, model)
        applied = {k for k, saved in ctx.mappings.items() if saved["is_active"]}
        wanted = request.get("mappings")
        if wanted:
            found = []
            for w in wanted:  # without a system_code: every applied mapping of the entity
                entity = low(w[f"{m}_entity_schema_name"], w[f"{m}_entity_name"])
                keys = [k for k in applied if k[:2] == entity and k[2] == low(w.get("system_code") or k[2])[0]]
                run_005(not keys and f"{'.'.join(entity)} has no applied mapping for {w.get('system_code') or 'any system'}.")
                found += sorted((k[:2], ctx.mappings[k]["system_code"]) for k in keys)
        else:
            found = sorted((k[:2], ctx.mappings[k]["system_code"]) for k in applied)
        run_005(not found and "There is no applied mapping to write checks from.")
        cur.execute(PARTS[f"{m}_validation_group"].read, {"project_id": project_id})
        locked = {model.key(r) + low(r["system_code"]) for r in cur.fetchall() if r["is_locked"]}
        for key, system in found:
            run_005(key + low(system) in locked and f"The checks of {'.'.join(key)} for {system} are locked.")
        return found

    return items


def prepare(model):
    m = model.m

    def run(cur, run_row, items):
        ctx = Context(cur, run_row["project_id"], model)
        cur.execute(PARTS[f"{m}_validation_check"].read, {"project_id": run_row["project_id"]})
        checks = {}
        for c in cur.fetchall():
            checks.setdefault(model.key(c) + low(c["system_code"]), []).append(c)
        run_row["ctx"], run_row["groups"], prepared = ctx, {}, {}
        for key, system in items:
            e = ctx.ledger.entities[key]
            saved = ctx.mappings[key + low(system)]
            plan = ctx.plan(e, system)
            existing = checks.get(key + low(system), [])
            name = f"{e[f'{m}_entity_schema_name']}.{e[f'{m}_entity_name']} / {system}"
            run_row["groups"][name] = (key, system, existing)

            def extra(item):
                row = item["row"]
                if "object_id" in row:
                    return {"sql_name": sql_name(row["object_schema"], row["object_name"]),
                            "batch_column": row["batch_attribute_name"]}
                em = SILVER if "operational_entity_name" in row else GOLD
                return {"sql_name": sql_name(row[f"{em.m}_entity_schema_name"], row[f"{em.m}_entity_name"]),
                        "audit_columns": ["SourceSystemID"] + [c["name"] for c in ctx.config.get(f"{em.m}_audit_columns") or []]}

            target = target_entity(ctx, e, plan, saved, lines_field="mapping_line")
            audit = [{"name": "SourceSystemID", "data_type": "BIGINT", "definition": "The system the row came from: "
                      "meta.system.SystemID of the row's SystemCode."}] + (ctx.config.get(f"{m}_audit_columns") or [])
            target = target.replace("entity {", "entity {" + f'"sql_name": "{sql_name(e[f"{m}_entity_schema_name"], e[f"{m}_entity_name"])}", ', 1)
            target += "\n" + blocks.rows([a | {"is_audit_column": True} for a in audit],
                                         ("name", "data_type", "is_audit_column", "definition"))
            part = {k: saved[k] for k in (f"{m}_object_mapping_row_filter", f"{m}_object_mapping_sample_query",
                                          f"{m}_object_mapping_transformation")}
            prepared[name] = {
                "context_records": prompts.context_records(cur, run_row["project_id"], f"{m}_validation", [system]),
                "systems": blocks.systems(cur, run_row["project_id"], [system]),
                "target_entity": target,
                "mapping_part": blocks.as_json(part),
                "mapping_tables": mapping_tables(ctx, e, plan, extra),
                "existing_checks": blocks.as_json([{k: v for k, v in c.items() if not k.startswith(f"{m}_entity")
                                                    and k != "system_code" and not k.startswith("validation_comparison")
                                                    and k != "validation_result_data_type"} for c in existing])
                if existing else blocks.NONE,
            }
        return prepared, []

    return run


def records(model):
    m = model.m

    def run(cur, run_row, name, answer):
        key, system, existing = run_row["groups"][name]
        e = run_row["ctx"].ledger.entities[key]
        owner = {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
                 "system_code": system}
        saved = {low(c[f"{m}_validation_check_name"]): c for c in existing}
        checks, notes = [], []
        fields = (f"{m}_validation_check_description", "validation_category_code", "validation_severity",
                  "validation_query_sql", "is_active")
        for c in answer["checks"]:
            old = saved.get(low(c[f"{m}_validation_check_name"]))
            if old and old["is_locked"]:
                notes.append(f"the check {c[f'{m}_validation_check_name']} is locked, left out (RUN-007).")
                continue
            if old and all(old[f] == c[f] for f in fields):
                continue
            checks.append(owner | {f"{m}_validation_check_name": c[f"{m}_validation_check_name"],
                                   **{f: c[f] for f in fields}, **PASS_CONDITION})
        documents = {f"{m}_validation_group": [owner | {f"{m}_validation_group_description":
                                                          answer[f"{m}_validation_group_description"]}]}
        if checks:
            documents[f"{m}_validation_check"] = checks
        return documents, notes

    return run


INPUTS = {
    "context_records": "the tenant's validation Notes (business rules to check) and mapping Notes (the house "
                       "standards the code applies)",
    "systems": "the tenant and the system whose loaded rows the checks test",
    "target_entity": "the loaded table (block): its SQL name, then one row per column in load order with its type, "
                     "marks, parent by alias and applied mapping line; then the audit columns the load adds",
    "mapping_part": "the applied mapping part: which source rows should arrive, and how they join",
    "mapping_tables": "the mapping's tables and lookups (blocks), with the same aliases, each with its SQL name and "
                      "batch column; a lookup lists its audit columns",
    "existing_checks": "the group's saved checks with their locks, or none: a rerun builds on them",
}


def step(model):
    m = model.m
    s = {"type": "string"}
    check = {"type": "object", "additionalProperties": False,
             "required": [f"{m}_validation_check_name", f"{m}_validation_check_description", "validation_category_code",
                          "validation_severity", "validation_query_sql", "is_active"],
             "properties": {f"{m}_validation_check_name": s, f"{m}_validation_check_description": s,
                            "validation_category_code": {"type": "string", "enum": list(LISTS["validation_category_code"])},
                            "validation_severity": {"type": "string", "enum": list(LISTS["validation_severity"])},
                            "validation_query_sql": {"type": "string", "description": "one SELECT returning one count"},
                            "is_active": {"type": "boolean"}}}
    return Step(workflow=f"{m}_validation", title=f"{'Silver' if model is SILVER else 'Gold'} validation", inputs=INPUTS,
                answer={"name": f"{m}_validation", "schema": {
                    "type": "object", "additionalProperties": False,
                    "required": [f"{m}_validation_group_description", "checks"],
                    "properties": {f"{m}_validation_group_description": s,
                                   "checks": {"type": "array", "items": check}}}},
                items=picked(model), prepare=prepare(model), records=records(model))


STEPS = (step(SILVER), step(GOLD))
