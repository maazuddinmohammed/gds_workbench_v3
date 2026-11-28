"""Silver and Gold mapping: how one source system loads one entity (design/workflows/mapping.md).

One one shot call per mapping (an entity and a system). Python builds the table list: this system's sources of the
entity, each with an alias, plus the parent entity behind each link as a lookup. The AI writes the mapping part (rows
to keep, a sample query with the joins, the entity level transformation) and one line per attribute. Attributes it
cannot map go in `unmapped` with the reason, which the Run log keeps for the review.

The same table list and layout serve the code and validation steps (core/code.py, core/validation.py).
"""

import re

from core import blocks, prompts
from core.models import GOLD, SILVER, Ledger, low
from core.parts import PARTS
from core.relationships import saved_links
from core.runs import Step, run_005

SAMPLES = 3  # samples of a lookup's natural key source
SOURCE_COLUMNS = ("attribute_name", "attribute_data_type", "is_natural_key", "is_meta_data", "is_nullable", "null_count",
                  "blank_count", "distinct_count", "attribute_definition", "sample_values", "links_to", "linked_from")


def alias_for(name, taken):
    """A short alias from a name's words: kics_user_info_v1 -> kui, JobProfile -> jp; numbered when taken."""
    words = [w for w in re.split(r"_|(?<=[a-z])(?=[A-Z])", name) if w and not re.fullmatch(r"v\d+", w.lower())]
    base = "".join(w[0] for w in words).lower()[:4] or "t"
    alias, n = base, 1
    while alias in taken:
        n += 1
        alias = f"{base}{n}"
    taken.add(alias)
    return alias


class Context:
    """What the mapping, code and validation calls of one Run share: the scope, the models and the saved mappings."""

    def __init__(self, cur, project_id, model):
        self.cur, self.project_id, self.model, m = cur, project_id, model, model.m
        self.scope = {low(t["object_schema"], t["object_name"]): t for t in blocks.scope_tables(cur, project_id)}
        self.silver = Ledger(cur, project_id, SILVER)
        self.ledger = self.silver if model is SILVER else Ledger(cur, project_id, GOLD)
        self.links = [link for link in saved_links(cur, project_id) if link["is_active"]]
        cur.execute("SELECT * FROM project.project_config WHERE project_id = %s", (project_id,))
        self.config = cur.fetchone() or {}
        self.mappings = {}
        cur.execute(PARTS[f"{m}_object_mapping"].read, {"project_id": project_id})
        for row in cur.fetchall():
            self.mappings[model.key(row) + low(row["system_code"])] = row | {"lines": {}}
        cur.execute(PARTS[f"{m}_attribute_mapping"].read, {"project_id": project_id})
        for row in cur.fetchall():
            self.mappings[model.key(row) + low(row["system_code"])]["lines"][low(row[f"{m}_attribute_name"])] = row
        self._columns = {}

    def columns(self, table):
        if table["object_id"] not in self._columns:
            self._columns[table["object_id"]] = blocks.columns(self.cur, self.project_id, table["object_id"])
        return self._columns[table["object_id"]]

    def silver_systems(self, e):
        """The systems a Silver entity's rows come from: the systems of its active source tables."""
        return sorted({self.scope[k]["system_code"] for k, s in e["sources"].items()
                       if s.get("is_active", True) and k in self.scope})

    def systems_of(self, e):
        if self.model is SILVER:
            return self.silver_systems(e)
        return sorted({s for k, src in e["sources"].items() if src.get("is_active", True) and k in self.silver.entities
                       for s in self.silver_systems(self.silver.entities[k])})

    def plan(self, e, system):
        """The table list of one mapping: this system's sources, then the parent behind each link, each with an
        alias. Each item: alias, role, its names as the mapping's table list stores them, and the row it is."""
        m, taken, items = self.model.m, set(), []
        for key, src in sorted(e["sources"].items()):
            if not src.get("is_active", True):
                continue
            if self.model is SILVER and key in self.scope and self.scope[key]["system_code"] == system:
                t = self.scope[key]
                items.append({"alias": alias_for(t["object_name"], taken), "role": "source", "key": key, "row": t,
                              "names": {"object_schema": t["object_schema"], "object_name": t["object_name"]}})
            if self.model is GOLD and key in self.silver.entities and system in self.silver_systems(self.silver.entities[key]):
                s = self.silver.entities[key]
                items.append({"alias": alias_for(s["operational_entity_name"], taken), "role": "source", "key": key,
                              "row": s, "names": {"operational_entity_schema_name": s["operational_entity_schema_name"],
                                                  "operational_entity_name": s["operational_entity_name"]}})
        for a in sorted(e["attributes"].values(), key=lambda a: a.get(f"{m}_attribute_ordinal_position") or 0):
            link = a.get("link_to")
            if a["is_active"] and link and link.get("is_active", True):
                key = self.model.key(link, "parent_")
                parent = self.ledger.entities.get(key)
                if parent and not any(i["key"] == key and i["role"] == "lookup" for i in items):
                    items.append({"alias": alias_for(parent[f"{m}_entity_name"], taken), "role": "lookup", "key": key,
                                  "row": parent, "names": {f"{m}_entity_schema_name": parent[f"{m}_entity_schema_name"],
                                                           f"{m}_entity_name": parent[f"{m}_entity_name"]}})
                if self.model is GOLD:  # a Gold link is built from a Silver link: its Silver parent gives the natural key
                    for source in a["sources"]:
                        silver = self.silver.entities.get(source[:2])
                        silver_link = silver and silver["attributes"].get(source[2:3]) and silver["attributes"][source[2:3]].get("link_to")
                        parent_key = silver_link and SILVER.key(silver_link, "parent_")
                        if parent_key and parent_key in self.silver.entities and not any(i["key"] == parent_key for i in items):
                            s = self.silver.entities[parent_key]
                            items.append({"alias": alias_for(s["operational_entity_name"], taken), "role": "added",
                                          "key": parent_key, "row": s,
                                          "names": {"operational_entity_schema_name": s["operational_entity_schema_name"],
                                                    "operational_entity_name": s["operational_entity_name"]}})
        return items


