"""The Silver (operational) and Gold (dimensional) model Runs: tool based, one subject area per Run
(design/workflows/silver-model.md, gold-model.md, and "The ledger and the tools" in design/overview/run.md).

When the Run starts, Python copies the saved model into the **ledger**, a working copy kept only in memory. The AI
reads it and writes its answer into it through tools, one entity at a time, until it answers without a tool call.
Then the ledger's changes become the draft. Each entity and attribute in the ledger has a `ledger_status`:
`unchanged`, `changed`, `new` or `switched_off`. Silver and Gold have the same shape, so one `Ledger` serves both;
`Model` says how they differ (where sources come from, the type field and the read tools).
"""

import copy
import json
from dataclasses import dataclass

from core import blocks, prompts
from core.ai import AIError
from core.parts import PARTS
from core.relationships import saved_links
from core.runs import Step, run_005

ENTITY_TYPES_SQL = """SELECT operational_entity_type_code, operational_entity_type_name, operational_entity_type_description
                        FROM reference.operational_entity_type WHERE is_active ORDER BY operational_entity_type_code"""


def low(*names):
    return tuple(str(n).strip().lower() for n in names)


@dataclass(frozen=True)
class Model:
    m: str  # operational or dimensional: the prefix of every column name
    workflow: str
    title: str
    type_field: str  # operational_entity_type_code, or dimensional_entity_type
    source_fields: tuple  # what names an entity source: a table (Silver) or a Silver entity (Gold)
    column_fields: tuple  # what names an attribute source

    def key(self, record, prefix=""):
        return low(record[f"{prefix}{self.m}_entity_schema_name"], record[f"{prefix}{self.m}_entity_name"])

    def name(self, record, prefix=""):
        return f"{record[f'{prefix}{self.m}_entity_schema_name']}.{record[f'{prefix}{self.m}_entity_name']}"


SILVER = Model("operational", "operational", "Silver model", "operational_entity_type_code",
               ("object_schema", "object_name"), ("object_schema", "object_name", "attribute_name"))
GOLD = Model("dimensional", "dimensional", "Gold model", "dimensional_entity_type",
             ("operational_entity_schema_name", "operational_entity_name"),
             ("operational_entity_schema_name", "operational_entity_name", "operational_attribute_name"))


# --- The ledger -------------------------------------------------------------------------------------------------------


class Ledger:
    """The saved model of one project, as a working copy the AI changes through tools. Never saved or reused."""

    def __init__(self, cur, project_id, model):
        self.model, m = model, model.m
        self.entities = {}  # key -> entity dict: fields, sources, attributes, link targets, ledger_status, flags
        read = lambda part: _read(cur, project_id, f"{m}_{part}")  # noqa: E731
        for e in read("entity"):
            self.entities[model.key(e)] = e | {"sources": {}, "attributes": {}, "ledger_status": "unchanged",
                                                "read": False, "saved": True}
        for s in read("entity_source"):
            self.entities[model.key(s)]["sources"][low(*(s[f] for f in model.source_fields))] = s
        for a in read("attribute"):
            self.entities[model.key(a)]["attributes"][low(a[f"{m}_attribute_name"])] = a | {
                "sources": {}, "link_to": None, "ledger_status": "unchanged", "saved": True}
        for s in read("attribute_source"):
            attr = self.entities[model.key(s)]["attributes"][low(s[f"{m}_attribute_name"])]
            attr["sources"][low(*(s[f] for f in model.column_fields))] = s
        for link in read("link"):
            attr = self.entities[model.key(link)]["attributes"][low(link[f"{m}_attribute_name"])]
            attr["link_to"] = link
        self.saved = copy.deepcopy(self.entities)  # the model as saved, to compare with at the end

    def get(self, schema, name):
        return self.entities.get(low(schema, name))

    def entity_row(self, e):
        m = self.model.m
        keys = [a[f"{m}_attribute_name"] for a in e["attributes"].values() if a["is_natural_key"] and a["is_active"]]
        return {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
                self.model.type_field: e.get(self.model.type_field), f"{m}_entity_definition": e.get(f"{m}_entity_definition"),
                "natural_key": keys, "is_active": e["is_active"], "ledger_status": e["ledger_status"]}

    def full(self, e):
        """An entity in full, as JSON: what get_entity_details and the prompt show. Marks it as read (RUN-007)."""
        e["read"] = True
        m = self.model.m
        skip = {"sources", "attributes", "read", "saved", "link_to"}
        return {**{k: v for k, v in e.items() if k not in skip},
                "sources": list(e["sources"].values()),
                "attributes": [{**{k: v for k, v in a.items() if k not in skip and not k.startswith(f"{m}_entity")},
                                "sources": [{k: v for k, v in s.items() if not k.startswith(f"{m}_") or k.endswith("_note")}
                                            for s in a["sources"].values()],
                                "link_to": _link_target(m, a["link_to"])}
                               for a in e["attributes"].values()]}


