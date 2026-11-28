"""Tests for the web backend, web_app/backend/app.py (step 4a2), on the demo data (database/demo/).

The routes are thin doors into core/, so these tests check what only the door can get wrong: that every route is
refused for someone without access (proving it goes through `require`), that refusals come back with the right HTTP
status and rule ID, and that the whole scope loop works through HTTP. The database connection is the test's own,
rolled back at the end.
"""

import pytest
from fastapi.testclient import TestClient

from core.project_change_sets import make_scope_draft
from core.tenant_lock import take_lock
from web_app.backend.app import app, database

SAP_VBAK = {"tenant_code": "ACME", "system_code": "SAP_ERP", "connection_code": "sap_erp",
            "object_schema": "sap", "object_name": "VBAK", "is_active": True, "is_locked": False}
SF_ACCOUNT = {"tenant_code": "ACME", "system_code": "SALESFORCE_CRM", "connection_code": "salesforce_crm",
              "object_schema": "salesforce", "object_name": "Account", "is_active": True, "is_locked": False}
SILVER = {"tenant_code": "GDS", "system_code": "GDS_US", "connection_code": "gds_us",
          "object_schema": "silver_sales", "object_name": "sales_order", "is_active": True, "is_locked": False}


@pytest.fixture
def web(demo_data):
    """A client for the app on the test's connection, and a way to call it as a given demo email."""
    d = demo_data
    d.conn.execute("INSERT INTO security.principal (principal_email, principal_display_name) "
                   "VALUES ('olly@demo.local', 'Olly (no access)')")
    take_lock(d.conn, d.ben, d.acme)
    d.draft = make_scope_draft(d.conn, d.ben, d.sales, [SAP_VBAK], "A draft")

    def use_test_connection():
        yield d.conn

    app.dependency_overrides[database] = use_test_connection
    client = TestClient(app)

    def call(email, method, path, **kwargs):
        return client.request(method, path, headers={"X-Forwarded-Email": email}, **kwargs)

    d.call = call
    yield d
    app.dependency_overrides.clear()


# Every /api route as the app names it, with an example body. `change` routes need CHANGE; the rest need READ.
ROUTES = [
    ("GET", "/api/me", None, "me"),
    ("GET", "/api/tenants/{tenant_id}/tables", None, "read"),
    ("GET", "/api/tenants/{tenant_id}/projects", None, "read"),
    ("GET", "/api/tenants/{tenant_id}/lock", None, "read"),
    ("POST", "/api/tenants/{tenant_id}/lock", {}, "change"),
    ("DELETE", "/api/tenants/{tenant_id}/lock", None, "change"),
    ("POST", "/api/tenants/{tenant_id}/lock/override", None, "change"),
    ("GET", "/api/projects/{project_id}/scope", None, "read"),
    ("POST", "/api/projects/{project_id}/scope-drafts", {"title": "x", "records": [SAP_VBAK]}, "change"),
    ("GET", "/api/scope-drafts/{change_set_id}", None, "read"),
    ("POST", "/api/scope-drafts/{change_set_id}/apply", None, "change"),
    ("POST", "/api/scope-drafts/{change_set_id}/reject", None, "change"),
]


def routes(d):
    """The routes with the demo's ids filled in: tenant ACME, project Sales, and Ben's draft."""
    return [(method, path.format(tenant_id=d.acme, project_id=d.sales, change_set_id=d.draft), body, kind)
            for method, path, body, kind in ROUTES]


def test_every_api_route_is_in_the_route_list():
    """A new route must be added to ROUTES above, so the refusal tests below cover it."""
    in_app = {(method, route.path) for route in app.routes if route.path.startswith("/api")
              for method in route.methods}
    assert in_app == {(method, path) for method, path, _, _ in ROUTES}


def test_every_api_route_refuses_someone_not_signed_in(web):
    for method, path, body, _ in routes(web):
        for email in ("", "nobody@demo.local"):
            assert web.call(email, method, path, json=body).status_code == 401, (method, path, email)