def stored_tables(items):
    return [{"alias": i["alias"], "role": i["role"], **i["names"]} for i in items]


def attributes_of(model, e):
    m = model.m
    return sorted((a for a in e["attributes"].values() if a["is_active"]),
                  key=lambda a: a.get(f"{m}_attribute_ordinal_position") or 0)


def target_entity(ctx, e, items, saved, scd_type=None, lines_field="saved_line"):
    """The `target_entity` block: everything about one attribute in one row, sources and parents by alias."""
    m = ctx.model.m
    by_key = {i["key"]: i["alias"] for i in items if i["role"] == "source"}
    lookups = {i["key"]: i["alias"] for i in items if i["role"] == "lookup"}
    rows = []
    for a in attributes_of(ctx.model, e):
        sources, notes = [], []
        for key, s in a["sources"].items():
            if s.get("is_active", True) and key[:2] in by_key:
                sources.append({"alias": by_key[key[:2]], "attribute_name": key_name(s, ctx.model)})
                if s.get(f"{m}_attribute_source_note"):
                    notes.append(s[f"{m}_attribute_source_note"])
        link = a.get("link_to")
        line = (saved or {}).get("lines", {}).get(low(a[f"{m}_attribute_name"]))
        rows.append({f"{m}_attribute_name": a[f"{m}_attribute_name"],
                     f"{m}_attribute_data_type": a[f"{m}_attribute_data_type"],
                     "is_surrogate_key": a["is_surrogate_key"], "is_natural_key": a["is_natural_key"],
                     "is_nullable": a["is_nullable"], "sources": sources,
                     f"{m}_attribute_source_note": " ".join(notes) or None,
                     "link_to": lookups.get(ctx.model.key(link, "parent_")) if link and link.get("is_active", True) else None,
                     "map_in_this_call": not a["is_surrogate_key"],
                     lines_field: line[f"{m}_attribute_mapping_transformation"] if line else None,
                     "is_locked": bool(line and line["is_locked"])})
    head = {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
            f"{m}_entity_definition": e.get(f"{m}_entity_definition"), f"{m}_entity_grain": e.get(f"{m}_entity_grain"),
            "is_merged": e.get("is_merged"), "scd_type": scd_type or ctx.config.get(f"{m}_entity_scd_type")}
    fields = (f"{m}_attribute_name", f"{m}_attribute_data_type", "is_surrogate_key", "is_natural_key", "is_nullable",
              "sources", f"{m}_attribute_source_note", "link_to", "map_in_this_call", lines_field, "is_locked")
    return blocks.block("entity", head, rows, fields)


