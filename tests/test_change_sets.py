"""Tests for core/change_sets.py, the change set engine, with scope records (steps 3d and 4c2): making, checking,
applying and rejecting a draft.

Project Orders belongs to ERP. Ben is a Developer in ERP. The catalog comes from the `cat` fixture in conftest.py:
ERP's Source table sap.VBAK on erp_db, ERP's Bronze, Silver and Gold on the data lake connection gds_us, Shared's
global Bronze table and Fabrikam's private Bronze table, also on gds_us.
"""

from types import SimpleNamespace

import pytest

from core.problems import NotFound, Refused
from core.change_sets import apply as apply_draft
from core.change_sets import get_change_set, list_changes, make_draft, read_records, reject as reject_draft, validate


def make_scope_draft(conn, principal_id, project_id, records, title):
    return make_draft(conn, principal_id, project_id, {"project_input_scope": records}, title)


@pytest.fixture
def p(cat):
    conn, demo = cat.conn, cat.demo
    conn.execute(
        """INSERT INTO security.tenant_principal_access (tenant_id, principal_id, tenant_role, granted_by_principal_id)
           VALUES (%s, %s, 'developer', %s)""",
        (cat.erp, demo.ben, demo.sam),
    )
    project = conn.execute(
        "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Orders') RETURNING project_id", (cat.erp,)
    ).fetchone()[0]
    demo.lock(cat.erp, demo.ben)
    return SimpleNamespace(cat=cat, conn=conn, demo=demo, project=project, ben=demo.ben)


def rec(schema, name, connection="gds_us", active=True, locked=False):
    tenant, system = {"gds_us": ("GDS", "GDS_US"), "erp_db": ("ERP", "ERP_DB")}[connection]
    return {
        "tenant_code": tenant,
        "system_code": system,
        "connection_code": connection,
        "object_schema": schema,
        "object_name": name,
        "is_active": active,
        "is_locked": locked,
    }


BRONZE = rec("bronze_erp", "orders")
SOURCE = rec("sap", "VBAK", connection="erp_db")
SILVER = rec("silver_erp", "order")
SHARED = rec("bronze_shared", "calendar")
FABRIKAM = rec("bronze_hr", "employees")


def draft(p, *records, title="Scope for Orders"):
    return make_scope_draft(p.conn, p.ben, p.project, list(records), title)


def check(p, change_set_id):
    return [(problem.rule_id, problem.record) for problem in validate(p.conn, p.ben, change_set_id)]


def refused(rule_id, call, kind=Refused):
    with pytest.raises(kind) as info:
        call()
    assert info.value.rule_id == rule_id


def scope_rows(p):
    sql = "SELECT count(*) FROM project.project_input_scope WHERE project_id = %s"
    return p.conn.execute(sql, (p.project,)).fetchone()[0]


# --- Making a draft --------------------------------------------------------------------------------------------------


def test_draft_is_saved_on_the_current_version_and_scope_does_not_change(p):
    p.conn.execute("UPDATE project.project SET project_version = 7 WHERE project_id = %s", (p.project,))
    change_set_id = draft(p, BRONZE, SOURCE)
    saved = p.conn.execute(
        """SELECT project_id, project_change_set_status, project_change_set_source, base_project_version,
                  project_input_scope_document, created_by_principal_id
             FROM application.project_change_set WHERE project_change_set_id = %s""",
        (change_set_id,),
    ).fetchone()
    assert saved == (p.project, "draft", "web_app_edit", 7, [BRONZE, SOURCE], p.ben)
    assert scope_rows(p) == 0


def test_viewer_cannot_make_a_draft(p):
    refused("ACCESS-002", lambda: make_scope_draft(p.conn, p.cat.eve, p.project, [BRONZE], "Scope"))


def test_without_the_tenant_lock_you_cannot_make_a_draft(p):
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    refused("ACCESS-003", lambda: draft(p, BRONZE))


def test_the_lock_on_the_data_lake_tenant_does_not_count(p):
    """Orders belongs to ERP, so only ERP's lock counts, even for a table that sits in the lake."""
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    p.demo.lock(p.cat.gds, p.ben)
    refused("ACCESS-003", lambda: draft(p, BRONZE))


def test_locked_project_cannot_get_a_draft(p):
    p.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (p.project,))
    refused("CHANGE-SET-004", lambda: draft(p, BRONZE))


def test_unknown_project_is_not_found(p):
    refused("ACCESS-001", lambda: make_scope_draft(p.conn, p.ben, -1, [BRONZE], "Scope"), kind=NotFound)


