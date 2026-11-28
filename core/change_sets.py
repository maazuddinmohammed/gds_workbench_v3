"""Project change sets: the one engine every change to a project goes through (step 4c2).

A hand edit, a Run and a push all make a draft change set: for each part (core/parts.py), a list of records. The draft
changes nothing until a person applies it. Then all of it is saved in one transaction, or nothing, and the project
version goes up by one.

How a draft is worked out: its records are saved on the project as it is now, part by part, parents first, inside a
transaction. That shows what each record does (added, changed, switched off or unchanged) and what the project would
look like after Apply, so the rules of docs/rules/ can be checked on it (core/rules.py). Validating and listing the
changes then roll that transaction back; Apply keeps it when no problem blocks it. So there is one way to work out a
draft, and Apply can never save something the review did not show.

Nothing is ever deleted: a record with `"is_active": false` switches its row off. A record that leaves a field out
keeps the saved value. Problems are never stored; they are worked out fresh each time (design/operations/change-sets.md).
"""

from decimal import Decimal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core import rules
from core.access import CHANGE, READ, require
from core.parts import PARTS
from core.problems import NotFound, Problem

LOCK_RESPECTING_SOURCES = ("ai_run", "vscode_push")  # CHANGE-SET-005: these may not change a locked row
PAGE_SIZE = 50
JSON_VALUES = {"validation_comparison_value"}  # a JSONB column that may hold a plain number or text


def make_draft(conn, principal_id, project_id, documents, title, source="web_app_edit", via_mcp=False):
    """Save `documents` ({part: [records]}) as a new draft on the project's current version, and return its id.

    Needs CHANGE, the tenant lock and an unlocked project. A document of the wrong shape is the caller's mistake
    (ValueError). Whether its records name real rows and keep the rules is worked out by `validate`, so a draft can
    be saved and its problems shown.
    """
    project = _project(conn, project_id)
    require(conn, principal_id, project["tenant_id"], CHANGE, project_id=project_id, via_mcp=via_mcp)
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        raise ValueError("a draft needs a title")
    return save_draft(conn, project_id, principal_id, documents, title, source, project["project_version"])


def save_draft(conn, project_id, principal_id, documents, title, source, base_version):
    """Save a draft with no access check: for a Run, which checked access when it started. Its draft is saved even
    if the tenant lock ended while it ran; Apply needs the lock."""
    documents = well_formed(documents)
    columns = [f"{part}_document" for part in documents]
    with conn.transaction():
        return conn.execute(
            f"""INSERT INTO application.project_change_set
                    (project_id, project_change_set_status, project_change_set_title, project_change_set_source,
                     base_project_version, created_by_principal_id{''.join(', ' + c for c in columns)})
                VALUES (%s, 'draft', %s, %s, %s, %s{', %s' * len(columns)})
                RETURNING project_change_set_id""",
            (project_id, title, source, base_version, principal_id,
             *[Jsonb(records) for records in documents.values()]),
        ).fetchone()[0]


def validate(conn, principal_id, change_set_id, via_mcp=False):
    """Every problem of the change set, worked out fresh, each with its rule ID. Changes nothing."""
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    return _work_out_and_undo(conn, draft)[1]


def get_change_set(conn, principal_id, change_set_id, via_mcp=False):
    """Where a change set stands: its status, who made it and how, the version it was built on and the project's
    version now, and for each part how many records add, change, switch off or leave a row unchanged."""
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    changes, _ = _work_out_and_undo(conn, draft)
    counts = {}
    for change in changes:
        part = counts.setdefault(change["part"], {"added": 0, "changed": 0, "switched_off": 0, "unchanged": 0})
        part[change["change"]] += 1
    return {**_summary(conn, change_set_id), "counts": counts}