def _link_target(m, link):
    if not link or not link.get("is_active", True):
        return None
    return {f"{m}_entity_schema_name": link[f"parent_{m}_entity_schema_name"],
            f"{m}_entity_name": link[f"parent_{m}_entity_name"]}


def _read(cur, project_id, part):
    cur.execute(PARTS[part].read, {"project_id": project_id})
    return [{k: v for k, v in row.items() if k != "id"} for row in cur.fetchall()]


# --- The write tools: each changes the ledger, or answers with a short error and changes nothing --------------------


class ToolError(Exception):
    pass


def save_entity(ctx, args):
    ledger, model, m = ctx["ledger"], ctx["model"], ctx["model"].m
    schema, name = args[f"{m}_entity_schema_name"].strip(), args[f"{m}_entity_name"].strip()
    if low(schema) not in ctx["schemas"]:
        raise ToolError(f"{schema} is not one of the project's {model.title} schemas: {', '.join(ctx['schema_names'])}")
    if model is SILVER and args[model.type_field] not in ctx["types"]:
        raise ToolError(f"Unknown type code {args[model.type_field]}")
    sources = {}
    for s in args["sources"]:
        key = low(*(s[f] for f in model.source_fields))
        if key not in ctx["source_names"]:
            raise ToolError(f"No {'scope table' if model is SILVER else 'Silver entity'} {'.'.join(key)}")
        sources[key] = {f: ctx["source_names"][key][i] for i, f in enumerate(model.source_fields)} | {
            f"{m}_entity_source_note": s[f"{m}_entity_source_note"], "is_active": True}
    e = ledger.get(schema, name)
    if e is not None:
        _may_change(e, None, m)
    fields = {f: args[f] for f in (model.type_field, f"{m}_entity_definition", f"{m}_entity_grain", "is_merged")}
    if e is None:
        e = {f"{m}_entity_schema_name": schema, f"{m}_entity_name": name, "is_locked": False, "is_active": True,
             "attributes": {}, "sources": {}, "ledger_status": "new", "read": True, "saved": False}
        ledger.entities[low(schema, name)] = e
    for key, saved in e["sources"].items():
        if key not in sources and saved.get("is_locked"):
            sources[key] = saved  # a locked source stays
    e.update(fields)
    e["sources"] = {k: (e["sources"].get(k, {}) | v) for k, v in sources.items()}
    _touch(e)
    return {"saved": ledger.model.name(e), "sources": len(sources)}


def save_attributes(ctx, args):
    ledger, model, m = ctx["ledger"], ctx["model"], ctx["model"].m
    e = _entity(ledger, args, m)
    saved_names = []
    for a in args["attributes"]:
        name = a[f"{m}_attribute_name"].strip()
        attr = e["attributes"].get(low(name))
        _may_change(e, attr, m)
        if low(name) in ctx["audit"]:
            raise ToolError(f"{name} is an audit column the load adds; never model it")
        sources = {}
        for s in a["sources"]:
            key = low(*(s[f] for f in model.column_fields))
            if key not in ctx["column_names"]:
                raise ToolError(f"No column {'.'.join(key)}")
            sources[key] = {f: ctx["column_names"][key][i] for i, f in enumerate(model.column_fields)} | {
                f"{m}_attribute_source_note": s[f"{m}_attribute_source_note"], "is_active": True}
        link = a["link_to"]
        if link and ledger.get(link[f"{m}_entity_schema_name"], link[f"{m}_entity_name"]) is None:
            raise ToolError(f"No {model.title} entity {link[f'{m}_entity_schema_name']}.{link[f'{m}_entity_name']} "
                            "to link to: save it first")
        fields = {f: a[f] for f in (f"{m}_attribute_definition", f"{m}_attribute_data_type", "is_nullable",
                                    "is_surrogate_key", "is_natural_key")}
        if attr is None:
            attr = {f"{m}_attribute_name": name, "is_locked": False, "is_active": True, "sources": {}, "link_to": None,
                    "ledger_status": "new", "saved": False}
            e["attributes"][low(name)] = attr
        attr.update(fields)
        _touch(attr)
        attr["sources"] = {k: (attr["sources"].get(k, {}) | v) for k, v in sources.items()}
        attr["sources"] |= {k: s for k, s in (ledger.saved.get(ledger.model.key(e), {}).get("attributes", {})
                                              .get(low(name), {}).get("sources", {}).items())
                            if s.get("is_locked") and k not in attr["sources"]}  # a locked source stays
        if link:
            target = ledger.get(link[f"{m}_entity_schema_name"], link[f"{m}_entity_name"])
            attr["link_to"] = {f"parent_{m}_entity_schema_name": target[f"{m}_entity_schema_name"],
                               f"parent_{m}_entity_name": target[f"{m}_entity_name"], "is_active": True}
        elif attr["link_to"]:
            attr["link_to"] = attr["link_to"] | {"is_active": False}
        _touch(e)
        saved_names.append(name)
    return {"saved": saved_names}