def test_outsider_gets_not_found(p):
    refused("ACCESS-001", lambda: make_scope_draft(p.conn, p.cat.gus, p.project, [BRONZE], "Scope"), kind=NotFound)


@pytest.mark.parametrize(
    "records",
    [
        [],
        "not a list",
        [{k: v for k, v in BRONZE.items() if k != "object_name"}],  # a key field missing
        [BRONZE | {"object_id": 5}],  # a database id is not allowed
        [BRONZE | {"object_name": "  "}],
    ],
)
def test_malformed_records_are_refused_and_nothing_is_saved(p, records):
    with pytest.raises(ValueError):
        make_scope_draft(p.conn, p.ben, p.project, records, "Scope")
    assert p.conn.execute("SELECT count(*) FROM application.project_change_set").fetchone()[0] == 0


def test_a_draft_needs_a_title(p):
    with pytest.raises(ValueError):
        draft(p, BRONZE, title="  ")


# --- Checking a draft ------------------------------------------------------------------------------------------------


def test_a_good_draft_has_no_problems(p):
    """ERP's Source and Bronze tables, and Shared's global table, may all be in scope (SCOPE-001 and 002 pass)."""
    assert check(p, draft(p, SOURCE, BRONZE, SHARED)) == []


def test_names_are_matched_ignoring_case_and_outer_spaces(p):
    shouty = {k: (f" {v.upper()} " if isinstance(v, str) else v) for k, v in BRONZE.items()}
    assert check(p, draft(p, shouty)) == []