def list_changes(conn, principal_id, change_set_id, part, change=None, page=1, via_mcp=False):
    """One part's records that add, change or switch off a row, 50 per page, with what is saved now next to each
    change. `change` keeps only one kind. Unchanged records are never listed."""
    if part not in PARTS:
        raise ValueError(f"unknown part {part!r}")
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    changes, _ = _work_out_and_undo(conn, draft)
    listed = [c for c in changes if c["part"] == part and c["change"] != "unchanged" and change in (None, c["change"])]
    start = (page - 1) * PAGE_SIZE
    return {"part": part, "page": page, "page_size": PAGE_SIZE, "total": len(listed),
            "changes": [{k: c[k] for k in ("change", "record", "current") if k in c}
                        for c in listed[start:start + PAGE_SIZE]]}


def list_change_sets(conn, principal_id, tenant_id, project_id=None, status=None, limit=None, via_mcp=False):
    """The tenant's project change sets, newest first, optionally for one project and one status."""
    require(conn, principal_id, tenant_id, READ, project_id=project_id, via_mcp=via_mcp)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT cs.project_change_set_id, p.project_name, cs.project_change_set_title,
                       cs.project_change_set_status, cs.project_change_set_source, cs.base_project_version,
                       p.project_version, c.principal_display_name AS created_by_display_name, cs.created_time,
                       d.principal_display_name AS decided_by_display_name, cs.decided_time
                  FROM application.project_change_set AS cs JOIN project.project AS p USING (project_id)
                  JOIN security.principal AS c ON c.principal_id = cs.created_by_principal_id
                  LEFT JOIN security.principal AS d ON d.principal_id = cs.decided_by_principal_id
                 WHERE p.tenant_id = %(t)s AND (%(p)s::bigint IS NULL OR p.project_id = %(p)s)
                   AND (%(s)s::text IS NULL OR cs.project_change_set_status = %(s)s)
                 ORDER BY cs.project_change_set_id DESC {'LIMIT %(n)s' if limit else ''}""",
            {"t": tenant_id, "p": project_id, "s": status, "n": limit},
        )
        return cur.fetchall()


def apply(conn, principal_id, change_set_id, via_mcp=False):
    """Apply: save the whole draft, or nothing. Returns the problems that stopped it; empty means applied.

    Needs CHANGE, the tenant lock (ACCESS-003) and an unlocked project (CHANGE-SET-004). The project and change set
    rows stay locked until the end, so two Applies at the same moment cannot both pass the version check
    (CHANGE-SET-002). Warnings never stop it. Then the change set is marked applied with who and when
    (CHANGE-SET-008), and the project version goes up by one.
    """
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    require(conn, principal_id, draft["tenant_id"], CHANGE, project_id=draft["project_id"], via_mcp=via_mcp)
    try:
        with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
            draft = _load(cur, change_set_id, for_update=True)
            _, problems = _work_out(cur, draft)
            blocking = [p for p in problems if p.level == "blocks_apply"]
            if blocking:
                raise _Undo(blocking)
            _decide(cur, principal_id, change_set_id, "applied")
            cur.execute(
                """UPDATE project.project SET project_version = project_version + 1,
                          updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                    WHERE project_id = %s""",
                (draft["project_id"],),
            )
    except _Undo as undone:
        return undone.result
    return []


def reject(conn, principal_id, change_set_id, via_mcp=False):
    """Reject: mark it rejected with who and when; nothing in the project changes. Returns the problems that
    stopped it; empty means rejected. A draft, or a change set still receiving, can be rejected (CHANGE-SET-001),
    also one built on an older version: that is how it is cleared."""
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    require(conn, principal_id, draft["tenant_id"], CHANGE, project_id=draft["project_id"], via_mcp=via_mcp)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        draft = _load(cur, change_set_id, for_update=True)
        problem = change_set_001(draft["status"], rejecting=True)
        if problem is not None:
            return [problem]
        _decide(cur, principal_id, change_set_id, "rejected")
    return []


def take_out(conn, principal_id, change_set_id, part, record, via_mcp=False):
    """Take one record out of a draft during review (C9), such as a link the reviewer does not want. The draft keeps
    the rest. Needs what Apply needs."""
    draft = _readable(conn, principal_id, change_set_id, via_mcp)
    require(conn, principal_id, draft["tenant_id"], CHANGE, project_id=draft["project_id"], via_mcp=via_mcp)
    if part not in PARTS:
        raise ValueError(f"unknown part {part!r}")
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        draft = _load(cur, change_set_id, for_update=True)
        problem = change_set_001(draft["status"])
        if problem:
            return [problem]
        records = draft["documents"].get(part) or []
        if not 0 <= record < len(records):
            raise ValueError(f"{part} has no record {record}")
        cur.execute(f"""UPDATE application.project_change_set SET {part}_document = {part}_document - %s,
                               updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                         WHERE project_change_set_id = %s""", (record, change_set_id))
    return []


def read_records(conn, principal_id, project_id, part, via_mcp=False):
    """The project's saved rows of one part, as records (the shape a draft uses), switched-off rows included."""
    if part not in PARTS:
        raise ValueError(f"unknown part {part!r}")
    project = _project(conn, project_id)
    require(conn, principal_id, project["tenant_id"], READ, project_id=project_id, via_mcp=via_mcp)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(PARTS[part].read, {"project_id": project_id})
        return [{k: v for k, v in row.items() if k != "id"} for row in cur.fetchall()]


