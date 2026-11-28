"""Tests for snapshots and pushes (core/snapshot.py): what a pull's zip holds and how a pushed zip is loaded into a
change set. Azure storage cannot be reached locally, so the zips go in and out as bytes."""

import io
import json
import zipfile

import pytest

from core import change_sets, snapshot
from core.problems import Refused
from core.tenant_lock import take_lock
from tests_helpers import apply_scope_draft, make_scope_draft

VBAK = {"tenant_code": "ACME", "system_code": "SAP_ERP", "connection_code": "sap_erp", "object_schema": "sap",
        "object_name": "VBAK", "is_active": True}
KNA1 = VBAK | {"object_name": "KNA1"}


@pytest.fixture
def d(demo_data):
    take_lock(demo_data.conn, demo_data.ben, demo_data.acme)
    assert apply_scope_draft(demo_data.conn, demo_data.ben, make_scope_draft(demo_data.conn, demo_data.ben, demo_data.sales, [VBAK], "VBAK")) == []
    return demo_data


def files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {name: z.read(name).decode() for name in z.namelist()}


def zipped(found):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, text in found.items():
            z.writestr(name, text)
    return buffer.getvalue()


def test_a_snapshot_holds_the_version_and_one_line_per_scope_row(d):
    snapshot_id, version, data = snapshot.create(d.conn, d.asha, d.sales)  # a Viewer may pull
    found = files(data)
    assert json.loads(found["gds.json"])["project_version"] == version == 2
    lines = [json.loads(line) for line in found["scope.jsonl"].splitlines()]
    assert lines == [{"tenant_code": "ACME", "system_code": "SAP_ERP", "connection_code": "sap_erp",
                      "object_schema": "sap", "object_name": "VBAK", "is_locked": False, "is_active": True}]
    assert "scope.jsonl" in found["README.md"]


def test_a_push_loads_every_line_into_one_change_set_that_reviews_like_any_other(d):
    _, _, data = snapshot.create(d.conn, d.ben, d.sales)
    found = files(data)
    found["scope.jsonl"] += json.dumps(KNA1) + "\n"
    change_set_id = snapshot.start(d.conn, d.ben, d.sales, "Add KNA1")
    assert snapshot.next_upload(d.conn, d.ben, change_set_id) == 1
    summary = snapshot.load(d.conn, d.ben, change_set_id, 1, zipped(found))
    assert summary["project_change_set_status"] == "draft"
    assert summary["counts"] == {"project_input_scope": {"added": 1, "changed": 0, "switched_off": 0, "unchanged": 1}}
    assert snapshot.next_upload(d.conn, d.ben, change_set_id) == 2
    assert change_sets.apply(d.conn, d.ben, change_set_id) == []


def test_a_push_built_on_an_older_version_is_refused_before_review(d):
    _, _, data = snapshot.create(d.conn, d.ben, d.sales)
    assert apply_scope_draft(d.conn, d.ben, make_scope_draft(d.conn, d.ben, d.sales, [KNA1], "KNA1")) == []
    change_set_id = snapshot.start(d.conn, d.ben, d.sales, "Late push")
    with pytest.raises(Refused) as info:
        snapshot.load(d.conn, d.ben, change_set_id, 1, data)
    assert info.value.rule_id == "CHANGE-SET-002"


def test_a_line_that_is_not_json_stops_the_load_and_names_the_line(d):
    _, _, data = snapshot.create(d.conn, d.ben, d.sales)
    found = files(data)
    found["scope.jsonl"] += "{not json\n"
    change_set_id = snapshot.start(d.conn, d.ben, d.sales, "Broken")
    with pytest.raises(ValueError, match="scope.jsonl line 2"):
        snapshot.load(d.conn, d.ben, change_set_id, 1, zipped(found))
