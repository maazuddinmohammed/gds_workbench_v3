"""Project change sets: making, checking, applying and rejecting a scope draft (steps 3d1 to 3d3).

A scope draft holds only the changes: one record per table to add, switch off, switch on, lock or unlock. Nothing is
ever deleted; taking a table out of scope switches its row off (SCOPE-004). Each record names its table by row key
only, in words, never by database id (CHANGE-SET-003):

    {"tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
     "object_schema": "bronze_erp", "object_name": "orders", "is_active": true, "is_locked": false}

The first five fields are the table's row key (its connection's tenant, system and code, then schema and name).
`is_active` and `is_locked` are the values to set on the project's scope row for that table; they are not part of
the key. Making a draft changes nothing in the project. Checking it returns every problem at once, each with its
rule ID, so a person can fix them all in one go.
"""

from dataclasses import dataclass
from datetime import datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from core.access import CHANGE, READ, require
from core.catalog import scope_001, scope_002
from core.problems import NotFound, Problem

KEY_FIELDS = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")
VALUE_FIELDS = ("is_active", "is_locked")
RECORD_FIELDS = KEY_FIELDS + VALUE_FIELDS
LOCK_RESPECTING_SOURCES = ("ai_run", "vscode_push")  # CHANGE-SET-005: these may not change a locked row


def make_scope_draft(conn, principal_id, project_id, records, title, via_mcp=False):
    """Save `records` as a new draft change set for the project's scope, and return its id.

    Needs CHANGE on the project's tenant, the tenant lock (ACCESS-003), and the project not locked (CHANGE-SET-004).
    A record of the wrong shape is a mistake by the caller and raises ValueError. Whether the tables exist and may
    be in scope is checked by `check_scope_draft`, so a draft can be saved and its problems shown.
    """
    project = _project(conn, project_id)
    require(conn, principal_id, project["tenant_id"], CHANGE, project_id=project_id, via_mcp=via_mcp)
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        raise ValueError("a draft needs a title")
    records = _well_formed(records)
    with conn.transaction():
        return conn.execute(
            """INSERT INTO application.project_change_set
                   (project_id, project_change_set_status, project_change_set_title, project_change_set_source,
                    base_project_version, project_input_scope_document, created_by_principal_id)
               VALUES (%s, 'draft', %s, 'web_app_edit', %s, %s, %s)
               RETURNING project_change_set_id""",
            (project_id, title, project["project_version"], Jsonb(records), principal_id),
        ).fetchone()[0]


def check_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    """Every problem in a scope draft, as a list (empty if there are none). Anyone who can read the project may ask."""
    with conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id)
        require(conn, principal_id, draft["tenant_id"], READ, project_id=draft["project_id"], via_mcp=via_mcp)
        return _problems(cur, draft)


@dataclass(frozen=True)
class ScopeDraft:
    """A scope change set as a person reviews it: what it changes, and every problem it has now."""

    change_set_id: int
    project_id: int
    title: str
    status: str  # draft, applied or rejected
    source: str
    base_project_version: int
    records: list[dict]
    created_by_display_name: str
    created_time: datetime
    problems: list[Problem]


def read_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    """A scope change set with its records and its problems, for review. Anyone who can read the project may ask."""
    with conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id)
        require(conn, principal_id, draft["tenant_id"], READ, project_id=draft["project_id"], via_mcp=via_mcp)
        cur.execute(
            """SELECT cs.project_change_set_title AS title, cs.created_time, p.principal_display_name
                 FROM application.project_change_set AS cs
                 JOIN security.principal AS p ON p.principal_id = cs.created_by_principal_id
                WHERE cs.project_change_set_id = %s""",
            (change_set_id,),
        )
        extra = cur.fetchone()
        return ScopeDraft(
            change_set_id=change_set_id,
            project_id=draft["project_id"],
            title=extra["title"],
            status=draft["status"],
            source=draft["source"],
            base_project_version=draft["base_project_version"],
            records=draft["records"],
            created_by_display_name=extra["principal_display_name"],
            created_time=extra["created_time"],
            problems=_problems(cur, draft),
        )


