"""Load order: the order a model's entities must load in, parents first, worked out from the links without AI
(design/workflows/silver-model.md, "Load order"). It writes a draft like every change; a person can also edit the
order by hand. A link from an entity to itself is ignored. Entities in a loop are named and ordered by name after
the others. A locked entity keeps its order.
"""

from psycopg.rows import dict_row

from core import change_sets
from core.access import CHANGE, require
from core.models import GOLD, SILVER, Ledger
from core.problems import NotFound


def work_out(ledger):
    """({entity key: order from 1}, entities in a loop): every active entity after all its parents."""
    m = ledger.model.m
    active = {k: e for k, e in ledger.entities.items() if e["is_active"]}
    parents = {k: {ledger.model.key(a["link_to"], "parent_") for a in e["attributes"].values()
                   if a["is_active"] and a["link_to"] and a["link_to"].get("is_active", True)} & active.keys() - {k}
               for k, e in active.items()}
    order, placed = {}, set()
    while len(placed) < len(active):
        ready = sorted(k for k in active if k not in placed and parents[k] <= placed)
        if not ready:
            break
        for k in ready:
            order[k] = len(order) + 1
        placed |= set(ready)
    loop = sorted(k for k in active if k not in placed)
    for k in loop:
        order[k] = len(order) + 1
    return order, [f"{active[k][f'{m}_entity_schema_name']}.{active[k][f'{m}_entity_name']}" for k in loop]


def make_draft(conn, principal_id, project_id, model_name, via_mcp=False):
    """A draft with the worked-out load order of the Silver (`operational`) or Gold (`dimensional`) model. Returns
    (change set id or None when nothing changes, entities in a loop)."""
    model = SILVER if model_name == "operational" else GOLD
    m = model.m
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM project.project WHERE project_id = %s AND is_active", (project_id,))
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        require(conn, principal_id, project["tenant_id"], CHANGE, project_id=project_id, via_mcp=via_mcp)
        ledger = Ledger(cur, project_id, model)
    order, loop = work_out(ledger)
    records = [{f"{m}_entity_schema_name": e[f"{m}_entity_schema_name"], f"{m}_entity_name": e[f"{m}_entity_name"],
                f"{m}_entity_dependency_order": order[k]}
               for k, e in sorted(ledger.entities.items())
               if k in order and not e["is_locked"] and e.get(f"{m}_entity_dependency_order") != order[k]]
    if not records:
        return None, loop
    title = f"{'Silver' if model is SILVER else 'Gold'} load order"
    return change_sets.make_draft(conn, principal_id, project_id, {f"{m}_entity": records}, title, via_mcp=via_mcp), loop