# --- Working out a draft --------------------------------------------------------------------------------------------


class _Undo(Exception):
    """Leaves a transaction, rolling it back, and carries what was worked out inside it."""

    def __init__(self, result):
        self.result = result


def _work_out_and_undo(conn, draft):
    try:
        with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
            raise _Undo(_work_out(cur, draft))
    except _Undo as undone:
        return undone.result


def _work_out(cur, draft):
    """Save the draft's records on the project and return (changes, problems): one change per record that names a
    known row, in part order, and every problem in order: the whole draft, the records, then the rules."""
    project_id = draft["project_id"]
    problems = [problem for problem in (change_set_001(draft["status"]),
                                        change_set_002(draft["base_project_version"], draft["project_version"]))
                if problem is not None]
    changes, touched = [], {}
    for part in PARTS.values():
        records = draft["documents"].get(part.name) or []
        if not records:
            continue
        cur.execute(part.read, {"project_id": project_id})
        saved = {row.pop("id"): row for row in cur.fetchall()}
        seen = {}
        for index, record in enumerate(records):
            found = change_set_013(part, record, index, seen) or change_set_012(part, record, index)
            if found:
                problems.append(found)
                continue
            ids = _resolve(cur, part, record, project_id)
            if ids is None:
                problems.append(change_set_003(part, record, index))
                continue
            row_id = _row_id(cur, part, ids)
            change, current = _compare(part, record, saved.get(row_id))
            locked = change_set_005(draft["source"], part, record, saved.get(row_id), change, index)
            if locked:
                problems.append(locked)
            try:
                with cur.connection.transaction():
                    row_id = _save(cur, part, ids, record, row_id, change)
            except psycopg.errors.IntegrityError as error:
                problems.append(_database_problem(part, record, index, error))
                continue
            changes.append({"part": part.name, "index": index, "change": change, "record": record, "current": current})
            if row_id is not None:
                touched[(part.name, row_id)] = index
    for problem in rules.check(cur, project_id, set(draft["documents"]), touched):
        problems.append(problem)
    return changes, problems


def _resolve(cur, part, record, project_id):
    """The record's key and reference ids, or None when a name it gives is unknown (CHANGE-SET-003)."""
    columns = {**part.key, **{c: r for c, r in (part.refs or {}).items() if all(f in record for f in r[0])}}
    if not columns:
        return {}
    params = {field: record.get(field) for field in part.fields} | {"project_id": project_id}
    cur.execute("SELECT " + ", ".join(f"{sql} AS {column}" for column, (_, sql) in columns.items()), params)
    ids = cur.fetchone()
    for column, (fields, _) in columns.items():
        if ids[column] is None and (column in part.key or any(record[f] is not None for f in fields)):
            return None
    return ids


def _row_id(cur, part, ids):
    keys = list(part.key)
    cur.execute(f"SELECT {part.id_column} FROM {part.table} WHERE "
                + " AND ".join(f"{c} = %({c})s" for c in keys), {c: ids[c] for c in keys})
    row = cur.fetchone()
    return None if row is None else row[part.id_column]