def remove_entity(ctx, args):
    e = _entity(ctx["ledger"], args, ctx["model"].m)
    _may_change(e, None, ctx["model"].m)
    if not e["saved"]:
        del ctx["ledger"].entities[ctx["model"].key(args)]
        return {"dropped": ctx["model"].name(args)}
    e["is_active"], e["ledger_status"] = False, "switched_off"
    for a in e["attributes"].values():
        if not a["is_locked"]:
            a["is_active"], a["ledger_status"] = False, "switched_off"
    return {"switched_off": ctx["model"].name(args)}


def remove_attributes(ctx, args):
    m = ctx["model"].m
    e = _entity(ctx["ledger"], args, m)
    done = []
    for name in args["attribute_names"]:
        attr = e["attributes"].get(low(name))
        if attr is None:
            raise ToolError(f"{ctx['model'].name(args)} has no attribute {name}")
        _may_change(e, attr, m)
        if attr["saved"]:
            attr["is_active"], attr["ledger_status"] = False, "switched_off"
        else:
            del e["attributes"][low(name)]
        if e["ledger_status"] == "unchanged":
            e["ledger_status"] = "changed"
        done.append(name)
    return {"switched_off": done}


def _entity(ledger, args, m):
    e = ledger.get(args[f"{m}_entity_schema_name"], args[f"{m}_entity_name"])
    if e is None:
        raise ToolError(f"No entity {args[f'{m}_entity_schema_name']}.{args[f'{m}_entity_name']}: save_entity first")
    return e


def _may_change(e, attr, m):
    """The write is refused when a row is locked, was switched off by a person, or the entity was not read (RUN-007)."""
    name = e[f"{m}_entity_name"]
    if e["is_locked"]:
        raise ToolError(f"{name} is locked")
    if attr and attr["is_locked"]:
        raise ToolError(f"{name}.{attr[f'{m}_attribute_name']} is locked")
    if e["saved"] and not e["read"]:
        raise ToolError(f"{name} is saved and you have not read it in full: call get_entity_details first")
    for row in (e, attr):
        if row and row["saved"] and not row["is_active"] and row["ledger_status"] == "unchanged":
            raise ToolError(f"{name} was switched off by a person; never bring it back")


def _touch(row):
    """A row the AI saved: switched on, and changed (or new)."""
    row["is_active"] = True
    row["ledger_status"] = "changed" if row["saved"] else "new"


# --- The read tools --------------------------------------------------------------------------------------------------


def list_scope_tables(ctx, args):
    return blocks.rows(ctx["scope_rows"], ("object_schema", "object_name", "system_code", "object_definition",
                                           "object_grain", "subject_area_names"))


def get_table_details(ctx, args):
    table = ctx["scope"].get(low(args["object_schema"], args["object_name"]))
    if table is None:
        raise ToolError(f"No scope table {args['object_schema']}.{args['object_name']}")
    return table_block(ctx, table, samples=False)


def list_entities(ctx, args):
    model = SILVER if args["model"] == "operational" else GOLD
    ledger = ctx["ledgers"][model.m]
    return blocks.rows([ledger.entity_row(e) for e in sorted(ledger.entities.values(), key=lambda e: model.key(e))],
                       (f"{model.m}_entity_schema_name", f"{model.m}_entity_name", model.type_field,
                        f"{model.m}_entity_definition", "natural_key", "is_active", "ledger_status"))


def get_entity_details(ctx, args):
    model = SILVER if args["model"] == "operational" else GOLD
    e = ctx["ledgers"][model.m].get(args["entity_schema_name"], args["entity_name"])
    if e is None:
        raise ToolError(f"No {args['model']} entity {args['entity_schema_name']}.{args['entity_name']}")
    if model is SILVER and ctx["model"] is GOLD:
        return silver_block(e)
    return blocks.as_json(ctx["ledgers"][model.m].full(e))


def silver_block(e):
    """A Silver entity as Gold sees it: an entity line, then its active attributes as rows."""
    head = {k: e.get(k) for k in ("operational_entity_schema_name", "operational_entity_name", "operational_entity_type_code",
                                  "operational_entity_definition", "operational_entity_grain", "is_merged")}
    attrs = [a | {"link_to": _link_target("operational", a["link_to"])} for a in e["attributes"].values() if a["is_active"]]
    return blocks.block("entity", head, attrs, ("operational_attribute_name", "operational_attribute_data_type",
                                                "is_surrogate_key", "is_natural_key", "is_nullable",
                                                "operational_attribute_definition", "link_to"))


