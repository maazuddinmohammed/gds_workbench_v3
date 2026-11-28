"""Tests for core/tenant_lock.py: taking, retaking, releasing and overriding the tenant lock (ACCESS-003, 008, 009).

The demo rows come from the `demo` fixture in conftest.py. Each test checks what is saved in the database, or what
the person is refused, never only what the code was told.
"""

from datetime import timedelta

import psycopg
import pytest

from core.access import CHANGE, require
from core.problems import NotFound, Refused
from core.tenant_lock import current_lock, override_lock, release_lock, take_lock


def lock_row(demo):
    """(holder, how long the lock was taken for, purpose) as saved, or None if the tenant has no lock row."""
    return demo.conn.execute(
        """SELECT locked_by_principal_id, tenant_lock_expires_time - tenant_lock_acquired_time, tenant_lock_purpose
             FROM security.tenant_lock WHERE tenant_id = %s""",
        (demo.contoso,),
    ).fetchone()


def refused(rule_id, call, kind=Refused):
    with pytest.raises(kind) as info:
        call()
    assert info.value.rule_id == rule_id
    return info.value


# --- Taking the lock -----------------------------------------------------------------------------------------------


def test_take_lock_for_the_time_you_choose(demo):
    lock = take_lock(demo.conn, demo.ben, demo.contoso, minutes=90, purpose="Scope for Retail")
    assert lock.locked_by_display_name == "Ben"
    assert lock_row(demo) == (demo.ben, timedelta(minutes=90), "Scope for Retail")


def test_take_lock_without_a_time_gives_60_minutes(demo):
    take_lock(demo.conn, demo.ben, demo.contoso)
    assert lock_row(demo)[1] == timedelta(minutes=60)


def test_take_lock_for_the_full_4_hours(demo):
    take_lock(demo.conn, demo.ben, demo.contoso, minutes=240)
    assert lock_row(demo)[1] == timedelta(hours=4)


@pytest.mark.parametrize("minutes", [0, -10, 241, 1.5, "60"])
def test_a_time_outside_1_minute_to_4_hours_is_refused(demo, minutes):
    refused("ACCESS-003", lambda: take_lock(demo.conn, demo.ben, demo.contoso, minutes=minutes))
    assert lock_row(demo) is None


def test_with_the_lock_you_can_change(demo):
    take_lock(demo.conn, demo.ben, demo.contoso)
    require(demo.conn, demo.ben, demo.contoso, CHANGE, project_id=demo.retail)


def test_lock_held_by_someone_else_is_refused_with_who_and_until_when(demo):
    take_lock(demo.conn, demo.cara, demo.contoso)
    problem = refused("ACCESS-003", lambda: take_lock(demo.conn, demo.ben, demo.contoso))
    assert "locked by Cara until" in problem.message
    assert lock_row(demo)[0] == demo.cara


def test_taking_your_own_lock_again_starts_your_time_over(demo):
    demo.lock(demo.contoso, demo.ben, minutes=10)  # taken 2 hours ago, 10 minutes left
    take_lock(demo.conn, demo.ben, demo.contoso, minutes=30)
    assert lock_row(demo)[:2] == (demo.ben, timedelta(minutes=30))
    assert current_lock(demo.conn, demo.asha, demo.contoso).expires_time > demo.conn.execute(
        "SELECT CURRENT_TIMESTAMP + INTERVAL '29 minutes'"
    ).fetchone()[0]


def test_an_ended_lock_is_replaced(demo):
    demo.lock(demo.contoso, demo.cara, minutes=-5)
    lock = take_lock(demo.conn, demo.ben, demo.contoso)
    assert lock.locked_by_principal_id == demo.ben
    assert lock_row(demo)[0] == demo.ben


def test_viewer_cannot_take_the_lock(demo):
    refused("ACCESS-002", lambda: take_lock(demo.conn, demo.asha, demo.contoso))
    assert lock_row(demo) is None


def test_outsider_gets_not_found(demo):
    refused("ACCESS-001", lambda: take_lock(demo.conn, demo.ben, demo.fabrikam), kind=NotFound)


def test_lock_can_be_taken_on_a_locked_catalog(demo):
    demo.conn.execute("UPDATE core.tenant SET is_metadata_locked = TRUE WHERE tenant_id = %s", (demo.contoso,))
    take_lock(demo.conn, demo.ben, demo.contoso)
    assert lock_row(demo)[0] == demo.ben


def test_mcp_needs_mcp_access_to_take_the_lock(demo):
    take_lock(demo.conn, demo.ben, demo.contoso, via_mcp=True)
    release_lock(demo.conn, demo.ben, demo.contoso)
    refused("ACCESS-004", lambda: take_lock(demo.conn, demo.cara, demo.contoso, via_mcp=True))
    assert lock_row(demo) is None


def test_anyone_who_reads_the_tenant_sees_who_holds_the_lock(demo):
    assert current_lock(demo.conn, demo.asha, demo.contoso) is None
    take_lock(demo.conn, demo.ben, demo.contoso)
    assert current_lock(demo.conn, demo.asha, demo.contoso).locked_by_display_name == "Ben"