def test_change_set_001_only_a_draft(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute(
        """UPDATE application.project_change_set SET project_change_set_status = 'rejected',
                  decided_by_principal_id = %s, decided_time = CURRENT_TIMESTAMP
            WHERE project_change_set_id = %s""",
        (p.ben, change_set_id),
    )
    assert check(p, change_set_id) == [("CHANGE-SET-001", None)]


def test_change_set_002_project_moved_on(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("UPDATE project.project SET project_version = 2 WHERE project_id = %s", (p.project,))
    assert check(p, change_set_id) == [("CHANGE-SET-002", None)]


def test_change_set_003_table_that_does_not_exist(p):
    assert check(p, draft(p, BRONZE, rec("bronze_erp", "nope"))) == [("CHANGE-SET-003", 1)]


def test_change_set_003_same_name_on_another_connection_is_not_found(p):
    """bronze_erp.orders exists on gds_us, not on erp_db."""
    assert check(p, draft(p, rec("bronze_erp", "orders", connection="erp_db"))) == [("CHANGE-SET-003", 0)]


def test_scope_001_silver_table_refused(p):
    problems = validate(p.conn, p.ben, draft(p, SILVER))
    assert [(x.rule_id, x.record) for x in problems] == [("SCOPE-001", 0)]
    assert str(problems[0]) == "SCOPE-001: silver_erp.order is in zone Silver; only Source and Bronze can be in scope."


def test_scope_002_another_private_tenants_table_refused(p):
    assert check(p, draft(p, FABRIKAM)) == [("SCOPE-002", 0)]


def test_switching_a_table_off_is_never_a_scope_problem(p):
    assert check(p, draft(p, SILVER | {"is_active": False}, FABRIKAM | {"is_active": False})) == []


def test_every_problem_is_reported_at_once(p):
    change_set_id = draft(p, SILVER, FABRIKAM, BRONZE, rec("x", "y"))
    p.conn.execute("UPDATE project.project SET project_version = 2 WHERE project_id = %s", (p.project,))
    assert check(p, change_set_id) == [
        ("CHANGE-SET-002", None),
        ("CHANGE-SET-003", 3),
        ("SCOPE-001", 0),
        ("SCOPE-002", 1),
    ]


def test_change_set_013_the_same_table_twice(p):
    assert check(p, draft(p, BRONZE, BRONZE | {"object_name": " ORDERS ", "is_active": False})) == [
        ("CHANGE-SET-013", 1)]


def test_scope_005_two_tables_with_the_same_schema_and_name(p):
    twin = p.cat.table(p.cat.erp_db, p.cat.erp, "bronze", "bronze_erp", "orders")  # same name, another connection
    assert twin
    assert check(p, draft(p, BRONZE, rec("bronze_erp", "orders", connection="erp_db"))) == [("SCOPE-005", 1)]


def test_a_record_may_leave_a_field_out_to_keep_the_saved_value(p):
    add_row(p, p.cat.erp_bronze, locked=True)
    assert apply(p, draft(p, {k: v for k, v in BRONZE.items() if k != "is_locked"} | {"is_active": False})) == []
    assert scope(p) == {p.cat.erp_bronze: (False, True)}


@pytest.fixture
def locked_bronze(p):
    p.conn.execute(
        "INSERT INTO project.project_input_scope (project_id, object_id, is_locked) VALUES (%s, %s, TRUE)",
        (p.project, p.cat.erp_bronze),
    )


@pytest.mark.parametrize("source", ["vscode_push", "ai_run"])
def test_change_set_005_push_or_run_cannot_change_a_locked_row(p, locked_bronze, source):
    change_set_id = draft(p, BRONZE | {"is_active": False, "is_locked": True})
    p.conn.execute(
        "UPDATE application.project_change_set SET project_change_set_source = %s WHERE project_change_set_id = %s",
        (source, change_set_id),
    )
    assert check(p, change_set_id) == [("CHANGE-SET-005", 0)]


def test_change_set_005_push_that_leaves_a_locked_row_as_it_is_is_fine(p, locked_bronze):
    change_set_id = draft(p, BRONZE | {"is_locked": True})
    p.conn.execute(
        "UPDATE application.project_change_set SET project_change_set_source = 'vscode_push' "
        "WHERE project_change_set_id = %s",
        (change_set_id,),
    )
    assert check(p, change_set_id) == []


def test_change_set_005_hand_edit_may_unlock_a_locked_row(p, locked_bronze):
    assert check(p, draft(p, BRONZE | {"is_locked": False})) == []


def test_anyone_who_reads_the_project_may_check_but_outsiders_get_not_found(p):
    change_set_id = draft(p, BRONZE)
    assert validate(p.conn, p.cat.eve, change_set_id) == []  # Eve is a Viewer in ERP
    refused("ACCESS-001", lambda: validate(p.conn, p.cat.gus, change_set_id), kind=NotFound)
    refused("ACCESS-001", lambda: validate(p.conn, p.ben, -1), kind=NotFound)


# --- Applying a draft (3d2) ------------------------------------------------------------------------------------------


def scope(p):
    """The project's scope rows as {object_id: (is_active, is_locked)}."""
    rows = p.conn.execute(
        "SELECT object_id, is_active, is_locked FROM project.project_input_scope WHERE project_id = %s", (p.project,)
    ).fetchall()
    return {object_id: (active, locked) for object_id, active, locked in rows}


def state(p, change_set_id):
    """Everything Apply may change: the scope rows, the project version and the change set's status and decider."""
    sql = "SELECT project_version FROM project.project WHERE project_id = %s"
    version = p.conn.execute(sql, (p.project,)).fetchone()
    decided = p.conn.execute(
        """SELECT project_change_set_status, decided_by_principal_id, decided_time IS NOT NULL
             FROM application.project_change_set WHERE project_change_set_id = %s""",
        (change_set_id,),
    ).fetchone()
    return scope(p), version[0], decided


def apply(p, change_set_id):
    return [(problem.rule_id, problem.record) for problem in apply_draft(p.conn, p.ben, change_set_id)]


def add_row(p, object_id, active=True, locked=False):
    p.conn.execute(
        "INSERT INTO project.project_input_scope (project_id, object_id, is_active, is_locked) VALUES (%s, %s, %s, %s)",
        (p.project, object_id, active, locked),
    )


def test_apply_saves_the_draft_moves_the_version_and_records_who(p):
    cat = p.cat
    add_row(p, cat.erp_source)  # in scope already
    add_row(p, cat.shared_bronze)  # in scope, not in the draft
    change_set_id = draft(p, BRONZE | {"is_locked": True}, SOURCE | {"is_active": False})
    assert apply(p, change_set_id) == []
    assert state(p, change_set_id) == (
        {
            cat.erp_bronze: (True, True),  # added, and locked by hand
            cat.erp_source: (False, False),  # switched off, the row is kept
            cat.shared_bronze: (True, False),  # untouched
        },
        2,
        ("applied", p.ben, True),
    )


def test_switching_off_a_table_with_no_scope_row_adds_nothing(p):
    change_set_id = draft(p, BRONZE | {"is_active": False})
    assert apply(p, change_set_id) == []
    assert scope(p) == {}


def test_switching_a_table_back_on_reuses_its_row(p):
    add_row(p, p.cat.erp_bronze, active=False)
    row_id = "SELECT project_input_scope_id FROM project.project_input_scope WHERE object_id = %s"
    before = p.conn.execute(row_id, (p.cat.erp_bronze,)).fetchone()
    assert apply(p, draft(p, BRONZE)) == []
    assert p.conn.execute(row_id, (p.cat.erp_bronze,)).fetchone() == before
    assert scope(p) == {p.cat.erp_bronze: (True, False)}


def test_any_problem_means_nothing_is_saved(p):
    add_row(p, p.cat.erp_source)
    change_set_id = draft(p, BRONZE, SOURCE | {"is_active": False}, SILVER, FABRIKAM)
    before = state(p, change_set_id)
    assert apply(p, change_set_id) == [("SCOPE-001", 2), ("SCOPE-002", 3)]
    assert state(p, change_set_id) == before


def test_applying_twice_is_refused_the_second_time(p):
    change_set_id = draft(p, BRONZE)
    assert apply(p, change_set_id) == []
    after_first = state(p, change_set_id)
    assert apply(p, change_set_id) == [("CHANGE-SET-001", None), ("CHANGE-SET-002", None)]
    assert state(p, change_set_id) == after_first


def test_two_drafts_on_the_same_version_only_the_first_applies(p):
    first, second = draft(p, BRONZE), draft(p, SOURCE)
    assert apply(p, first) == []
    assert apply(p, second) == [("CHANGE-SET-002", None)]
    assert scope(p) == {p.cat.erp_bronze: (True, False)}


def test_viewer_cannot_apply(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-002", lambda: apply_draft(p.conn, p.cat.eve, change_set_id))
    assert scope(p) == {}


def test_without_the_tenant_lock_you_cannot_apply(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    refused("ACCESS-003", lambda: apply(p, change_set_id))
    assert scope(p) == {}


def test_locked_project_cannot_apply(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (p.project,))
    refused("CHANGE-SET-004", lambda: apply(p, change_set_id))
    assert scope(p) == {}


def test_mcp_without_mcp_access_cannot_apply(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-004", lambda: apply_draft(p.conn, p.ben, change_set_id, via_mcp=True))
    assert scope(p) == {}


def test_outsider_and_unknown_change_set_get_not_found(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-001", lambda: apply_draft(p.conn, p.cat.gus, change_set_id), kind=NotFound)
    refused("ACCESS-001", lambda: apply(p, -1), kind=NotFound)


# --- Rejecting a draft (3d3) -----------------------------------------------------------------------------------------


def reject(p, change_set_id, who=None):
    return [(x.rule_id, x.record) for x in reject_draft(p.conn, who or p.ben, change_set_id)]


def test_reject_records_who_and_changes_nothing_in_the_project(p):
    add_row(p, p.cat.erp_source)
    change_set_id = draft(p, BRONZE, SOURCE | {"is_active": False})
    before_scope, before_version, _ = state(p, change_set_id)
    assert reject(p, change_set_id) == []
    assert state(p, change_set_id) == (before_scope, before_version, ("rejected", p.ben, True))


def test_a_rejected_draft_cannot_be_applied_or_rejected_again(p):
    change_set_id = draft(p, BRONZE)
    assert reject(p, change_set_id) == []
    after = state(p, change_set_id)
    assert reject(p, change_set_id) == [("CHANGE-SET-001", None)]
    assert apply(p, change_set_id) == [("CHANGE-SET-001", None)]
    assert state(p, change_set_id) == after


def test_an_applied_draft_cannot_be_rejected(p):
    change_set_id = draft(p, BRONZE)
    assert apply(p, change_set_id) == []
    after = state(p, change_set_id)
    assert reject(p, change_set_id) == [("CHANGE-SET-001", None)]
    assert state(p, change_set_id) == after


def test_a_change_set_still_receiving_can_be_rejected_but_not_applied(p):
    """A push that was started and given up: Apply refuses it, Reject clears it (CHANGE-SET-001, changed Nov 21)."""
    change_set_id = draft(p, BRONZE)
    p.conn.execute(
        "UPDATE application.project_change_set SET project_change_set_status = 'receiving' WHERE project_change_set_id = %s",
        (change_set_id,),
    )
    before_scope, before_version, _ = state(p, change_set_id)
    assert apply(p, change_set_id) == [("CHANGE-SET-001", None)]
    assert reject(p, change_set_id) == []
    assert state(p, change_set_id) == (before_scope, before_version, ("rejected", p.ben, True))


def test_an_out_of_date_draft_can_still_be_rejected(p):
    """Ben's draft lost the race (CHANGE-SET-002); rejecting it is how it is cleared away."""
    first, second = draft(p, BRONZE), draft(p, SOURCE)
    assert apply(p, first) == []
    assert reject(p, second) == []
    assert state(p, second)[2][0] == "rejected"


def test_viewer_cannot_reject(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-002", lambda: reject(p, change_set_id, who=p.cat.eve))
    assert state(p, change_set_id)[2][0] == "draft"


def test_without_the_tenant_lock_you_cannot_reject(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (p.cat.erp,))
    refused("ACCESS-003", lambda: reject(p, change_set_id))
    assert state(p, change_set_id)[2][0] == "draft"


def test_locked_project_cannot_reject(p):
    change_set_id = draft(p, BRONZE)
    p.conn.execute("UPDATE project.project SET is_locked = TRUE WHERE project_id = %s", (p.project,))
    refused("CHANGE-SET-004", lambda: reject(p, change_set_id))
    assert state(p, change_set_id)[2][0] == "draft"


def test_mcp_without_mcp_access_cannot_reject(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-004", lambda: reject_draft(p.conn, p.ben, change_set_id, via_mcp=True))


def test_outsider_and_unknown_change_set_get_not_found_on_reject(p):
    change_set_id = draft(p, BRONZE)
    refused("ACCESS-001", lambda: reject(p, change_set_id, who=p.cat.gus), kind=NotFound)
    refused("ACCESS-001", lambda: reject(p, -1), kind=NotFound)


# --- Any part: records name rows by names, and the review shows what each one does (step 4c2) -------------------


def enrich(p, **fields):
    record = {"object_schema": "bronze_erp", "object_name": "orders"} | fields
    return make_draft(p.conn, p.ben, p.project, {"object_enrichment": [record]}, "Enrich orders")


def test_records_of_another_part_name_their_table_by_schema_and_name(p):
    add_row(p, p.cat.erp_bronze)
    assert apply(p, enrich(p, object_definition="Orders.", object_grain="One row per order.")) == []
    assert read_records(p.conn, p.ben, p.project, "object_enrichment") == [
        {"object_schema": "bronze_erp", "object_name": "orders", "object_definition": "Orders.",
         "object_grain": "One row per order.", "is_locked": False, "is_active": True}]


def test_the_review_counts_and_lists_changes_with_the_saved_values(p):
    add_row(p, p.cat.erp_bronze)
    assert apply(p, enrich(p, object_definition="Orders.", object_grain="One row per order.")) == []
    change_set_id = enrich(p, object_definition="Orders our customers place.")
    assert get_change_set(p.conn, p.ben, change_set_id)["counts"] == {
        "object_enrichment": {"added": 0, "changed": 1, "switched_off": 0, "unchanged": 0}}
    listed = list_changes(p.conn, p.ben, change_set_id, "object_enrichment")
    assert listed["changes"] == [{"change": "changed",
                                  "record": {"object_schema": "bronze_erp", "object_name": "orders",
                                             "object_definition": "Orders our customers place."},
                                  "current": {"object_definition": "Orders."}}]
    assert read_records(p.conn, p.ben, p.project, "object_enrichment")[0]["object_definition"] == "Orders."


def test_a_table_not_in_scope_is_change_set_003(p):
    assert check(p, enrich(p, object_definition="Orders.")) == [("CHANGE-SET-003", 0)]


def test_take_out_removes_one_record_from_a_draft(p):
    change_set_id = draft(p, SILVER, BRONZE)
    assert check(p, change_set_id) == [("SCOPE-001", 0)]
    from core.change_sets import take_out
    assert take_out(p.conn, p.ben, change_set_id, "project_input_scope", 0) == []
    assert check(p, change_set_id) == []
    assert apply(p, change_set_id) == []
    assert scope(p) == {p.cat.erp_bronze: (True, False)}


def test_a_note_and_its_new_group_in_one_draft(p):
    """A Note names its group by name, so a group added in the same draft is found (groups are saved first)."""
    documents = {"context_group": [{"context_group_name": "ERP facts", "context_type_code": "source_information",
                                    "system_code": "ERP_DB"}],
                 "context_record": [{"context_group_name": "ERP facts", "context_record_number": 1,
                                     "context_record_text": "VBAK holds sales order headers."}]}
    change_set_id = make_draft(p.conn, p.ben, p.project, documents, "A Note")
    assert apply(p, change_set_id) == []
    assert [r["context_record_text"] for r in read_records(p.conn, p.ben, p.project, "context_record")] == [
        "VBAK holds sales order headers."]
    unknown = {"context_group": [{"context_group_name": "X", "context_type_code": "no_such_type"}]}
    assert check(p, make_draft(p.conn, p.ben, p.project, unknown, "Bad type")) == [("CHANGE-SET-003", 0)]
