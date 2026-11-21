"""The tenant lock: one person at a time may change a tenant (ACCESS-003).

Taking the lock gives it to you for as long as you choose, up to 4 hours (60 minutes if you do not say), or tells
you who holds it and until when. Taking it again while you hold it starts your time over. A lock past its end time
counts as no lock, and the next person to take the lock replaces it. Anyone who may change the tenant may release
its lock, their own or someone else's; the web app and the plugin ask them to confirm first. There is no lock
history (design.md).

`core/` writes inside `conn.transaction()`, so each call saves all of its changes or none. The apps pass an
autocommit connection, which makes each call its own transaction.
"""

from dataclasses import dataclass
from datetime import datetime

from psycopg import errors
from psycopg.rows import dict_row

from core.access import CHANGE, READ, access_003, require
from core.problems import Refused

DEFAULT_MINUTES = 60
MAX_MINUTES = 4 * 60  # the most the database allows (ck_tenant_lock_interval, ACCESS-009)


@dataclass(frozen=True)
class TenantLock:
    """Who holds a tenant's lock, and until when."""

    tenant_id: int
    locked_by_principal_id: int
    locked_by_display_name: str
    expires_time: datetime
    purpose: str | None = None


def current_lock(conn, principal_id, tenant_id, via_mcp=False):
    """The tenant's lock if someone holds it now, otherwise None. Anyone who can read the tenant may ask."""
    require(conn, principal_id, tenant_id, READ, via_mcp=via_mcp)
    with conn.cursor(row_factory=dict_row) as cur:
        row = _read_lock(cur, tenant_id, only_current=True)
    return None if row is None else _to_lock(tenant_id, row)


def take_lock(conn, principal_id, tenant_id, minutes=DEFAULT_MINUTES, purpose=None, via_mcp=False):
    """Take the tenant's lock for `minutes` (1 to 240), and return it.

    Refused (ACCESS-003) if someone else holds it; the message says who and until when. To take it anyway, release
    their lock first with `release_lock`.
    """
    require(conn, principal_id, tenant_id, CHANGE, via_mcp=via_mcp, taking_lock=True)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= MAX_MINUTES:
        raise Refused(
            "ACCESS-003", f"A lock lasts from 1 minute to {MAX_MINUTES // 60} hours. You asked for {minutes!r}."
        )
    purpose = purpose.strip() if purpose and purpose.strip() else None
    try:
        with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
            lock = _read_lock(cur, tenant_id, only_current=False, for_update=True)
            if lock is not None and lock["is_current"] and lock["locked_by_principal_id"] != principal_id:
                access_003(lock, principal_id, _tenant(cur, tenant_id))  # says who holds it and until when
            if lock is None:
                cur.execute(
                    """INSERT INTO security.tenant_lock
                           (tenant_id, locked_by_principal_id, tenant_lock_purpose, tenant_lock_expires_time)
                       VALUES (%s, %s, %s, CURRENT_TIMESTAMP + make_interval(mins => %s))""",
                    (tenant_id, principal_id, purpose, minutes),
                )
            else:
                # Your own lock starts over; an ended lock of anyone is replaced by yours.
                cur.execute(
                    """UPDATE security.tenant_lock
                          SET locked_by_principal_id = %s,
                              tenant_lock_purpose = %s,
                              tenant_lock_acquired_time = CURRENT_TIMESTAMP,
                              tenant_lock_expires_time = CURRENT_TIMESTAMP + make_interval(mins => %s),
                              updated_time = CURRENT_TIMESTAMP,
                              updated_by = CURRENT_USER
                        WHERE tenant_id = %s""",
                    (principal_id, purpose, minutes, tenant_id),
                )
    except errors.UniqueViolation:
        # Someone took the lock at the same moment; the database let only one row in (ACCESS-008).
        with conn.cursor(row_factory=dict_row) as cur:
            access_003(_read_lock(cur, tenant_id, only_current=True), principal_id, _tenant(cur, tenant_id))
    return current_lock(conn, principal_id, tenant_id, via_mcp=via_mcp)


def release_lock(conn, principal_id, tenant_id, via_mcp=False):
    """Release the tenant's lock, whoever holds it, so the tenant is free at once.

    Anyone who may change the tenant may do this: Developers, Tenant Admins and Super Admins, for their own lock or
    someone else's. Returns the lock that was released, so the caller can say whose it was, or None if nobody held
    one. Asking the person to confirm is the web app's and the plugin's job, not core/'s.
    """
    require(conn, principal_id, tenant_id, CHANGE, via_mcp=via_mcp, taking_lock=True)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        row = _read_lock(cur, tenant_id, only_current=False, for_update=True)
        cur.execute("DELETE FROM security.tenant_lock WHERE tenant_id = %s", (tenant_id,))
    if row is None or not row["is_current"]:
        return None
    return _to_lock(tenant_id, row)


def _read_lock(cur, tenant_id, only_current, for_update=False):
    cur.execute(
        f"""SELECT l.locked_by_principal_id, l.tenant_lock_expires_time, l.tenant_lock_purpose,
                   p.principal_display_name AS locked_by_display_name,
                   l.tenant_lock_expires_time > CURRENT_TIMESTAMP AS is_current
              FROM security.tenant_lock AS l
              JOIN security.principal AS p ON p.principal_id = l.locked_by_principal_id
             WHERE l.tenant_id = %s
             {"FOR UPDATE OF l" if for_update else ""}""",
        (tenant_id,),
    )
    row = cur.fetchone()
    if row is None or (only_current and not row["is_current"]):
        return None
    return row


def _to_lock(tenant_id, row):
    return TenantLock(
        tenant_id=tenant_id,
        locked_by_principal_id=row["locked_by_principal_id"],
        locked_by_display_name=row["locked_by_display_name"],
        expires_time=row["tenant_lock_expires_time"],
        purpose=row["tenant_lock_purpose"],
    )


def _tenant(cur, tenant_id):
    cur.execute("SELECT tenant_name FROM core.tenant WHERE tenant_id = %s", (tenant_id,))
    return cur.fetchone()