def key_name(source, model):
    """The column or Silver attribute a source row names."""
    return source["attribute_name"] if model is SILVER else source["operational_attribute_name"]


def mapping_tables(ctx, e, items, extra=None):
    """The `mapping_tables` blocks: each table or entity on the list with its alias and role. `extra` adds fields to
    each head line (validation adds the SQL name and batch column)."""
    m, out = ctx.model.m, []
    on_list = {i["key"]: i["alias"] for i in items if i["role"] == "source"}
    nk_sources = set()
    for i in items:
        if i["role"] == "lookup":
            for a in i["row"]["attributes"].values():
                if a["is_natural_key"] and a["is_active"]:
                    nk_sources |= set(a["sources"])
    for i in items:
        head = {"alias": i["alias"], "role": i["role"], **i["names"], **((extra or (lambda _: {}))(i))}
        if i["role"] == "lookup":
            out.append(lookup_block(ctx, i, head))
        elif ctx.model is SILVER:
            t = i["row"]
            head |= {k: t[k] for k in ("system_code", "row_count", "object_definition", "object_grain")}
            head["operational_entity_source_note"] = e["sources"][i["key"]].get("operational_entity_source_note")
            rows = []
            for c in ctx.columns(t):
                here = i["key"] + low(c["attribute_name"])
                rows.append(c | {"links_to": _links(ctx, here, "from", "to", on_list, nk_sources),
                                 "linked_from": _links(ctx, here, "to", "from", on_list, nk_sources)})
            out.append(blocks.block("table", head, rows, SOURCE_COLUMNS))
        else:
            s = i["row"]
            head |= {"operational_entity_definition": s.get("operational_entity_definition"),
                     "operational_entity_grain": s.get("operational_entity_grain"), "is_merged": s.get("is_merged"),
                     "dimensional_entity_source_note": e["sources"].get(i["key"], {}).get("dimensional_entity_source_note")}
            rows = [a | {"link_to": _target(a)} for a in attributes_of(SILVER, s)]
            out.append(blocks.block("entity", head, rows, ("operational_attribute_name", "operational_attribute_data_type",
                                                          "is_surrogate_key", "is_natural_key", "is_nullable",
                                                          "operational_attribute_definition", "link_to")))
    return "\n\n".join(out)


def _target(a):
    link = a.get("link_to")
    if not link or not link.get("is_active", True):
        return None
    return f"{link['parent_operational_entity_schema_name']}.{link['parent_operational_entity_name']}"


def _links(ctx, here, this_end, other_end, on_list, nk_sources):
    found = []
    for link in ctx.links:
        at = low(link[f"{this_end}_object_schema"], link[f"{this_end}_object_name"], link[f"{this_end}_attribute_name"])
        if at != here:
            continue
        other = low(link[f"{other_end}_object_schema"], link[f"{other_end}_object_name"])
        column = link[f"{other_end}_attribute_name"]
        facts = {"relationship_kind": link["relationship_kind"], "inferred_cardinality": link["inferred_cardinality"],
                 "validation_result": link["validation_result"]}
        if other in on_list:
            found.append({"alias": on_list[other], "attribute_name": column} | facts)
        elif other + low(column) in nk_sources:
            found.append({"object_schema": link[f"{other_end}_object_schema"],
                          "object_name": link[f"{other_end}_object_name"], "attribute_name": column} | facts)
    return found