def _compare(part, record, saved):
    """(change, current): what the record does to the saved row, and the saved values it changes."""
    if saved is None:
        return ("added" if record.get("is_active", True) else "unchanged"), None
    names = {f for fields, _ in (part.refs or {}).values() for f in fields}  # names compare ignoring case
    differ = {f: saved[f] for f in record
              if f in saved and f not in part.key_fields and not _same(saved[f], record[f], f in names)}
    if not differ:
        return "unchanged", None
    if record.get("is_active") is False and saved.get("is_active"):
        return "switched_off", differ
    return "changed", differ


def _same(saved, new, is_name):
    if isinstance(saved, Decimal) and isinstance(new, (int, float)):
        return float(saved) == float(new)
    if is_name and isinstance(saved, str) and isinstance(new, str):
        return saved.strip().lower() == new.strip().lower()
    return saved == new


def _save(cur, part, ids, record, row_id, change):
    """Write the record's fields on its row; add the row when it is new. Returns the row's id."""
    if change == "unchanged":
        return row_id
    values = {c: ids[c] for c in (part.refs or {}) if c in ids}
    values |= {f: Jsonb(record[f]) if isinstance(record[f], (list, dict)) or f in JSON_VALUES else record[f]
               for f in part.values if f in record}
    if row_id is None:
        values |= {c: ids[c] for c in part.key}
        cur.execute(f"INSERT INTO {part.table} ({', '.join(values)}) VALUES ({', '.join(f'%({c})s' for c in values)})"
                    f" RETURNING {part.id_column}", values)
        return cur.fetchone()[part.id_column]
    if values:
        cur.execute(f"UPDATE {part.table} SET {', '.join(f'{c} = %({c})s' for c in values)}, "
                    f"updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER "
                    f"WHERE {part.id_column} = %(row_id)s", values | {"row_id": row_id})
    return row_id


def _database_problem(part, record, index, error):
    constraint = getattr(error.diag, "constraint_name", None) or "a database check"
    return Problem("DATABASE", f"The database refused {_name(part, record)} ({constraint}): "
                               f"{error.diag.message_primary}.", index, part.name)


# --- The checks on the whole draft and each record, one per rule ----------------------------------------------------


def change_set_001(status, rejecting=False):
    """CHANGE-SET-001: Apply works only on a draft; Reject on a draft or a change set that is still receiving."""
    if status == "draft" or (rejecting and status == "receiving"):
        return None
    return Problem("CHANGE-SET-001", f"This change set is {status}, not a draft.")


def change_set_002(base_version, project_version):
    """CHANGE-SET-002: a project draft applies only on the version it was built on."""
    if base_version != project_version:
        return Problem(
            "CHANGE-SET-002",
            f"The draft was built on project version {base_version}, but the project is now at {project_version}. "
            "Make a new draft from the current project.",
        )
    return None


def change_set_003(part, record, index):
    """CHANGE-SET-003: a record that names a row, table or column which does not exist is a problem."""
    return Problem("CHANGE-SET-003", f"{_name(part, record)} names something that does not exist in this project.",
                   index, part.name)


def change_set_005(source, part, record, saved, change, index):
    """CHANGE-SET-005: a Run or a VS Code push cannot change a locked row. A hand edit in the web app can."""
    if source not in LOCK_RESPECTING_SOURCES or saved is None or not saved.get("is_locked") or change == "unchanged":
        return None
    return Problem("CHANGE-SET-005", f"{_name(part, record)} is locked. Unlock it by hand in the web app first, or "
                                     "take this change out.", index, part.name)


def change_set_012(part, record, index):
    """CHANGE-SET-012: a value that comes from a list is on that list."""
    for field, allowed in rules.LISTS.items():
        if field in record and record[field] is not None and record[field] not in allowed:
            return Problem("CHANGE-SET-012", f"{_name(part, record)}: {field} is {record[field]!r}; it must be one of "
                                             f"{', '.join(allowed)}.", index, part.name)
    return None


