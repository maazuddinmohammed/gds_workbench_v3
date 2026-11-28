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
from tests_helpers import apply_scope_draft, check_scope_draft, make_scope_draft
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
    """(is_error, answer): the tool's answer, or the error text."""
    assert response.status_code == 200, response.text
    body = response.json()["result"]
    if body.get("isError"):
        return True, body["content"][0]["text"]
    if "structuredContent" in body:
        return False, body["structuredContent"]["result"]
    return False, json.loads(body["content"][0]["text"])


def easy_auth(object_id, tenant=TENANT):
    """The header App Service sign-in sends: base64 JSON with the token's claims."""
    claims = [{"typ": "http://schemas.microsoft.com/identity/claims/tenantid", "val": tenant},
              {"typ": "http://schemas.microsoft.com/identity/claims/objectidentifier", "val": object_id},
              {"typ": "name", "val": "Someone"}]
    encoded = base64.b64encode(json.dumps({"auth_typ": "aad", "claims": claims}).encode()).decode()
    return {"X-MS-CLIENT-PRINCIPAL": encoded}


def test_health_live_says_up_and_which_build(mcp):
    assert mcp.client.get("/health/live").json() == {"status": "live", "version": "local", "environment": "local"}


def test_health_ready_checks_the_database(mcp, monkeypatch):
    assert mcp.client.get("/health/ready").json()["status"] == "ready"

    def no_database():
        raise OSError("database down")

    monkeypatch.setattr(mcp_app, "open_database", no_database)
    response = mcp.client.get("/health/ready")
    assert (response.status_code, response.json()["status"]) == (503, "not_ready")


@pytest.mark.parametrize("path", ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"])
def test_sign_in_page_points_vs_code_at_microsoft_for_this_server(mcp, monkeypatch, path):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")

    answer = mcp.client.get(path, headers={"Host": "gds-mcp.example.net"}).json()

    assert answer == {
        "resource": "https://gds-mcp.example.net/mcp",
        "authorization_servers": [f"https://login.microsoftonline.com/{TENANT}/v2.0"],
        "scopes_supported": ["https://gds-mcp.example.net/mcp/workbench.access"],
        "bearer_methods_supported": ["header"],
    }


def test_local_user_reads_the_project(mcp):
    is_error, answer = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}))

    assert not is_error and answer["row_counts"]["project_input_scope"] == 1


def test_member_without_mcp_access_is_refused_by_access_004(mcp):
    mcp.conn.execute("UPDATE security.tenant_principal_access SET mcp_access_enabled = FALSE "
                     "WHERE principal_id = %s AND tenant_id = %s", (mcp.ben, mcp.acme))

    is_error, text = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}))

    assert is_error and "ACCESS-004: You do not have MCP access" in text


def test_outsider_gets_not_found_access_001(mcp, monkeypatch):
    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", OLLY)

    is_error, text = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}))

    assert is_error and "ACCESS-001:" in text


@pytest.mark.parametrize("object_id", ["00000000-0000-4000-8000-0000000000ff", "not-a-uuid"])
def test_unknown_local_user_is_not_signed_in(mcp, monkeypatch, object_id):
    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", object_id)

    is_error, text = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}))

    assert is_error and "not signed in" in text


def test_on_azure_the_sign_in_header_says_who_you_are(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")

    is_error, rows = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}, headers=easy_auth(ASHA),
                                     host="gds-mcp.example.net"))

    assert not is_error and rows["project_name"] == "Sales"


def test_on_azure_the_local_setting_is_ignored_and_no_header_is_refused(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")

    is_error, text = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}, host="gds-mcp.example.net"))

    assert is_error and "not signed in" in text


def test_on_azure_a_sign_in_from_another_microsoft_tenant_is_refused(mcp, monkeypatch):
    monkeypatch.setenv("GDS_ENVIRONMENT", "production")
    other_tenant = easy_auth(ASHA, tenant="99999999-2222-4333-8444-555555555555")

    is_error, text = result(mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}, headers=other_tenant,
                                     host="gds-mcp.example.net"))

    assert is_error and "not signed in" in text


def test_a_request_for_another_host_is_turned_away(mcp):
    response = mcp.call("get_project_detail", {"tenant_code": "ACME", "project_name": "Sales"}, host="evil.example.com")

    assert response.status_code == 421


# --- Tenants, projects and the tenant lock (design/operations/shared.md) ------------------------------------------

CARA = "00000000-0000-4000-8000-000000000004"


