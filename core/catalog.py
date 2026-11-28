"""Reading the catalog: the tables a person can see from a tenant (step 3c).

A table belongs to its source tenant (`core.object.source_tenant_id`), whose data it is. Which connection it sits on
does not decide who sees it: a Bronze copy of ERP's table sits on the data lake connection but is listed under ERP,
and being a member of the data lake tenant does not show you everyone's Bronze tables (docs/rules/catalog.md).

From a tenant you see its own tables and the tables of every active global tenant, because those are the tables
its projects may scope (SCOPE-002). The list comes 50 tables at a time, in a fixed order (zone, schema, name), with
the total, so the web app and MCP can page through a few hundred tables. Paging is done in SQL (LIMIT and OFFSET),
so only one page of rows is read. Nothing here changes the database.
"""

from dataclasses import dataclass

from psycopg.rows import dict_row

from core.access import READ, require

PAGE_SIZE = 50
ZONE_ORDER = ("source", "bronze", "silver", "gold")  # the order zones are listed in; any other zone comes last
SCOPE_ZONES = ("source", "bronze")  # SCOPE-001


@dataclass(frozen=True)
class CatalogTable:
    """One table of the catalog, as shown in the table list."""

    object_id: int
    object_schema: str
    object_name: str
    zone_code: str
    object_type_code: str
    source_tenant_code: str
    source_tenant_name: str
    is_global: bool  # the table belongs to a global tenant, not to the tenant you asked about
    connection_tenant_code: str  # the tenant of the connection the table sits on; first field of its row key
    connection_code: str  # where the table sits
    system_code: str
    is_active: bool  # false if the table or its connection is switched off
    can_scope: bool  # SCOPE-001 and SCOPE-002: this tenant's projects may put it in scope


@dataclass(frozen=True)
class TablePage:
    """One page of the table list, and how many tables match in all."""

    tables: list[CatalogTable]
    page: int
    total: int
    page_size: int = PAGE_SIZE


def is_scope_zone(zone_code):
    """Only Source and Bronze tables can be in scope (SCOPE-001, checked in core/rules.py)."""
    return zone_code.strip().lower() in SCOPE_ZONES


def is_scope_tenant(source_tenant_id, source_tenant_visibility, project_tenant_id):
    """A scope table belongs to the project's tenant or to a global tenant (SCOPE-002, checked in core/rules.py)."""
    return source_tenant_id == project_tenant_id or source_tenant_visibility == "global"


def list_tables(
    conn, principal_id, tenant_id, zones=None, scope_only=False, include_switched_off=False, page=1, via_mcp=False
):
    """The tables of `tenant_id` and of every active global tenant, one page of 50 at a time.

    Anyone who can read the tenant may ask (ACCESS-001). Filters:
    - `zones`: a list of zone codes, for example ["source", "bronze"]; None for all zones;
    - `scope_only`: only the tables this tenant's projects may put in scope;
    - `include_switched_off`: also the tables that are switched off, or whose connection is.
    `page` starts at 1. A page past the end is empty.
    """
    require(conn, principal_id, tenant_id, READ, via_mcp=via_mcp)
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError(f"page must be a whole number from 1, not {page!r}")

    with conn.cursor(row_factory=dict_row) as cur:
        params = {
            "tenant_id": tenant_id,
            "zones": None if zones is None else _known_zones(cur, zones),
            "include_switched_off": include_switched_off,
            # Every table listed here is the tenant's own or a global tenant's, so SCOPE-002 always holds and
            # scope-only is just the SCOPE-001 zone check. If SCOPE-002 changes, change this filter with it.
            "scope_zones": list(SCOPE_ZONES) if scope_only else None,
            "zone_order": list(ZONE_ORDER),
            "limit": PAGE_SIZE,
            "offset": (page - 1) * PAGE_SIZE,
        }
        matching = """
                 FROM core.object AS o
                 JOIN core.tenant AS st ON st.tenant_id = o.source_tenant_id
                 JOIN reference.zone AS z ON z.zone_id = o.zone_id
                 JOIN reference.object_type AS ot ON ot.object_type_id = o.object_type_id
                 JOIN core.connection AS c ON c.connection_id = o.connection_id
                 JOIN core.tenant AS ct ON ct.tenant_id = c.tenant_id
                 JOIN core.system AS s ON s.system_id = c.system_id
                WHERE (st.tenant_id = %(tenant_id)s OR (st.tenant_visibility = 'global' AND st.is_active))
                  AND (%(zones)s::text[] IS NULL OR lower(btrim(z.zone_code)) = ANY(%(zones)s::text[]))
                  AND (%(scope_zones)s::text[] IS NULL OR lower(btrim(z.zone_code)) = ANY(%(scope_zones)s::text[]))
                  AND (%(include_switched_off)s OR (o.is_active AND c.is_active))"""

        cur.execute("SELECT count(*) AS total" + matching, params)
        total = cur.fetchone()["total"]
        cur.execute(
            """SELECT o.object_id, o.object_schema, o.object_name, lower(btrim(z.zone_code)) AS zone_code,
                      ot.object_type_code, st.tenant_id AS source_tenant_id, st.tenant_code AS source_tenant_code,
                      st.tenant_name AS source_tenant_name, st.tenant_visibility AS source_tenant_visibility,
                      ct.tenant_code AS connection_tenant_code, c.connection_code, s.system_code,
                      o.is_active AND c.is_active AS is_active"""
            + matching
            + """
                ORDER BY coalesce(array_position(%(zone_order)s::text[], lower(btrim(z.zone_code))::text), 99),
                         lower(o.object_schema), lower(o.object_name), o.object_id
                LIMIT %(limit)s OFFSET %(offset)s""",
            params,
        )
        rows = cur.fetchall()

    return TablePage(tables=[_to_table(row, tenant_id) for row in rows], page=page, total=total)


def _to_table(row, tenant_id):
    return CatalogTable(
        object_id=row["object_id"],
        object_schema=row["object_schema"],
        object_name=row["object_name"],
        zone_code=row["zone_code"],
        object_type_code=row["object_type_code"],
        source_tenant_code=row["source_tenant_code"],
        source_tenant_name=row["source_tenant_name"],
        is_global=row["source_tenant_id"] != tenant_id,
        connection_tenant_code=row["connection_tenant_code"],
        connection_code=row["connection_code"],
        system_code=row["system_code"],
        is_active=row["is_active"],
        can_scope=is_scope_zone(row["zone_code"])
        and is_scope_tenant(row["source_tenant_id"], row["source_tenant_visibility"], tenant_id),
    )


def _known_zones(cur, zones):
    """The zone codes in lower case, or ValueError naming the zones there are."""
    cur.execute("SELECT lower(zone_code) AS code FROM reference.zone WHERE is_active ORDER BY zone_id")
    known = [row["code"] for row in cur.fetchall()]
    codes = [str(zone).strip().lower() for zone in zones]
    unknown = [zone for zone, code in zip(zones, codes) if code not in known]
    if unknown:
        raise ValueError(f"unknown zone {unknown}; zones are {', '.join(known)}")
    return codes
