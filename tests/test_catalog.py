"""Tests for core/catalog.py: which tables a person sees from a tenant (step 3c, SCOPE-001, SCOPE-002).

The catalog follows the example agreed with Maaz: ERP owns a Source table on its own connection, and its Bronze,
Silver and Gold tables sit on the GDS US connection of the data lake tenant GDS, still owned by ERP. Shared is a
global tenant with one Bronze table; Fabrikam is another private tenant. The catalog is the `cat` fixture and the
people the `demo` fixture, both in conftest.py; Eve is a member of ERP only, Gus of GDS only.
"""

import pytest

from core.catalog import list_tables, scope_001, scope_002
from core.problems import NotFound, Refused


def ids(page):
    return [t.object_id for t in page.tables]


def by_id(page):
    return {t.object_id: t for t in page.tables}


def test_member_sees_their_tenants_tables_in_every_zone_including_those_in_the_lake(cat):
    page = list_tables(cat.conn, cat.eve, cat.erp)
    assert ids(page) == [cat.erp_source, cat.erp_bronze, cat.shared_bronze, cat.erp_silver, cat.erp_gold]
    assert by_id(page)[cat.erp_bronze].source_tenant_code == "ERP"
    assert by_id(page)[cat.erp_bronze].connection_code == "gds_us"


def test_member_of_the_lake_tenant_does_not_see_other_tenants_tables(cat):
    page = list_tables(cat.conn, cat.gus, cat.gds)
    assert ids(page) == [cat.shared_bronze]  # GDS owns no tables; only the global one shows


def test_global_tables_are_listed_and_marked(cat):
    page = by_id(list_tables(cat.conn, cat.eve, cat.erp))
    assert page[cat.shared_bronze].is_global is True
    assert page[cat.shared_bronze].source_tenant_name == "Shared"
    assert page[cat.erp_bronze].is_global is False


def test_another_private_tenants_tables_never_appear(cat):
    for who, tenant in [(cat.eve, cat.erp), (cat.gus, cat.gds), (cat.demo.sam, cat.erp)]:
        page = list_tables(cat.conn, who, tenant, include_switched_off=True)
        assert cat.fabrikam_bronze not in ids(page)


def test_an_inactive_global_tenants_tables_do_not_appear(cat):
    cat.conn.execute("UPDATE core.tenant SET is_active = FALSE WHERE tenant_id = %s", (cat.demo.shared,))
    assert cat.shared_bronze not in ids(list_tables(cat.conn, cat.eve, cat.erp))


def test_zone_filter(cat):
    page = list_tables(cat.conn, cat.eve, cat.erp, zones=["Bronze", "gold"])
    assert ids(page) == [cat.erp_bronze, cat.shared_bronze, cat.erp_gold]


def test_unknown_zone_is_refused(cat):
    with pytest.raises(ValueError, match="platinum"):
        list_tables(cat.conn, cat.eve, cat.erp, zones=["platinum"])


def test_can_scope_follows_scope_001_and_002(cat):
    page = by_id(list_tables(cat.conn, cat.eve, cat.erp))
    assert {object_id: t.can_scope for object_id, t in page.items()} == {
        cat.erp_source: True,
        cat.erp_bronze: True,
        cat.shared_bronze: True,  # a global tenant's Bronze table (SCOPE-002)
        cat.erp_silver: False,  # SCOPE-001
        cat.erp_gold: False,
    }


def test_scope_only_filter(cat):
    page = list_tables(cat.conn, cat.eve, cat.erp, scope_only=True)
    assert ids(page) == [cat.erp_source, cat.erp_bronze, cat.shared_bronze]
    assert page.total == 3


def test_switched_off_table_is_hidden_unless_asked_for(cat):
    old = cat.table(cat.gds_us, cat.erp, "bronze", "bronze_erp", "old_orders", active=False)
    assert old not in ids(list_tables(cat.conn, cat.eve, cat.erp))
    page = by_id(list_tables(cat.conn, cat.eve, cat.erp, include_switched_off=True))
    assert page[old].is_active is False
    assert page[cat.erp_bronze].is_active is True


def test_table_on_a_switched_off_connection_is_hidden_unless_asked_for(cat):
    cat.conn.execute("UPDATE core.connection SET is_active = FALSE WHERE connection_id = %s", (cat.erp_db,))
    assert cat.erp_source not in ids(list_tables(cat.conn, cat.eve, cat.erp))
    page = by_id(list_tables(cat.conn, cat.eve, cat.erp, include_switched_off=True))
    assert page[cat.erp_source].is_active is False


def test_paging_50_at_a_time_in_a_stable_order(cat):
    for n in range(115):  # with ERP's 4 and Shared's 1, 120 tables in all
        cat.table(cat.erp_db, cat.erp, "source", "sap", f"T{n:03d}")
    pages = [list_tables(cat.conn, cat.eve, cat.erp, page=n) for n in (1, 2, 3, 4)]
    assert [len(p.tables) for p in pages] == [50, 50, 20, 0]
    assert {p.total for p in pages} == {120}
    listed = [t for p in pages for t in p.tables]
    assert len({t.object_id for t in listed}) == 120
    zones = ("source", "bronze", "silver", "gold")
    order = [(zones.index(t.zone_code), t.object_schema.lower(), t.object_name.lower()) for t in listed]
    assert order == sorted(order)
    assert ids(list_tables(cat.conn, cat.eve, cat.erp, page=2)) == ids(pages[1])


@pytest.mark.parametrize("page", [0, -1, 1.5, True])
def test_bad_page_is_refused(cat, page):
    with pytest.raises(ValueError):
        list_tables(cat.conn, cat.eve, cat.erp, page=page)


def test_outsider_gets_not_found(cat):
    with pytest.raises(NotFound) as info:
        list_tables(cat.conn, cat.gus, cat.erp)
    assert info.value.rule_id == "ACCESS-001"


def test_mcp_without_mcp_access_is_refused(cat):
    with pytest.raises(Refused) as info:
        list_tables(cat.conn, cat.eve, cat.erp, via_mcp=True)
    assert info.value.rule_id == "ACCESS-004"


# --- The two scope rules on their own, with the examples from docs/rules/scope.md ------------------------------------


@pytest.mark.parametrize(("zone", "allowed"), [("source", True), ("Bronze", True), ("silver", False), ("gold", False)])
def test_scope_001_only_source_and_bronze(zone, allowed):
    assert scope_001(zone) is allowed


def test_scope_002_own_tenant_or_global_only():
    contoso, shared, fabrikam = 1, 2, 3
    assert scope_002(contoso, "private", project_tenant_id=contoso) is True  # Retail scopes a Contoso table
    assert scope_002(shared, "global", project_tenant_id=contoso) is True  # or a table of the global tenant Shared
    assert scope_002(fabrikam, "private", project_tenant_id=contoso) is False  # never another private tenant's