TOOLS = {"list_scope_tables": list_scope_tables, "get_table_details": get_table_details, "list_entities": list_entities,
         "get_entity_details": get_entity_details, "save_entity": save_entity, "save_attributes": save_attributes,
         "remove_entity": remove_entity, "remove_attributes": remove_attributes}


def tool_definitions(model):
    m = model.m
    s, n, b = {"type": "string"}, {"type": ["string", "null"]}, {"type": "boolean"}

    def obj(props, desc=None):
        return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props,
                **({"description": desc} if desc else {})}

    def fn(name, description, props):
        return {"type": "function", "name": name, "description": description, "strict": True, "parameters": obj(props)}

    ent = {f"{m}_entity_schema_name": s, f"{m}_entity_name": s}
    entity_source = obj({**{f: s for f in model.source_fields}, f"{m}_entity_source_note": n})
    column_source = obj({**{f: s for f in model.column_fields}, f"{m}_attribute_source_note": n})
    type_prop = ({"type": "string", "description": "one of the entity type codes"} if model is SILVER
                 else {"type": "string", "enum": ["fact", "dimension"]})
    attribute = obj({f"{m}_attribute_name": s, f"{m}_attribute_definition": s, f"{m}_attribute_data_type": s,
                     "is_nullable": b, "is_surrogate_key": b, "is_natural_key": b,
                     "sources": {"type": "array", "items": column_source},
                     "link_to": {"anyOf": [obj(ent), {"type": "null"}]}})
    tools = [
        fn("list_entities", "Every entity of a model, switched-off ones included, one row each.",
           {"model": {"type": "string", "enum": ["operational", "dimensional"] if model is GOLD else ["operational"]}}),
        fn("get_entity_details", "One entity in full. Read a saved entity this way before changing or linking to it.",
           {"model": {"type": "string", "enum": ["operational", "dimensional"] if model is GOLD else ["operational"]},
            "entity_schema_name": s, "entity_name": s}),
        fn("save_entity", "Make an entity, or replace a saved one's fields and its complete list of sources. "
                          "Attributes are saved with save_attributes.",
           {**ent, model.type_field: type_prop, f"{m}_entity_definition": s, f"{m}_entity_grain": s, "is_merged": b,
            "sources": {"type": "array", "items": entity_source}}),
        fn("save_attributes", "Make or replace attributes of a saved entity, matched by name. About 50 per call.",
           {**ent, "attributes": {"type": "array", "items": attribute}}),
        fn("remove_entity", "Drop a new entity, or switch a saved one off with its attributes.", ent),
        fn("remove_attributes", "Drop new attributes, or switch saved ones off.",
           {**ent, "attribute_names": {"type": "array", "items": s}}),
    ]
    if model is SILVER:
        tools = [fn("list_scope_tables", "Every scope table, one row each, with its areas.", {}),
                 fn("get_table_details", "One scope table with its business columns and every link, without samples.",
                    {"object_schema": s, "object_name": s})] + tools
    return tools


def call_tool(ctx, name, arguments):
    """Run one tool call and return its answer as text; an error is a short message and changes nothing."""
    try:
        args = json.loads(arguments)
    except (ValueError, TypeError):
        return json.dumps({"error": "Cut off: save fewer attributes per call"})
    try:
        answer = TOOLS[name](ctx, args)
    except ToolError as error:
        return json.dumps({"error": str(error)})
    ctx["counts"]["writes" if name.startswith(("save", "remove")) else "reads"] += 1
    return answer if isinstance(answer, str) else json.dumps(answer)


# --- Preparing the context ---------------------------------------------------------------------------------------


AREA_COLUMNS = ("attribute_name", "attribute_data_type", "attribute_inferred_data_type", "is_natural_key",
                "is_surrogate_key", "is_foreign_key_candidate", "is_nullable", "null_count", "blank_count",
                "distinct_count", "attribute_definition", "sample_values", "links_to", "linked_from")
RELATED_COLUMNS = ("attribute_name", "attribute_data_type", "attribute_inferred_data_type", "is_natural_key",
                   "is_surrogate_key", "attribute_definition")