def lookup_block(ctx, item, head):
    """A lookup: the parent entity with only its two keys; the natural key lists where its value comes from."""
    m, p = ctx.model.m, item["row"]
    head |= {"is_merged": p.get("is_merged"), "scd_type": ctx.config.get(f"{m}_entity_scd_type")}
    rows = []
    for a in attributes_of(ctx.model, p):
        if not (a["is_surrogate_key"] or a["is_natural_key"]):
            continue
        sources, notes = [], []
        for key, s in a["sources"].items():
            if not s.get("is_active", True):
                continue
            notes.append(s.get(f"{m}_attribute_source_note") or "")
            if ctx.model is SILVER and key[:2] in ctx.scope:
                t = ctx.scope[key[:2]]
                col = next((c for c in ctx.columns(t) if low(c["attribute_name"]) == key[2:]), None)
                sources.append({"object_schema": t["object_schema"], "object_name": t["object_name"],
                                "attribute_name": s["attribute_name"], "system_code": t["system_code"],
                                "attribute_data_type": col["attribute_data_type"] if col else None,
                                "sample_values": (col["sample_values"] if col else [])[:SAMPLES]})
            elif ctx.model is GOLD:
                sources.append({k: s[k] for k in ("operational_entity_schema_name", "operational_entity_name",
                                                  "operational_attribute_name")})
        rows.append({f"{m}_attribute_name": a[f"{m}_attribute_name"], f"{m}_attribute_data_type": a[f"{m}_attribute_data_type"],
                     "is_surrogate_key": a["is_surrogate_key"], "is_natural_key": a["is_natural_key"],
                     "sources": sources, f"{m}_attribute_source_note": " ".join(n for n in notes if n) or None})
    return blocks.block("entity", head, rows, (f"{m}_attribute_name", f"{m}_attribute_data_type", "is_surrogate_key",
                                               "is_natural_key", "sources", f"{m}_attribute_source_note"))


# --- The step ----------------------------------------------------------------------------------------------------


def picked_mappings(model):
    """Items: (entity key, system code), from `request["mappings"]`, or every active entity with each of its systems."""
    m = model.m

    def items(cur, project_id, request):
        ctx = Context(cur, project_id, model)
        wanted = request.get("mappings")
        if wanted:
            found = []
            for w in wanted:  # without a system_code: every system the entity has a source in
                e = ctx.ledger.get(w[f"{m}_entity_schema_name"], w[f"{m}_entity_name"])
                name = f"{w[f'{m}_entity_schema_name']}.{w[f'{m}_entity_name']}"
                run_005((e is None or not e["is_active"]) and f"{name} is not an active entity.")
                systems = [s for s in ctx.systems_of(e) if s.upper() == (w.get("system_code") or s).upper()]
                run_005(not systems and f"{name} has no source in {w.get('system_code') or 'any system'}.")
                found += [(model.key(e), s) for s in systems]
        else:
            found = [(k, s) for k, e in sorted(ctx.ledger.entities.items()) if e["is_active"] for s in ctx.systems_of(e)]
        run_005(not found and "There is no entity with a source to map yet.")
        for key, system in found:
            saved = ctx.mappings.get(key + low(system))
            run_005(saved is not None and saved["is_locked"] and f"The mapping of {'.'.join(key)} for {system} is locked.")
        return found

    return items


def label(model, ctx, item):
    e = ctx.ledger.entities[item[0]]
    return f"{e[f'{model.m}_entity_schema_name']}.{e[f'{model.m}_entity_name']} / {item[1]}"


def prepare(model):
    m = model.m

    def run(cur, run_row, items):
        ctx = Context(cur, run_row["project_id"], model)
        run_row["ctx"], run_row["plans"] = ctx, {}
        prepared = {}
        for key, system in items:
            e = ctx.ledger.entities[key]
            plan = ctx.plan(e, system)
            saved = ctx.mappings.get(key + low(system))
            name = label(model, ctx, (key, system))
            run_row["plans"][name] = (key, system, plan, saved)
            part = None
            if saved:
                part = {k: saved[k] for k in (f"{m}_object_mapping_row_filter", f"{m}_object_mapping_sample_query",
                                              f"{m}_object_mapping_transformation", "is_locked")}
            prepared[name] = {
                "context_records": prompts.context_records(cur, run_row["project_id"], f"{m}_mapping", [system]),
                "systems": blocks.systems(cur, run_row["project_id"], [system]),
                "target_entity": target_entity(ctx, e, plan, saved),
                "mapping_tables": mapping_tables(ctx, e, plan),
                "existing_mapping_part": blocks.as_json(part) if part else blocks.NONE,
            }
        return prepared, []

    return run