def apply_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    """Apply a scope draft: save all of it, or nothing. Returns the problems that stopped it; empty means applied.

    Needs CHANGE on the project's tenant, the tenant lock (ACCESS-003) and the project not locked (CHANGE-SET-004).
    The project and change set rows stay locked until the end, so two Applies at the same moment cannot both pass the
    version check (CHANGE-SET-002). The same checks as `check_scope_draft` run inside, on the rows as they are now.
    Each record updates the project's scope row for its table, or adds one. Nothing is ever deleted, and a record
    that switches off a table with no scope row does nothing. Then the change set is marked applied with who and
    when (CHANGE-SET-008), and the project version goes up by one.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id)
    require(conn, principal_id, draft["tenant_id"], CHANGE, project_id=draft["project_id"], via_mcp=via_mcp)

    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id, for_update=True)
        problems = _problems(cur, draft)
        if problems:
            return problems
        for record in draft["records"]:
            table = _find_table(cur, record)
            if _scope_row(cur, draft["project_id"], table["object_id"]) is not None:
                cur.execute(
                    """UPDATE project.project_input_scope
                          SET is_active = %s, is_locked = %s,
                              updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                        WHERE project_id = %s AND object_id = %s""",
                    (record["is_active"], record["is_locked"], draft["project_id"], table["object_id"]),
                )
            elif record["is_active"]:
                cur.execute(
                    """INSERT INTO project.project_input_scope (project_id, object_id, is_active, is_locked)
                       VALUES (%s, %s, TRUE, %s)""",
                    (draft["project_id"], table["object_id"], record["is_locked"]),
                )
        cur.execute(
            """UPDATE application.project_change_set
                  SET project_change_set_status = 'applied', decided_by_principal_id = %s,
                      decided_time = CURRENT_TIMESTAMP, updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                WHERE project_change_set_id = %s""",
            (principal_id, change_set_id),
        )
        cur.execute(
            """UPDATE project.project
                  SET project_version = project_version + 1, updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                WHERE project_id = %s""",
            (draft["project_id"],),
        )
    return []


def reject_scope_draft(conn, principal_id, change_set_id, via_mcp=False):
    """Reject a scope draft: mark it rejected with who and when. Nothing in the project changes, not even its version.

    Needs the same as Apply: CHANGE on the project's tenant, the tenant lock (ACCESS-003) and the project not locked
    (CHANGE-SET-004). Only a draft, or a change set still receiving, can be rejected (CHANGE-SET-001). Returns the problems that stopped it, like Apply;
    empty means rejected. A draft built on an older project version can still be rejected; that is how it is cleared.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id)
    require(conn, principal_id, draft["tenant_id"], CHANGE, project_id=draft["project_id"], via_mcp=via_mcp)

    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        draft = _load_draft(cur, change_set_id, for_update=True)
        problem = change_set_001(draft["status"], rejecting=True)
        if problem is not None:
            return [problem]
        cur.execute(
            """UPDATE application.project_change_set
                  SET project_change_set_status = 'rejected', decided_by_principal_id = %s,
                      decided_time = CURRENT_TIMESTAMP, updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                WHERE project_change_set_id = %s""",
            (principal_id, change_set_id),
        )
    return []


def _load_draft(cur, change_set_id, for_update=False):
    """The change set with its project's tenant and current version, or NotFound (ACCESS-001)."""
    cur.execute(
        f"""SELECT cs.project_id, cs.project_change_set_status AS status, cs.project_change_set_source AS source,
                   cs.base_project_version, cs.project_input_scope_document AS records,
                   p.tenant_id, p.project_version
              FROM application.project_change_set AS cs
              JOIN project.project AS p ON p.project_id = cs.project_id
             WHERE cs.project_change_set_id = %s
             {"FOR UPDATE OF p, cs" if for_update else ""}""",
        (change_set_id,),
    )
    draft = cur.fetchone()
    if draft is None:
        raise NotFound("ACCESS-001", "Change set not found.")
    return draft


def _problems(cur, draft):
    """Every problem in the draft, in order: the whole draft first, then each record."""
    problems = [
        change_set_001(draft["status"]),
        change_set_002(draft["base_project_version"], draft["project_version"]),
    ]
    for index, record in enumerate(draft["records"]):
        table = _find_table(cur, record)
        if table is None:
            problems.append(change_set_003(record, index))
            continue
        row = _scope_row(cur, draft["project_id"], table["object_id"])
        problems.append(change_set_005(draft["source"], row, record, table, index))
        if record["is_active"]:  # SCOPE-001 and 002 are about tables in scope; switching one off is always fine
            problems.append(_scope_001(table, index))
            problems.append(_scope_002(table, draft["tenant_id"], index))
    return [problem for problem in problems if problem is not None]