def test_list_tenants_gives_your_role_and_switches_by_code_without_ids(mcp):
    is_error, answer = result(mcp.call("list_tenants", {}))

    assert not is_error and answer["user"]["principal_display_name"].startswith("Ben")
    acme = next(t for t in answer["tenants"] if t["tenant_code"] == "ACME")
    assert (acme["tenant_role"], acme["mcp_access_enabled"], acme["permissions"]) == ("developer", True,
                                                                                     ["CHANGE", "READ"])
    assert acme["data_lake_connection"] == {"tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us"}
    assert "tenant_id" not in acme


def test_get_project_detail_counts_the_active_rows(mcp):
    is_error, answer = result(mcp.call("get_project_detail", {"tenant_code": "acme", "project_name": "SALES"}))

    assert not is_error
    assert (answer["project_name"], answer["project_version"]) == ("Sales", 2)  # one Apply so far
    assert answer["row_counts"]["project_input_scope"] == 1


def test_an_unknown_tenant_code_is_not_found(mcp):
    is_error, text = result(mcp.call("list_projects", {"tenant_code": "NOPE"}))

    assert is_error and "ACCESS-001: Tenant not found" in text


def test_the_lock_tools_release_your_own_and_override_someone_elses(mcp, monkeypatch):
    def tool(name):
        return result(mcp.call(name, {"tenant_code": "ACME"}))[1]

    assert tool("check_tenant_lock")["is_yours"] is True
    assert tool("release_tenant_lock") == {"tenant_code": "ACME", "released": True}
    assert tool("check_tenant_lock") == {"tenant_code": "ACME", "is_locked": False}

    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", CARA)
    assert tool("acquire_tenant_lock")["locked_by_display_name"] == "Cara (Tenant Admin)"

    monkeypatch.setenv("GDS_LOCAL_PRINCIPAL_OBJECT_ID", BEN)
    is_error, text = result(mcp.call("release_tenant_lock", {"tenant_code": "ACME"}))
    assert is_error and "ACCESS-003:" in text and "Cara" in text
    overridden = tool("override_tenant_lock")
    assert (overridden["overridden"], overridden["was_locked_by_display_name"]) == (True, "Cara (Tenant Admin)")
    assert tool("check_tenant_lock") == {"tenant_code": "ACME", "is_locked": False}


# --- Change sets through MCP (design/operations/change-sets.md) --------------------------------------------------

SF_ACCOUNT = {"tenant_code": "ACME", "system_code": "SALESFORCE_CRM", "connection_code": "salesforce_crm",
              "object_schema": "salesforce", "object_name": "Account", "is_active": True, "is_locked": False}
SILVER = {"tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
          "object_schema": "silver_sales", "object_name": "sales_order", "is_active": True, "is_locked": False}


def test_review_and_apply_a_change_set_through_the_tools(mcp):
    draft = make_scope_draft(mcp.conn, mcp.ben, mcp.sales, [SF_ACCOUNT, SILVER], "Two tables")

    is_error, problems = result(mcp.call("validate_change_set", {"kind": "project", "change_set_id": draft}))
    assert not is_error and problems["can_apply"] is False
    assert [(p["rule_id"], p["record"], p["row_key"]["object_name"]) for p in problems["problems"]][0] == (
        "SCOPE-001", 1, "sales_order")

    is_error, summary = result(mcp.call("get_change_set", {"kind": "project", "change_set_id": draft}))
    assert summary["counts"] == {"project_input_scope": {"added": 2, "changed": 0, "switched_off": 0, "unchanged": 0}}

    is_error, listed = result(mcp.call("list_change_sets", {"kind": "project", "tenant_code": "ACME", "status": "draft"}))
    assert listed["change_sets"][0]["project_change_set_id"] == draft

    is_error, applied = result(mcp.call("apply_change_set", {"kind": "project", "change_set_id": draft}))
    assert applied["applied"] is False and applied["problems"][0]["rule_id"] == "SCOPE-001"
    assert result(mcp.call("reject_change_set", {"kind": "project", "change_set_id": draft}))[1]["rejected"] is True

    draft = make_scope_draft(mcp.conn, mcp.ben, mcp.sales, [SF_ACCOUNT], "Account")
    is_error, changes = result(mcp.call("list_change_set_changes", {"kind": "project", "change_set_id": draft,
                                                                     "part": "project_input_scope"}))
    assert [c["record"]["object_name"] for c in changes["changes"]] == ["Account"]
    is_error, applied = result(mcp.call("apply_change_set", {"kind": "project", "change_set_id": draft}))
    assert (applied["applied"], applied["project_version"]) == (True, 3)


def test_metadata_change_sets_are_not_built_yet(mcp):
    is_error, text = result(mcp.call("get_change_set", {"kind": "metadata", "change_set_id": 1}))
    assert is_error and "Only kind" in text