def table_block(ctx, table, samples=True, area=None, only=None):
    """A scope table as the Silver model sees it: its business columns with their links (design/workflows/
    silver-model.md). `area` leaves out foreign keys that come in from outside the area; `only` keeps only those
    columns and shows no counts or samples (a related table)."""
    t = (table["object_schema"].lower(), table["object_name"].lower())
    cols = [c for c in ctx["columns"](table) if not c["is_meta_data"]]
    rows = []
    for c in cols:
        here = t + (c["attribute_name"].lower(),)
        out = [_end(link, "to") for link in ctx["links"] if _at(link, "from") == here]
        inn = [_end(link, "from") for link in ctx["links"] if _at(link, "to") == here
               and not (area is not None and link["relationship_kind"] == "foreign_key"
                        and (link["from_object_schema"].lower(), link["from_object_name"].lower()) not in area)]
        if only is not None and c["attribute_name"].lower() not in only:
            continue
        rows.append(c | {"links_to": out, "linked_from": inn, "sample_values": c["sample_values"] if samples else []})
    head = {k: table[k] for k in ("object_schema", "object_name", "system_code", "row_count", "object_definition",
                                  "object_grain")}
    return blocks.block("table", head, rows, RELATED_COLUMNS if only is not None else AREA_COLUMNS)


def _at(link, end):
    return (link[f"{end}_object_schema"].lower(), link[f"{end}_object_name"].lower(), link[f"{end}_attribute_name"].lower())


def _end(link, end):
    return {"object_schema": link[f"{end}_object_schema"], "object_name": link[f"{end}_object_name"],
            "attribute_name": link[f"{end}_attribute_name"], "relationship_kind": link["relationship_kind"],
            "inferred_cardinality": link["inferred_cardinality"], "validation_result": link["validation_result"]}


def _area(cur, project_id, request):
    name = (request.get("subject_area_name") or "").strip()
    cur.execute(PARTS["subject_area"].read, {"project_id": project_id})
    area = next((a for a in cur.fetchall() if a["subject_area_name"].lower() == name.lower() and a["is_active"]), None)
    run_005(area is None and f"No active subject area {name!r}. Pick one.")
    cur.execute(PARTS["subject_area_table"].read, {"project_id": project_id})
    tables = [t for t in cur.fetchall() if t["subject_area_name"] == area["subject_area_name"] and t["is_active"]]
    run_005(not tables and f"{area['subject_area_name']} has no tables.")
    return area, {(t["object_schema"].lower(), t["object_name"].lower()) for t in tables}


def _config(cur, project_id):
    cur.execute("SELECT * FROM project.project_config WHERE project_id = %s", (project_id,))
    return cur.fetchone() or {}


def silver_items(cur, project_id, request):
    area, _ = _area(cur, project_id, request)
    run_005(not _config(cur, project_id).get("operational_schemas") and "The project has no Silver schema.")
    return [area["subject_area_name"]]


def _context(cur, run, model):
    """What both model Runs share: the scope, its links, the ledgers and the project settings."""
    project_id = run["project_id"]
    scope = blocks.scope_tables(cur, project_id)
    config = _config(cur, project_id)
    cache = {}

    def columns(table):
        if table["object_id"] not in cache:
            cache[table["object_id"]] = blocks.columns(cur, project_id, table["object_id"])
        return cache[table["object_id"]]

    ledgers = {"operational": Ledger(cur, project_id, SILVER)}
    if model is GOLD:
        ledgers["dimensional"] = Ledger(cur, project_id, GOLD)
    schemas = config.get(f"{model.m}_schemas") or []
    cur.execute(ENTITY_TYPES_SQL)
    types = cur.fetchall()
    return {"model": model, "ledger": ledgers[model.m], "ledgers": ledgers, "columns": columns,
            "scope": {low(t["object_schema"], t["object_name"]): t for t in scope}, "scope_list": scope,
            "links": [link for link in saved_links(cur, project_id) if link["is_active"]], "config": config,
            "schemas": {low(s["schema_name"]) for s in schemas}, "schema_names": [s["schema_name"] for s in schemas],
            "types": {t["operational_entity_type_code"] for t in types}, "type_rows": types,
            "audit": {low(c["name"]) for c in (config.get(f"{model.m}_audit_columns") or [])} | {low("SourceSystemID")},
            "counts": {"reads": 0, "writes": 0}}


