// Turning Add and Remove clicks into the records of a scope draft (core/project_change_sets.py).
//
// A record names a table by its row key (its connection's tenant, system and connection, then schema and name) and
// says what the project's scope row should be: is_active (in scope or taken out) and is_locked. Taking a table out
// never deletes its row; it switches it off (SCOPE-004), and a table put back switches the same row on again.
// Only real changes become records: adding a table already in scope, or taking out one already out, is nothing.
// The rules themselves (which tables may be in scope, locks, versions) are checked by the backend, not here.

import type { CatalogTable, ScopeRecord, ScopeTable } from "./api.ts";

export type Pending = Map<string, ScopeRecord>;

type RowKey = Pick<ScopeRecord, "tenant_code" | "system_code" | "connection_code" | "object_schema" | "object_name">;

export function rowKey(key: RowKey): string {
  return [key.tenant_code, key.system_code, key.connection_code, key.object_schema, key.object_name].join("|");
}

export function keyOfTable(table: CatalogTable): RowKey {
  return {
    tenant_code: table.connection_tenant_code,
    system_code: table.system_code,
    connection_code: table.connection_code,
    object_schema: table.object_schema,
    object_name: table.object_name,
  };
}

function scopeRow(scope: ScopeTable[], key: RowKey): ScopeTable | undefined {
  return scope.find((row) => rowKey(row) === rowKey(key));
}

/** Put a table in scope. `scope` is the project's scope now, rows taken out included. */
export function addTable(pending: Pending, scope: ScopeTable[], table: CatalogTable): Pending {
  return setInScope(pending, scope, keyOfTable(table), true);
}

/** Take a table out of scope. */
export function removeTable(pending: Pending, scope: ScopeTable[], row: ScopeTable): Pending {
  return setInScope(pending, scope, row, false);
}

function setInScope(pending: Pending, scope: ScopeTable[], key: RowKey, inScope: boolean): Pending {
  const next = new Map(pending);
  const row = scopeRow(scope, key);
  const already = row?.is_active ?? false;
  const id = rowKey(key);
  if (already === inScope) {
    next.delete(id); // no change from what is saved, so no record (this also undoes an earlier click)
  } else {
    const { tenant_code, system_code, connection_code, object_schema, object_name } = key;
    next.set(id, {
      tenant_code, system_code, connection_code, object_schema, object_name,
      is_active: inScope,
      is_locked: row?.is_locked ?? false, // keep a row's lock as it is; a new row starts unlocked
    });
  }
  return next;
}

/** Forget one pending change. */
export function undo(pending: Pending, id: string): Pending {
  const next = new Map(pending);
  next.delete(id);
  return next;
}

/** Is this table in scope once the pending changes are applied? */
export function inScopeAfter(pending: Pending, scope: ScopeTable[], key: RowKey): boolean {
  const change = pending.get(rowKey(key));
  return change ? change.is_active : (scopeRow(scope, key)?.is_active ?? false);
}
