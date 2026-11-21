"""Tests for the MCP server, mcp_server/app.py (step 4b2), on the demo data (database/demo/).

The tool is a thin door into core/, so these tests check what only the door can get wrong: who you are (the local
setting, or App Service's sign-in header on Azure, including another Microsoft tenant), that the call goes through
`require` with `via_mcp=True` (ACCESS-004 refuses a member without MCP access, while the web app lets them read),
that refusals name their rule ID, and that the scope comes back through MCP's own HTTP protocol. The database
connection is the test's own, rolled back at the end.
"""

import base64
import json

import pytest
from starlette.testclient import TestClient

import mcp_server.app as mcp_app
from core.project_change_sets import apply_scope_draft, make_scope_draft
from core.tenant_lock import take_lock

TENANT = "11111111-2222-4333-8444-555555555555"
BEN = "00000000-0000-4000-8000-000000000003"  # demo object IDs, database/demo/01_access.sql
ASHA = "00000000-0000-4000-8000-000000000002"
OLLY = "00000000-0000-4000-8000-0000000000aa"

SAP_VBAK = {"tenant_code": "ACME", "system_code": "SAP_ERP", "connection_code": "sap_erp",
            "object_schema": "sap", "object_name": "VBAK", "is_active": True, "is_locked": False}


class Borrowed:
    """The test's connection, lent to the server without letting it close it."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


@pytest.fixture
def mcp(demo_data, monkeypatch):
    """The MCP app on the test's connection, with Sales holding SAP VBAK in scope, and a way to call a tool."""
    d = demo_data
    d.conn.execute("INSERT INTO security.principal (principal_email, principal_display_name, entra_object_id) "
                   "VALUES ('olly@demo.local', 'Olly (no access)', %s)", (OLLY,))
    take_lock(d.conn, d.ben, d.acme)
    draft = make_scope_draft(d.conn, d.ben, d.sales, [SAP_VBAK], "Add VBAK")
    assert apply_scope_draft(d.conn, d.ben, draft) == []
    monkeypatch.setattr(mcp_app, "open_database", lambda: Borrowed(d.conn))
    monkeypatch.setenv("GDS_ENVIRONMENT", "local")
    monkeypatch.setenv("GDS_MCP_PUBLIC_URL", "https://gds-mcp.example.net/mcp")
    monkeypatch.setenv("GDS_ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", BEN)

    with TestClient(mcp_app.create_app(), base_url="http://127.0.0.1:8001") as client:
        def call(tool, arguments, headers=None, host=None):
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": tool, "arguments": arguments}},
                headers={"Accept": "application/json, text/event-stream", **({"Host": host} if host else {}),
                         **(headers or {})},
            )
            return response

        d.call = call
        d.client = client
        yield d


def result(response):
    """(is_error, answer): the scope rows, or the error text."""
    assert response.status_code == 200, response.text
    body = response.json()["result"]
    if body.get("isError"):
        return True, body["content"][0]["text"]
    return False, body["structuredContent"]["result"]


def easy_auth(object_id, tenant=TENANT):
    """The header App Service sign-in sends: base64 JSON with the token's claims."""
    claims = [{"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": tenant},
              {"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": object_id},
              {"typ": "name", "val": "Someone"}]
    encoded = base64.b64encode(json.dumps({"auth_typ": "aad", "claims": claims}).encode()).decode()
    return {"X-MS-CLIENT-PRINCIPAL": encoded}


def test_health(mcp):
    assert mcp.client.get("/health").json() == {"status": "ok", "version": "local", "environment": "local"}


def test_local_user_sees_the_project_scope(mcp):
    is_error, rows = result(mcp.call("see_project_scope", {"project_id": mcp.sales}))

    assert not is_error
    assert [(r["tenant_code"], r["connection_code"], r["object_schema"], r["object_name"], r["zone_code"])
            for r in rows] == [("ACME", "sap_erp", "sap", "VBAK", "source")]


def test_member_without_mcp_access_is_refused_by_access_004(mcp):
    mcp.conn.execute("UPDATE security.tenant_principal_access SET mcp_access_enabled = FALSE "
                     "WHERE principal_id = %s AND tenant_id = %s", (mcp.ben, mcp.acme))

    is_error, text = result(mcp.call("see_project_scope", {"project_id": mcp.sales}))

    assert is_error and "ACCESS-004: You do not have MCP access" in text


def test_outsider_gets_not_found_access_001(mcp, monkeypatch):
    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", OLLY)

    is_error, text = result(mcp.call("see_project_scope", {"project_id": mcp.sales}))

    assert is_error and "ACCESS-001:" in text


@pytest.mark.parametrize("object_id", ["00000000-0000-4000-8000-0000000000ff", "not-a-uuid"])
def test_unknown_local_user_is_not_signed_in(mcp, monkeypatch, object_id):
    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", object_id)

    is_error, text = result(mcp.call("see_project_scope", {"project_id": mcp.sales}))

    assert is_error and "not signed in" in text


def test_on_azure_the_sign_in_header_says_who_you_are(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")

    is_error, rows = result(mcp.call("see_project_scope", {"project_id": mcp.sales}, headers=easy_auth(ASHA),
                                     host="gds-mcp.example.net"))

    assert not is_error and [r["object_name"] for r in rows] == ["VBAK"]


def test_on_azure_the_local_setting_is_ignored_and_no_header_is_refused(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")

    is_error, text = result(mcp.call("see_project_scope", {"project_id": mcp.sales}, host="gds-mcp.example.net"))

    assert is_error and "not signed in" in text


def test_on_azure_a_sign_in_from_another_microsoft_tenant_is_refused(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")
    other_tenant = easy_auth(ASHA, tenant="99999999-2222-4333-8444-555555555555")

    is_error, text = result(mcp.call("see_project_scope", {"project_id": mcp.sales}, headers=other_tenant,
                                     host="gds-mcp.example.net"))

    assert is_error and "not signed in" in text


def test_a_request_for_another_host_is_turned_away(mcp):
    response = mcp.call("see_project_scope", {"project_id": mcp.sales}, host="evil.example.com")

    assert response.status_code == 421
