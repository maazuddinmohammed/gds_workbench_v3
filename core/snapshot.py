"""Snapshots and pushes: the project files the Bridge moves between VS Code and the server
(design/operations/change-sets.md, design/vscode/bridge.md). Step 4c builds the scope part first.

A snapshot is a zip: `gds.json` (the kind, tenant, project, version and snapshot id, sent back with a push),
`README.md` (the rules and the shape of each file, for the AI) and one `.jsonl` file per part, one record per line,
switched-off rows included. So far that is `scope.jsonl`. A push sends a zip of the same shape back; loading it
replaces the change set's records with every line it holds. A missing line, field or file changes nothing, and a
push never deletes: `"is_active": false` switches a row off.
"""

import io
import json
import zipfile
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from core import change_sets
from core.access import CHANGE, READ, require
from core.parts import PARTS
from core.problems import NotFound, Refused

FILES = {"scope.jsonl": "project_input_scope"}  # file -> part; more parts come file by file

README = """# {project_name} ({tenant_code}), version {project_version}

Files you edit, one database row per line (JSON). Each line names its row by names and codes, never by ids:
{files}

- To add a row, add a line. To change one, edit its values. To switch one off, set "is_active": false; to bring it
  back, set it to true. Nothing is ever deleted, and a line you leave out changes nothing.
- Push the folder back: the server loads every line into one change set and checks it. Each problem names its rule,
  file and line. A person applies the change set after reviewing it.
- gds.json says which project version these files were taken from. A push built on an older version is refused:
  pull again and redo the changes on top.
"""


def create(conn, principal_id, project_id, via_mcp=False):
    """The project's snapshot: (snapshot id, project version, zip bytes). Anyone who can read the project may."""
    project = _project(conn, project_id)
    require(conn, principal_id, project["tenant_id"], READ, project_id=project_id, via_mcp=via_mcp)
    snapshot_id = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    meta = {"kind": "project", "tenant_code": project["tenant_code"], "project_name": project["project_name"],
            "project_version": project["project_version"], "snapshot_id": snapshot_id}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("gds.json", json.dumps(meta, indent=1))
        files = "\n".join(f"- `{name}`: {', '.join(PARTS[part].fields)}" for name, part in FILES.items())
        z.writestr("README.md", README.format(files=files, **meta))
        for name, part in FILES.items():
            records = change_sets.read_records(conn, principal_id, project_id, part, via_mcp=via_mcp)
            z.writestr(name, "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records))
    return snapshot_id, project["project_version"], buffer.getvalue()


def start(conn, principal_id, project_id, title, via_mcp=False):
    """Open an empty change set for a push (status receiving) on the project's version; returns its id."""
    project = _project(conn, project_id)
    require(conn, principal_id, project["tenant_id"], CHANGE, project_id=project_id, via_mcp=via_mcp)
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        raise ValueError("a change set needs a title")
    with conn.transaction():
        return conn.execute(
            """INSERT INTO application.project_change_set
                   (project_id, project_change_set_status, project_change_set_title, project_change_set_source,
                    base_project_version, created_by_principal_id)
               VALUES (%s, 'receiving', %s, 'vscode_push', %s, %s) RETURNING project_change_set_id""",
            (project_id, title, project["project_version"], principal_id),
        ).fetchone()[0]


def next_upload(conn, principal_id, change_set_id, via_mcp=False):
    """The next upload number of a change set that can still take one (receiving or draft)."""
    row = _change_set(conn, change_set_id)
    require(conn, principal_id, row["tenant_id"], CHANGE, project_id=row["project_id"], via_mcp=via_mcp)
    if row["status"] not in ("receiving", "draft"):
        raise Refused("CHANGE-SET-001", f"This change set is {row['status']}, so it takes no upload.")
    return (row["upload_number"] or 0) + 1


def load(conn, principal_id, change_set_id, upload_number, zip_bytes, via_mcp=False):
    """Load an upload into the change set, all or nothing: every line becomes a record, replacing what it held.
    Refused (CHANGE-SET-002) when the files were taken from an older project version. A file that cannot be read
    stops the load, and the error names the file and line."""
    row = _change_set(conn, change_set_id)
    require(conn, principal_id, row["tenant_id"], CHANGE, project_id=row["project_id"], via_mcp=via_mcp)
    if row["status"] not in ("receiving", "draft"):
        raise Refused("CHANGE-SET-001", f"This change set is {row['status']}, so it takes no upload.")
    documents = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        meta = json.loads(z.read("gds.json"))
        if meta.get("project_version") != row["project_version"]:
            raise Refused("CHANGE-SET-002", f"These files were taken at version {meta.get('project_version')}, but the "
                                            f"project is now at {row['project_version']}. Pull again and redo the "
                                            "changes on top.")
        for name, part in FILES.items():
            if name not in z.namelist():
                continue
            for line_number, line in enumerate(z.read(name).decode("utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError as error:
                    raise ValueError(f"{name} line {line_number} is not JSON: {error}") from None
                if not isinstance(record, dict):
                    raise ValueError(f"{name} line {line_number} is not one record")
                documents.setdefault(part, []).append(record)
    if documents:
        change_sets.well_formed(documents)
    with conn.transaction():
        conn.execute(
            f"""UPDATE application.project_change_set
                   SET project_change_set_status = 'draft', upload_number = %s,
                       base_project_version = %s, {', '.join(f'{p}_document = %s' for p in PARTS)},
                       updated_time = CURRENT_TIMESTAMP, updated_by = CURRENT_USER
                 WHERE project_change_set_id = %s""",
            (upload_number, row["project_version"], *[Jsonb(documents.get(p, [])) for p in PARTS], change_set_id),
        )
    return change_sets.get_change_set(conn, principal_id, change_set_id, via_mcp=via_mcp)


def _project(conn, project_id):
    row = conn.execute(
        """SELECT p.tenant_id, t.tenant_code, p.project_name, p.project_version FROM project.project AS p
             JOIN core.tenant AS t USING (tenant_id) WHERE p.project_id = %s AND p.is_active""",
        (project_id,),
    ).fetchone()
    if row is None:
        raise NotFound("ACCESS-001", "Project not found.")
    return dict(zip(("tenant_id", "tenant_code", "project_name", "project_version"), row))


def _change_set(conn, change_set_id):
    row = conn.execute(
        """SELECT cs.project_id, p.tenant_id, cs.project_change_set_status, cs.upload_number, p.project_version
             FROM application.project_change_set AS cs JOIN project.project AS p USING (project_id)
            WHERE cs.project_change_set_id = %s""",
        (change_set_id,),
    ).fetchone()
    if row is None:
        raise NotFound("ACCESS-001", "Change set not found.")
    return dict(zip(("project_id", "tenant_id", "status", "upload_number", "project_version"), row))