def test_only_an_explicit_override_frees_someone_elses_lock(demo):
    """While Cara holds the lock, every other way in is refused and her lock stays exactly as it was: taking the
    lock, releasing it, any change in the web app or through MCP, and a Super Admin's change. Only override_lock
    frees it."""
    take_lock(demo.conn, demo.cara, demo.contoso, minutes=60)
    before = demo.conn.execute("SELECT * FROM security.tenant_lock WHERE tenant_id = %s", (demo.contoso,)).fetchone()

    refused("ACCESS-003", lambda: take_lock(demo.conn, demo.ben, demo.contoso))
    refused("ACCESS-003", lambda: take_lock(demo.conn, demo.ben, demo.contoso, via_mcp=True))
    refused("ACCESS-003", lambda: take_lock(demo.conn, demo.sam, demo.contoso))
    refused("ACCESS-003", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, project_id=demo.retail))
    refused("ACCESS-003", lambda: require(demo.conn, demo.ben, demo.contoso, CHANGE, via_mcp=True))
    refused("ACCESS-003", lambda: require(demo.conn, demo.sam, demo.contoso, CHANGE))
    refused("ACCESS-003", lambda: release_lock(demo.conn, demo.ben, demo.contoso))

    after = demo.conn.execute("SELECT * FROM security.tenant_lock WHERE tenant_id = %s", (demo.contoso,)).fetchone()
    assert after == before


# --- Releasing your own lock and overriding someone else's --------------------------------------------------------


def test_release_your_own_lock_frees_the_tenant(demo):
    take_lock(demo.conn, demo.ben, demo.contoso)
    assert release_lock(demo.conn, demo.ben, demo.contoso) is True
    assert lock_row(demo) is None
    take_lock(demo.conn, demo.cara, demo.contoso)
    assert lock_row(demo)[0] == demo.cara


def test_release_someone_elses_lock_is_refused_with_who_holds_it(demo):
    take_lock(demo.conn, demo.cara, demo.contoso)
    problem = refused("ACCESS-003", lambda: release_lock(demo.conn, demo.sam, demo.contoso))
    assert "locked by Cara" in problem.message
    assert lock_row(demo)[0] == demo.cara


@pytest.mark.parametrize(("overrider", "holder"), [("ben", "cara"), ("cara", "ben"), ("sam", "ben")])
def test_anyone_who_may_change_overrides_someone_elses_lock(demo, overrider, holder):
    """Developer, Tenant Admin and Super Admin can each end another person's lock. It is not handed over: the
    tenant is free until they take it themselves."""
    overrider, holder = getattr(demo, overrider), getattr(demo, holder)
    take_lock(demo.conn, holder, demo.contoso)
    ended = override_lock(demo.conn, overrider, demo.contoso)
    assert ended.locked_by_principal_id == holder  # so the web app can say whose lock it was
    assert lock_row(demo) is None
    take_lock(demo.conn, overrider, demo.contoso)
    assert lock_row(demo)[0] == overrider


def test_after_their_lock_is_overridden_the_old_holder_cannot_change(demo):
    take_lock(demo.conn, demo.cara, demo.contoso)
    override_lock(demo.conn, demo.ben, demo.contoso)
    problem = refused("ACCESS-003", lambda: require(demo.conn, demo.cara, demo.contoso, CHANGE))
    assert "Take the lock" in problem.message


def test_release_and_override_with_no_lock_say_nobody_held_it(demo):
    assert release_lock(demo.conn, demo.ben, demo.contoso) is False
    assert override_lock(demo.conn, demo.ben, demo.contoso) is None


def test_an_ended_lock_counts_as_nobodys(demo):
    demo.lock(demo.contoso, demo.cara, minutes=-5)
    assert release_lock(demo.conn, demo.ben, demo.contoso) is False
    assert override_lock(demo.conn, demo.ben, demo.contoso) is None


def test_viewer_cannot_release_or_override_a_lock(demo):
    take_lock(demo.conn, demo.ben, demo.contoso)
    refused("ACCESS-002", lambda: release_lock(demo.conn, demo.asha, demo.contoso))
    refused("ACCESS-002", lambda: override_lock(demo.conn, demo.asha, demo.contoso))
    assert lock_row(demo)[0] == demo.ben


def test_mcp_needs_mcp_access_to_release_or_override_a_lock(demo):
    take_lock(demo.conn, demo.ben, demo.contoso)
    refused("ACCESS-004", lambda: override_lock(demo.conn, demo.cara, demo.contoso, via_mcp=True))
    assert lock_row(demo)[0] == demo.ben


# --- What the database itself refuses ------------------------------------------------------------------------------


def test_database_keeps_one_lock_per_tenant(demo):
    """ACCESS-008: if two people take the lock at the same moment, the database lets only one row in."""
    demo.lock(demo.contoso, demo.cara)
    with pytest.raises(psycopg.errors.UniqueViolation), demo.conn.transaction():
        demo.lock(demo.contoso, demo.ben)


def test_database_refuses_a_lock_longer_than_4_hours(demo):
    """ACCESS-009."""
    with pytest.raises(psycopg.errors.CheckViolation), demo.conn.transaction():
        demo.conn.execute(
            """INSERT INTO security.tenant_lock (tenant_id, locked_by_principal_id, tenant_lock_expires_time)
               VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '5 hours')""",
            (demo.contoso, demo.ben),
        )