# --- The checks, one per rule ---------------------------------------------------------------------------------------


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


def change_set_003(record, index):
    """CHANGE-SET-003: a record that names a table which does not exist is a problem."""
    return Problem(
        "CHANGE-SET-003",
        f"No table {_name(record)} on connection {record['tenant_code']} / {record['system_code']} / "
        f"{record['connection_code']}.",
        index,
    )


def change_set_005(source, scope_row, record, table, index):
    """CHANGE-SET-005: a Run or a VS Code push cannot change a locked row. A hand edit in the web app can."""
    if source not in LOCK_RESPECTING_SOURCES or scope_row is None or not scope_row["is_locked"]:
        return None
    if all(scope_row[field] == record[field] for field in VALUE_FIELDS):
        return None  # the record leaves the locked row exactly as it is
    return Problem(
        "CHANGE-SET-005",
        f"{_name(table)} is locked in scope. Unlock it by hand in the web app first, or take this change out.",
        index,
    )


def _scope_001(table, index):
    if not scope_001(table["zone_code"]):
        message = f"{_name(table)} is in zone {table['zone_name']}; only Source and Bronze can be in scope."
        return Problem("SCOPE-001", message, index)
    return None


def _scope_002(table, project_tenant_id, index):
    if not scope_002(table["source_tenant_id"], table["source_tenant_visibility"], project_tenant_id):
        return Problem(
            "SCOPE-002",
            f"{_name(table)} belongs to {table['source_tenant_name']}, which is private to another tenant.",
            index,
        )
    return None


# --- Helpers ---------------------------------------------------------------------------------------------------------


def _project(conn, project_id):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id, project_version FROM project.project WHERE project_id = %s", (project_id,))
        project = cur.fetchone()
    if project is None:
        raise NotFound("ACCESS-001", "Project not found.")
    return project


def _well_formed(records):
    """The records, checked for shape: a non-empty list, each with exactly the seven fields, no table twice."""
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    seen = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != set(RECORD_FIELDS):
            raise ValueError(f"record {index} must have exactly these fields: {', '.join(RECORD_FIELDS)}")
        for field in KEY_FIELDS:
            if not isinstance(record[field], str) or not record[field].strip():
                raise ValueError(f"record {index}: {field} must be a non-empty text")
        for field in VALUE_FIELDS:
            if not isinstance(record[field], bool):
                raise ValueError(f"record {index}: {field} must be true or false")
        key = tuple(record[field].strip().lower() for field in KEY_FIELDS)
        if key in seen:
            raise ValueError(f"record {index}: {_name(record)} is in the draft twice")
        seen.add(key)
    return records


def _find_table(cur, record):
    """The table a record names, or None. Names compare like the ux_ indexes: case and outer spaces are ignored."""
    cur.execute(
        """SELECT o.object_id, o.object_schema, o.object_name, lower(btrim(z.zone_code)) AS zone_code, z.zone_name,
                  st.tenant_id AS source_tenant_id, st.tenant_name AS source_tenant_name,
                  st.tenant_visibility AS source_tenant_visibility
             FROM core.object AS o
             JOIN core.connection AS c ON c.connection_id = o.connection_id
             JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id
             JOIN core.system AS s ON s.system_id = c.system_id
             JOIN core.tenant AS st ON st.tenant_id = o.source_tenant_id
             JOIN reference.zone AS z ON z.zone_id = o.zone_id
            WHERE lower(btrim(ct.tenant_code)) = lower(btrim(%(tenant_code)s))
              AND lower(btrim(s.system_code)) = lower(btrim(%(system_code)s))
              AND lower(btrim(c.connection_code)) = lower(btrim(%(connection_code)s))
              AND lower(btrim(o.object_schema)) = lower(btrim(%(object_schema)s))
              AND lower(btrim(o.object_name)) = lower(btrim(%(object_name)s))""",
        record,
    )
    return cur.fetchone()


def _scope_row(cur, project_id, object_id):
    cur.execute(
        "SELECT is_active, is_locked FROM project.project_input_scope WHERE project_id = %s AND object_id = %s",
        (project_id, object_id),
    )
    return cur.fetchone()


def _name(table):
    return f"{table['object_schema']}.{table['object_name']}"