def silver_prepare(cur, run, items):
    ctx = _context(cur, run, SILVER)
    area, area_keys = _area(cur, run["project_id"], run["run_request_document"])
    ledger = ctx["ledger"]
    in_area = [t for k, t in ctx["scope"].items() if k in area_keys]
    related_keys = {}
    for link in ctx["links"]:
        for here, there in (("from", "to"), ("to", "from")):
            if (link[f"{here}_object_schema"].lower(), link[f"{here}_object_name"].lower()) in area_keys:
                key = (link[f"{there}_object_schema"].lower(), link[f"{there}_object_name"].lower())
                if key not in area_keys and key in ctx["scope"]:
                    related_keys.setdefault(key, set()).add(link[f"{there}_attribute_name"].lower())
    for key in related_keys:  # a related table also shows its keys
        related_keys[key] |= {c["attribute_name"].lower() for c in ctx["columns"](ctx["scope"][key])
                              if c["is_natural_key"] or c["is_surrogate_key"]}
    existing = [e for e in ledger.entities.values() if any(k in area_keys for k in e["sources"])]
    linked = {ledger.model.key(a["link_to"], "parent_") for e in existing for a in e["attributes"].values()
              if a["link_to"]}
    related = [e for k, e in ledger.entities.items() if e not in existing and
               (k in linked or any(s in related_keys for s in e["sources"]))]
    names = {}
    for t in ctx["scope_list"]:
        names.setdefault(low(t["object_schema"], t["object_name"]), t)
    ctx["source_names"] = {k: (t["object_schema"], t["object_name"]) for k, t in names.items()}
    ctx["column_names"] = _column_names(ctx)
    cur.execute(PARTS["subject_area_table"].read, {"project_id": run["project_id"]})
    areas_of = {}
    for row in cur.fetchall():
        if row["is_active"]:
            areas_of.setdefault(low(row["object_schema"], row["object_name"]), []).append(row["subject_area_name"])
    ctx["scope_rows"] = [t | {"subject_area_names": areas_of.get(k, [])} for k, t in ctx["scope"].items()]
    systems = sorted({t["system_code"] for t in in_area} | {ctx["scope"][k]["system_code"] for k in related_keys})
    run["ctx"] = ctx
    inputs = {
        "operational_schemas": blocks.rows(ctx["config"].get("operational_schemas") or [], ("schema_name", "description")),
        "operational_naming_instructions": ctx["config"].get("operational_naming_instructions") or blocks.NONE,
        "operational_audit_columns": blocks.rows(ctx["config"].get("operational_audit_columns") or [],
                                                 ("name", "data_type", "nullable", "definition")),
        "operational_entity_types": blocks.rows(ctx["type_rows"], ("operational_entity_type_code",
                                                                   "operational_entity_type_name",
                                                                   "operational_entity_type_description")),
        "context_records": prompts.context_records(cur, run["project_id"], "operational", systems),
        "systems": blocks.systems(cur, run["project_id"], systems),
        "subject_area": blocks.as_json({k: area[k] for k in ("subject_area_name", "subject_area_definition")}),
        "area_tables": "\n\n".join(table_block(ctx, t, area=area_keys) for t in in_area),
        "related_tables": "\n\n".join(table_block(ctx, ctx["scope"][k], samples=False, only=cols)
                                      for k, cols in sorted(related_keys.items())) or blocks.NONE,
        "existing_operational_entities": blocks.as_json([ledger.full(e) for e in existing]) if existing else blocks.NONE,
        "related_operational_entities": blocks.rows([ledger.entity_row(e) for e in related],
                                                    ("operational_entity_schema_name", "operational_entity_name",
                                                     "operational_entity_type_code", "operational_entity_definition",
                                                     "natural_key", "is_active", "ledger_status")),
    }
    return {area["subject_area_name"]: inputs}, [f"{len(in_area)} area tables, {len(related_keys)} related tables, "
                                                 f"{len(existing)} existing and {len(related)} related entities."]


def _column_names(ctx):
    names = {}
    for key, t in ctx["scope"].items():
        for c in ctx["columns"](t):
            names[key + low(c["attribute_name"])] = (t["object_schema"], t["object_name"], c["attribute_name"])
    return names


def gold_items(cur, project_id, request):
    area, area_keys = _area(cur, project_id, request)
    run_005(not _config(cur, project_id).get("dimensional_schemas") and "The project has no Gold schema.")
    ledger = Ledger(cur, project_id, SILVER)
    run_005(not any(e["is_active"] and any(k in area_keys for k in e["sources"]) for e in ledger.entities.values())
            and f"{area['subject_area_name']} has no Silver entities yet: run the Silver model for it first.")
    return [area["subject_area_name"]]