def change_set_013(part, record, index, seen):
    """CHANGE-SET-013: a draft names each row only once. `seen` collects the row keys of the part so far."""
    key = tuple(str(record.get(f, "")).strip().lower() for f in part.key_fields)
    if key in seen:
        return Problem("CHANGE-SET-013", f"{_name(part, record)} is in the draft twice (records {seen[key]} and "
                                         f"{index}).", index, part.name)
    seen[key] = index
    return None


# --- Helpers ---------------------------------------------------------------------------------------------------------


def _project(conn, project_id):
    row = conn.execute("SELECT tenant_id, project_version FROM project.project WHERE project_id = %s",
                       (project_id,)).fetchone()
    if row is None:
        raise NotFound("ACCESS-001", "Project not found.")
    return {"tenant_id": row[0], "project_version": row[1]}


def _readable(conn, principal_id, change_set_id, via_mcp):
    with conn.cursor(row_factory=dict_row) as cur:
        draft = _load(cur, change_set_id)
    require(conn, principal_id, draft["tenant_id"], READ, project_id=draft["project_id"], via_mcp=via_mcp)
    return draft


def _load(cur, change_set_id, for_update=False):
    """The change set with its documents and its project's tenant and current version, or NotFound (ACCESS-001)."""
    cur.execute(
        f"""SELECT cs.*, p.tenant_id, p.project_version
              FROM application.project_change_set AS cs JOIN project.project AS p USING (project_id)
             WHERE cs.project_change_set_id = %s {"FOR UPDATE OF p, cs" if for_update else ""}""",
        (change_set_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise NotFound("ACCESS-001", "Change set not found.")
    return {"project_id": row["project_id"], "tenant_id": row["tenant_id"], "project_version": row["project_version"],
            "status": row["project_change_set_status"], "source": row["project_change_set_source"],
            "base_project_version": row["base_project_version"],
            "documents": {name: row[f"{name}_document"] for name in PARTS if row[f"{name}_document"]}}


def _summary(conn, change_set_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT cs.project_change_set_id, t.tenant_code, p.project_name, cs.project_change_set_title,
                      cs.project_change_set_status, cs.project_change_set_source, cs.base_project_version,
                      p.project_version, p.is_locked, c.principal_display_name AS created_by_display_name,
                      cs.created_time, d.principal_display_name AS decided_by_display_name, cs.decided_time
                 FROM application.project_change_set AS cs JOIN project.project AS p USING (project_id)
                 JOIN core.tenant AS t ON t.tenant_id = p.tenant_id
                 JOIN security.principal AS c ON c.principal_id = cs.created_by_principal_id
                 LEFT JOIN security.principal AS d ON d.principal_id = cs.decided_by_principal_id
                WHERE cs.project_change_set_id = %s""",
            (change_set_id,),
        )
        return cur.fetchone()


def _decide(cur, principal_id, change_set_id, status):
    cur.execute(
        """UPDATE application.project_change_set
              SET project_change_set_status = %s, decided_by_principal_id = %s, decided_time = CURRENT_TIMESTAMP,
                  updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
            WHERE project_change_set_id = %s""",
        (status, principal_id, change_set_id),
    )


def well_formed(documents):
    """The documents, checked for shape: known parts, each a non-empty list of records with every key field."""
    if not isinstance(documents, dict) or not documents:
        raise ValueError("a draft needs at least one part with records")
    for part_name, records in documents.items():
        part = PARTS.get(part_name)
        if part is None:
            raise ValueError(f"unknown part {part_name!r}")
        if not isinstance(records, list) or not records:
            raise ValueError(f"{part_name}: records must be a non-empty list")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(f"{part_name} record {index} must be an object")
            unknown = set(record) - set(part.fields)
            missing = [f for f in part.key_fields if record.get(f) is None or str(record[f]).strip() == ""]
            if unknown or missing:
                raise ValueError(f"{part_name} record {index}: unknown fields {sorted(unknown)}, missing {missing}")
    return documents


def _name(part, record):
    return f"{part.name} {' / '.join(str(record.get(f)) for f in part.key_fields)}"