def test_every_tenant_route_is_not_found_for_someone_without_access(web):
    for method, path, body, kind in routes(web):
        if kind == "me":
            continue
        answer = web.call("olly@demo.local", method, path, json=body)
        assert (answer.status_code, answer.json()["rule_id"]) == (404, "ACCESS-001"), (method, path)


def test_every_change_route_is_refused_for_a_viewer(web):
    for method, path, body, kind in routes(web):
        if kind != "change":
            continue
        answer = web.call("asha@demo.local", method, path, json=body)
        assert (answer.status_code, answer.json()["rule_id"]) == (403, "ACCESS-002"), (method, path)


def test_a_viewer_can_use_every_read_route(web):
    for method, path, body, kind in routes(web):
        if kind in ("read", "me"):
            assert web.call("asha@demo.local", method, path, json=body).status_code == 200, (method, path)


def test_someone_elses_lock_is_refused_with_who_holds_it(web):
    answer = web.call("cara@demo.local", "POST", f"/api/projects/{web.sales}/scope-drafts",
                      json={"title": "x", "records": [SAP_VBAK]})
    assert answer.status_code == 403
    assert answer.json()["rule_id"] == "ACCESS-003"
    assert "Ben (Developer)" in answer.json()["message"]


def test_a_record_of_the_wrong_shape_is_422(web):
    answer = web.call("ben@demo.local", "POST", f"/api/projects/{web.sales}/scope-drafts",
                      json={"title": "x", "records": [{"object_name": "VBAK"}]})
    assert answer.status_code == 422


def test_me_shows_the_user_and_their_tenants(web):
    body = web.call("BEN@demo.local", "GET", "/api/me").json()
    assert body["user"]["display_name"] == "Ben (Developer)"
    assert [(t["tenant_code"], t["role"]) for t in body["tenants"]] == [("ACME", "developer"), ("GDS", "viewer")]


def test_the_scope_loop_through_http(web):
    ben = lambda method, path, **kw: web.call("ben@demo.local", method, path, **kw)  # noqa: E731

    tables = ben("GET", f"/api/tenants/{web.acme}/tables", params={"scope_only": True}).json()
    assert tables["total"] == 28

    made = ben("POST", f"/api/projects/{web.sales}/scope-drafts",
               json={"title": "Sales scope", "records": [SAP_VBAK, SF_ACCOUNT, SILVER]})
    assert made.status_code == 201
    draft_id = made.json()["change_set_id"]

    draft = ben("GET", f"/api/scope-drafts/{draft_id}").json()
    assert (draft["title"], draft["status"], len(draft["records"])) == ("Sales scope", "draft", 3)
    assert [(p["rule_id"], p["record"]) for p in draft["problems"]] == [("SCOPE-001", 2)]

    refused = ben("POST", f"/api/scope-drafts/{draft_id}/apply").json()
    assert refused["applied"] is False and refused["problems"][0]["rule_id"] == "SCOPE-001"
    assert ben("POST", f"/api/scope-drafts/{draft_id}/reject").json() == {"rejected": True, "problems": []}

    draft_id = ben("POST", f"/api/projects/{web.sales}/scope-drafts",
                   json={"title": "Sales scope", "records": [SAP_VBAK, SF_ACCOUNT]}).json()["change_set_id"]
    assert ben("POST", f"/api/scope-drafts/{draft_id}/apply").json() == {"applied": True, "problems": []}

    scope = ben("GET", f"/api/projects/{web.sales}/scope").json()
    assert [(t["object_schema"], t["object_name"]) for t in scope] == [("salesforce", "Account"), ("sap", "VBAK")]

    assert ben("DELETE", f"/api/tenants/{web.acme}/lock").json() == {"released": True}
    assert ben("GET", f"/api/tenants/{web.acme}/lock").json() == {"lock": None}


def test_health_needs_no_sign_in(web):
    answer = TestClient(app).get("/health")
    assert answer.status_code == 200
    assert answer.json()["status"] == "ok"
