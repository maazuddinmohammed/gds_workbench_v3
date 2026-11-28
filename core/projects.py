"""Reading projects: a tenant's projects, one project in detail, and a project's current scope (step 4a2).

Nothing here changes the database. Changing the scope goes through a draft (core/change_sets.py).
"""

from dataclasses import dataclass

from psycopg.rows import dict_row

from core.access import READ, require
from core.catalog import ZONE_ORDER
from core.problems import NotFound


@dataclass(frozen=True)
class Project:
    project_id: int
    project_name: str
    project_description: str | None
    project_version: int
    is_locked: bool  # project lock: the whole project is read-only (CHANGE-SET-004)


@dataclass(frozen=True)
class ScopeTable:
    """One table in a project's scope, named by its row key, the same way a scope draft record names it."""

    tenant_code: str  # the tenant of the connection the table sits on
    system_code: str
    connection_code: str
    object_schema: str
    object_name: str
    zone_code: str
    source_tenant_code: str  # whose table it is
    is_active: bool  # false: taken out of scope (the row is switched off, never deleted, SCOPE-004)
    is_locked: bool  # a person has locked this row against AI and VS Code changes (CHANGE-SET-005)
    table_is_active: bool  # false if the table, or its connection, is switched off in the catalog


def list_projects(conn, principal_id, tenant_id, via_mcp=False):
    """The tenant's active projects, by name. Anyone who can read the tenant may ask (ACCESS-001)."""
    require(conn, principal_id, tenant_id, READ, via_mcp=via_mcp)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT project_id, project_name, project_description, project_version, is_locked
                 FROM project.project
                WHERE tenant_id = %s AND is_active
                ORDER BY lower(project_name), project_id""",
            (tenant_id,),
        )
        return [Project(**row) for row in cur.fetchall()]


def find_project(conn, principal_id, tenant_id, project_name, via_mcp=False):
    """The id of the tenant's active project with this name (any case), or "not found" (ACCESS-001)."""
    require(conn, principal_id, tenant_id, READ, via_mcp=via_mcp)
    row = conn.execute(
        """SELECT project_id FROM project.project
            WHERE tenant_id = %s AND lower(btrim(project_name)) = lower(btrim(%s)) AND is_active""",
        (tenant_id, project_name or ""),
    ).fetchone()
    if row is None:
        raise NotFound("ACCESS-001", "Project not found.")
    return row[0]


# The parts of a project whose active rows get_project_detail counts, each with the SQL that counts them.
ROW_COUNTS = {
    "project_input_scope": "SELECT count(*) FROM project.project_input_scope WHERE project_id = %(p)s AND is_active",
    "object_enrichment": "SELECT count(*) FROM workflow.object_enrichment WHERE project_id = %(p)s AND is_active",
    "analysis_result": "SELECT count(*) FROM workflow.analysis_result WHERE project_id = %(p)s AND is_active",
    "subject_area": "SELECT count(*) FROM workflow.subject_area WHERE project_id = %(p)s AND is_active",
    "operational_entity": "SELECT count(*) FROM workflow.operational_entity WHERE project_id = %(p)s AND is_active",
    "dimensional_entity": "SELECT count(*) FROM workflow.dimensional_entity WHERE project_id = %(p)s AND is_active",
    "operational_object_mapping": """SELECT count(*) FROM workflow.operational_object_mapping AS m
        JOIN workflow.operational_entity AS e USING (operational_entity_id)
        WHERE e.project_id = %(p)s AND m.is_active""",
    "dimensional_object_mapping": """SELECT count(*) FROM workflow.dimensional_object_mapping AS m
        JOIN workflow.dimensional_entity AS e USING (dimensional_entity_id)
        WHERE e.project_id = %(p)s AND m.is_active""",
}


def get_project_detail(conn, principal_id, project_id, via_mcp=False):
    """One project: its version, whether it is locked, its settings and how many active rows each part has.

    Left out: the default AI settings, which only Runs in the web app use (design/operations/shared.md).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.tenant_id, t.tenant_code, p.project_name, p.project_description, p.project_version, p.is_locked
                 FROM project.project AS p JOIN core.tenant AS t USING (tenant_id)
                WHERE p.project_id = %s AND p.is_active""",
            (project_id,),
        )
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        require(conn, principal_id, project.pop("tenant_id"), READ, project_id=project_id, via_mcp=via_mcp)
        cur.execute(
            """SELECT operational_schemas, dimensional_schemas, operational_entity_scd_type, dimensional_entity_scd_type,
                      operational_naming_instructions, dimensional_naming_instructions, operational_audit_columns,
                      dimensional_audit_columns, is_sample_storage_allowed, sample_size, subject_area_target_column_count
                 FROM project.project_config WHERE project_id = %s""",
            (project_id,),
        )
        project["project_config"] = cur.fetchone()
        project["row_counts"] = {
            part: conn.execute(sql, {"p": project_id}).fetchone()[0] for part, sql in ROW_COUNTS.items()
        }
    return project


def current_scope(conn, principal_id, project_id, include_switched_off=False, via_mcp=False):
    """The tables in the project's scope, in the table list's order (zone, schema, name).

    Anyone who can read the project may ask. Rows taken out of scope show only when `include_switched_off` is true.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM project.project WHERE project_id = %s AND is_active", (project_id,))
        project = cur.fetchone()
        if project is None:
            raise NotFound("ACCESS-001", "Project not found.")
        require(conn, principal_id, project["tenant_id"], READ, project_id=project_id, via_mcp=via_mcp)
        cur.execute(
            """SELECT ct.tenant_code, sy.system_code, c.connection_code, o.object_schema, o.object_name,
                      lower(btrim(z.zone_code)) AS zone_code, st.tenant_code AS source_tenant_code,
                      s.is_active, s.is_locked, o.is_active AND c.is_active AS table_is_active
                 FROM project.project_input_scope AS s
                 JOIN core.object AS o ON o.object_id = s.object_id
                 JOIN core.connection AS c ON c.connection_id = o.connection_id
                 JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id
                 JOIN core.system AS sy ON sy.system_id = c.system_id
                 JOIN core.tenant AS st ON st.tenant_id = o.source_tenant_id
                 JOIN reference.zone AS z ON z.zone_id = o.zone_id
                WHERE s.project_id = %(project_id)s AND (%(include_switched_off)s OR s.is_active)
                ORDER BY coalesce(array_position(%(zone_order)s::text[], lower(btrim(z.zone_code))::text), 99),
                         lower(o.object_schema), lower(o.object_name), o.object_id""",
            {"project_id": project_id, "include_switched_off": include_switched_off, "zone_order": list(ZONE_ORDER)},
        )
        return [ScopeTable(**row) for row in cur.fetchall()]