def records(model):
    m = model.m
    part_fields = (f"{m}_object_mapping_row_filter", f"{m}_object_mapping_sample_query", f"{m}_object_mapping_transformation")

    def run(cur, run_row, name, answer):
        ctx = run_row["ctx"]
        key, system, plan, saved = run_row["plans"][name]
        e = ctx.ledger.entities[key]
        owner = {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
                 "system_code": system}
        given = answer[f"{m}_object_mapping"]
        tables = stored_tables(plan)
        part = {f: given[f] for f in part_fields if given[f] is not None and (not saved or saved[f] != given[f])}
        if not saved or saved[f"{m}_object_mapping_tables"] != tables:
            part[f"{m}_object_mapping_tables"] = tables
        documents, notes = {}, []
        if part or not saved:
            documents[f"{m}_object_mapping"] = [owner | part]
        attributes = {low(a[f"{m}_attribute_name"]): a for a in attributes_of(model, e)}
        lines = []
        for line in answer["attributes"]:
            a = attributes.get(low(line[f"{m}_attribute_name"]))
            old = (saved or {}).get("lines", {}).get(low(line[f"{m}_attribute_name"]))
            if old and old["is_locked"]:
                notes.append(f"the line for {line[f'{m}_attribute_name']} is locked, left out (RUN-007).")
                continue
            if a is not None and a["is_surrogate_key"]:
                continue
            text = line[f"{m}_attribute_mapping_transformation"]
            if old and old[f"{m}_attribute_mapping_transformation"] == text and old["is_active"] == line["is_active"]:
                continue
            lines.append(owner | {f"{m}_attribute_name": a[f"{m}_attribute_name"] if a else line[f"{m}_attribute_name"],
                                  f"{m}_attribute_mapping_transformation": text, "is_active": line["is_active"]})
        if lines:
            documents[f"{m}_attribute_mapping"] = lines
        notes += [f"not mapped: {u[f'{m}_attribute_name']}: {u['reason']}" for u in answer["unmapped"]]
        return documents, notes

    return run


def answer_schema(model):
    m = model.m
    s, n = {"type": "string"}, {"type": ["string", "null"]}
    obj = lambda props: {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}  # noqa: E731
    return {"name": f"{m}_mapping", "schema": obj({
        f"{m}_object_mapping": obj({f"{m}_object_mapping_row_filter": n, f"{m}_object_mapping_sample_query": n,
                                    f"{m}_object_mapping_transformation": n}),
        "attributes": {"type": "array", "items": obj({f"{m}_attribute_name": s,
                                                      f"{m}_attribute_mapping_transformation": s,
                                                      "is_active": {"type": "boolean"}})},
        "unmapped": {"type": "array", "items": obj({f"{m}_attribute_name": s, "reason": s})}})}


INPUTS = {
    "context_records": "the tenant's mapping Notes: house standards such as how lookups are joined",
    "systems": "the tenant and the system this mapping reads; lookups find it in meta.system by its SystemCode",
    "target_entity": "the entity (block): one row per attribute with its type, marks, sources and parent by alias, "
                     "its note, whether this call maps it, and its saved line and lock",
    "mapping_tables": "the only tables and entities the mapping may use (blocks), each with its alias and role: "
                      "source, lookup (a parent entity, with only its two keys), or added (in Gold, the Silver parent "
                      "behind a Silver link, whose natural key finds the Gold parent)",
    "existing_mapping_part": "the saved mapping part with its lock, or none: a rerun builds on it",
}


def step(model):
    m = model.m
    return Step(workflow=f"{m}_mapping", title=f"{'Silver' if model is SILVER else 'Gold'} mapping", inputs=INPUTS,
                answer=answer_schema(model), items=picked_mappings(model), prepare=prepare(model),
                records=records(model))


STEPS = (step(SILVER), step(GOLD))
