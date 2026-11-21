// Run with: npm test (Node's own test runner; no extra package).

import { test } from "node:test";
import assert from "node:assert/strict";
import type { CatalogTable, ScopeTable } from "./api.ts";
import { addTable, inScopeAfter, removeTable, rowKey, undo } from "./scopeChanges.ts";
import type { Pending } from "./scopeChanges.ts";

function table(schema: string, name: string, connectionTenant: string, connection: string, system: string): CatalogTable {
  return {
    object_id: 1, object_schema: schema, object_name: name, zone_code: "bronze", object_type_code: "TABLE",
    source_tenant_code: "ACME", source_tenant_name: "Acme Retail", is_global: false,
    connection_tenant_code: connectionTenant, connection_code: connection, system_code: system,
    is_active: true, can_scope: true,
  };
}

function scopeRow(schema: string, name: string, active: boolean, locked: boolean): ScopeTable {
  return {
    tenant_code: "ACME", system_code: "SAP_ERP", connection_code: "sap_erp", object_schema: schema,
    object_name: name, zone_code: "source", source_tenant_code: "ACME", is_active: active, is_locked: locked,
    table_is_active: true,
  };
}

const VBAK = table("sap", "VBAK", "ACME", "sap_erp", "SAP_ERP");
const BRONZE = table("bronze_sap", "vbak", "GDS", "gds_us", "GDS_US");
const none: Pending = new Map();

test("adding a table not in scope makes a record named by its connection's tenant", () => {
  const records = [...addTable(none, [], BRONZE).values()];
  assert.deepEqual(records, [{
    tenant_code: "GDS", system_code: "GDS_US", connection_code: "gds_us", object_schema: "bronze_sap",
    object_name: "vbak", is_active: true, is_locked: false,
  }]);
});

test("adding a table already in scope makes no record", () => {
  assert.equal(addTable(none, [scopeRow("sap", "VBAK", true, false)], VBAK).size, 0);
});

test("taking out a locked row switches it off and keeps its lock", () => {
  const row = scopeRow("sap", "VBAK", true, true);
  const records = [...removeTable(none, [row], row).values()];
  assert.equal(records.length, 1);
  assert.equal(records[0].is_active, false);
  assert.equal(records[0].is_locked, true);
});

test("putting back a row taken out earlier switches it on and keeps its lock", () => {
  const records = [...addTable(none, [scopeRow("sap", "VBAK", false, true)], VBAK).values()];
  assert.equal(records[0].is_active, true);
  assert.equal(records[0].is_locked, true);
});

test("adding back a table you just took out cancels the change", () => {
  const scope = [scopeRow("sap", "VBAK", true, false)];
  const removed = removeTable(none, scope, scope[0]);
  assert.equal(inScopeAfter(removed, scope, scope[0]), false);
  const back = addTable(removed, scope, VBAK);
  assert.equal(back.size, 0);
  assert.equal(inScopeAfter(back, scope, scope[0]), true);
});

test("undo forgets one change and keeps the others", () => {
  const two = addTable(addTable(none, [], VBAK), [], BRONZE);
  const left = undo(two, rowKey(scopeRow("sap", "VBAK", true, false)));
  assert.deepEqual([...left.values()].map((r) => r.object_name), ["vbak"]);
});