def gold_prepare(cur, run, items):
    ctx = _context(cur, run, GOLD)
    area, area_keys = _area(cur, run["project_id"], run["run_request_document"])
    silver, gold = ctx["ledgers"]["operational"], ctx["ledger"]
    own = [e for e in silver.entities.values() if e["is_active"] and any(k in area_keys for k in e["sources"])]
    own_keys = {SILVER.key(e) for e in own}
    near = {SILVER.key(a["link_to"], "parent_") for e in own for a in e["attributes"].values()
            if a["link_to"] and a["link_to"].get("is_active", True)}
    near |= {SILVER.key(e) for e in silver.entities.values() if e["is_active"] and any(
        a["link_to"] and SILVER.key(a["link_to"], "parent_") in own_keys for a in e["attributes"].values())}
    related = [silver.entities[k] for k in sorted(near - own_keys) if k in silver.entities]
    existing = [e for e in gold.entities.values() if any(k in own_keys for k in e["sources"])]
    related_gold = [e for e in gold.entities.values() if e not in existing and
                    any(k in near for k in e["sources"])]
    ctx["source_names"] = {SILVER.key(e): (e["operational_entity_schema_name"], e["operational_entity_name"])
                           for e in silver.entities.values() if e["is_active"]}
    ctx["column_names"] = {SILVER.key(e) + low(a["operational_attribute_name"]):
                           (e["operational_entity_schema_name"], e["operational_entity_name"],
                            a["operational_attribute_name"])
                           for e in silver.entities.values() for a in e["attributes"].values() if a["is_active"]}
    run["ctx"] = ctx
    cfg = ctx["config"]
    inputs = {
        "dimensional_schemas": blocks.rows(cfg.get("dimensional_schemas") or [], ("schema_name", "description")),
        "dimensional_naming_instructions": cfg.get("dimensional_naming_instructions") or blocks.NONE,
        "dimensional_audit_columns": blocks.rows(cfg.get("dimensional_audit_columns") or [],
                                                 ("name", "data_type", "nullable", "definition")),
        "dimensional_entity_scd_type": cfg.get("dimensional_entity_scd_type") or blocks.NONE,
        "operational_entity_scd_type": cfg.get("operational_entity_scd_type") or blocks.NONE,
        "context_records": prompts.context_records(cur, run["project_id"], "dimensional", []),
        "subject_area": blocks.as_json({k: area[k] for k in ("subject_area_name", "subject_area_definition")}),
        "operational_entities": "\n\n".join(silver_block(e) for e in own),
        "related_operational_entities": "\n\n".join(silver_block(e) for e in related) or blocks.NONE,
        "existing_dimensional_entities": blocks.as_json([gold.full(e) for e in existing]) if existing else blocks.NONE,
        "related_dimensional_entities": blocks.rows([gold.entity_row(e) for e in related_gold],
                                                    ("dimensional_entity_schema_name", "dimensional_entity_name",
                                                     "dimensional_entity_type", "dimensional_entity_definition",
                                                     "natural_key", "is_active", "ledger_status")),
    }
    return {area["subject_area_name"]: inputs}, [f"{len(own)} Silver entities in the area, {len(related)} related, "
                                                 f"{len(existing)} existing and {len(related_gold)} related Gold entities."]


# --- The Run: the tool loop, then the ledger's changes become the draft ---------------------------------------------


def run_tools(cur, run, prompt, prepared, call, log):
    """Work through tools until the AI answers without one. Returns (documents, why it stopped or None)."""
    step = STEPS[run["project_workflow"]]
    ctx = run["ctx"]
    model = ctx["model"]
    [(area_name, inputs)] = prepared.items()
    system, user = prompts.build(prompt, step.inputs, inputs, run["extra_instructions"])
    log("build_prompt", "completed", f"Prompt version {prompt['prompt_version_id']}.")
    tools = tool_definitions(model)
    stop, turns, summary = None, 0, None
    try:
        response = call([{"role": "system", "content": system}, {"role": "user", "content": user}], tools=tools)
        while True:
            calls = [o for o in response.output if o.type == "function_call"]
            if not calls:
                summary = response.output_text
                break
            turns += 1
            if turns > run["max_turns"]:
                stop = f"Stopped at the turn limit ({run['max_turns']} turns). Apply this draft and run the area again."
                break
            outputs = [{"type": "function_call_output", "call_id": c.call_id, "output": call_tool(ctx, c.name, c.arguments)}
                       for c in calls]
            if turns % 5 == 0:
                log("ai_call", "completed", f"Turn {turns}: {ctx['counts']['reads']} reads, {ctx['counts']['writes']} writes.")
            response = call(outputs, tools=tools, previous_response_id=response.id)
    except AIError as error:
        stop = f"Stopped: {error} The draft keeps what was saved so far."
    log("ai_call", "completed", f"{turns} turns, {ctx['counts']['reads']} reads, {ctx['counts']['writes']} writes."
        + (f" Summary: {summary.strip()}" if summary else ""))
    return to_documents(ctx["ledger"]), stop


def to_documents(ledger):
    """The ledger's real differences from what is saved, as draft records. Short lists are complete: a saved source
    missing from an entity or attribute is switched off."""
    model, m = ledger.model, ledger.model.m
    docs = {f"{m}_{p}": [] for p in ("entity", "attribute", "entity_source", "attribute_source", "link")}
    for key, e in ledger.entities.items():
        if e["ledger_status"] == "unchanged":
            continue
        ent = {f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"]}
        before = ledger.saved.get(key)
        fields = (model.type_field, f"{m}_entity_definition", f"{m}_entity_grain", "is_merged", "is_active")
        changed = {f: e.get(f) for f in fields if before is None or before.get(f) != e.get(f)}
        if changed:
            docs[f"{m}_entity"].append(ent | changed)
        docs[f"{m}_entity_source"] += _list_changes(e["sources"], (before or {}).get("sources", {}), ent,
                                                    model.source_fields, f"{m}_entity_source_note")
        position = max([a.get(f"{m}_attribute_ordinal_position") or 0 for a in e["attributes"].values()] + [0])
        for akey, a in e["attributes"].items():
            if a["ledger_status"] == "unchanged":
                continue
            attr = ent | {f"{m}_attribute_name": a[f"{m}_attribute_name"]}
            old = (before or {}).get("attributes", {}).get(akey)
            fields = (f"{m}_attribute_definition", f"{m}_attribute_data_type", "is_nullable", "is_surrogate_key",
                      "is_natural_key", "is_active")
            changed = {f: a.get(f) for f in fields if old is None or old.get(f) != a.get(f)}
            if old is None:
                position += 1
                changed[f"{m}_attribute_ordinal_position"] = position
            if changed:
                docs[f"{m}_attribute"].append(attr | changed)
            docs[f"{m}_attribute_source"] += _list_changes(a["sources"], (old or {}).get("sources", {}), attr,
                                                           model.column_fields, f"{m}_attribute_source_note")
            link, old_link = a["link_to"], (old or {}).get("link_to")
            if link and (old_link is None or _link_target(m, old_link) != _link_target(m, link)
                         or old_link.get("is_active") != link.get("is_active", True)):
                docs[f"{m}_link"].append(attr | {k: v for k, v in link.items() if k.startswith("parent_")}
                                         | {"is_active": link.get("is_active", True)})
    return {part: records for part, records in docs.items() if records}


def _list_changes(now, before, owner, name_fields, note):
    out = []
    for key, s in now.items():
        old = before.get(key)
        if old is None or old.get(note) != s.get(note) or not old.get("is_active", True):
            out.append(owner | {f: s[f] for f in name_fields} | {note: s.get(note), "is_active": True})
    for key, s in before.items():
        if key not in now and s.get("is_active", True) and not s.get("is_locked"):
            out.append(owner | {f: s[f] for f in name_fields} | {"is_active": False})
    return out


SILVER_INPUTS = {
    "operational_schemas": "the project's Silver schemas (rows): every entity goes in one",
    "operational_naming_instructions": "the project's naming style for entities and attributes",
    "operational_audit_columns": "the columns the load adds to every entity (rows): never model them or reuse their names",
    "operational_entity_types": "the entity types (rows): every entity gets one code",
    "context_records": "the tenant's Notes: modeling rules, the KPIs the model must support, facts about the systems",
    "systems": "the tenant and the systems of the tables below",
    "subject_area": "the area this Run builds: its name and boundary",
    "area_tables": "the area's tables (blocks): every business column with its definition, marks, counts, samples "
                   "and links (links_to: links that start at the column; linked_from: links that end at it)",
    "related_tables": "tables outside the area at the other end of those links (blocks), with only their keys and "
                      "linking columns: enough to link to them, not to model them",
    "existing_operational_entities": "in full (JSON), every saved entity built from an area table, with its locks: "
                                     "build on these, never a second copy",
    "related_operational_entities": "one row per other entity the area links to or is built from a related table: "
                                    "link to these; read one in full before changing it",
}
GOLD_INPUTS = {
    "dimensional_schemas": "the project's Gold schemas (rows): every entity goes in one",
    "dimensional_naming_instructions": "the project's naming style for facts, dimensions and attributes",
    "dimensional_audit_columns": "the columns the load adds to every Gold entity (rows), history columns included: "
                                 "never model them",
    "dimensional_entity_scd_type": "whether Gold keeps history (type_2) or not (type_1)",
    "operational_entity_scd_type": "whether Silver keeps history",
    "context_records": "the tenant's Notes: grains and shared dimensions, measures, what reports slice by",
    "subject_area": "the area this Run builds: its name and boundary",
    "operational_entities": "the Silver entities built from the area's tables (blocks): Gold's only sources",
    "related_operational_entities": "the Silver entities one link away (blocks), such as shared dimensions' sources",
    "existing_dimensional_entities": "in full (JSON), the saved Gold entities built from the area's Silver entities: "
                                     "build on these",
    "related_dimensional_entities": "one row per other Gold entity built from the related Silver entities: link to "
                                    "these, never make a second one",
}

STEPS = {
    "operational": Step(workflow="operational", title="Silver model", inputs=SILVER_INPUTS, answer=None,
                        items=silver_items, prepare=silver_prepare, records=None, mode="tool_assisted",
                        run_tools=run_tools),
    "dimensional": Step(workflow="dimensional", title="Gold model", inputs=GOLD_INPUTS, answer=None,
                        items=gold_items, prepare=gold_prepare, records=None, mode="tool_assisted",
                        run_tools=run_tools),
}
