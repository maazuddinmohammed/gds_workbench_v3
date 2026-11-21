// The tables in the project's scope now (core.projects.current_scope), with Remove for those who may change it.
// A table marked for removal stays listed, struck through, until the draft is applied.

import type { ScopeTable } from "./api";
import { inScopeAfter } from "./scopeChanges";
import type { Pending } from "./scopeChanges";

type Props = { scope: ScopeTable[]; pending: Pending; canChange: boolean; onRemove: (row: ScopeTable) => void };

export function ScopeList({ scope, pending, canChange, onRemove }: Props) {
  const active = scope.filter((t) => t.is_active);
  return (
    <section className="panel">
      <h2>In scope</h2>
      {active.length === 0 && <p className="muted">Nothing in scope yet.</p>}
      {active.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th>Zone</th>
              <th>System</th>
              {canChange && <th />}
            </tr>
          </thead>
          <tbody>
            {active.map((t) => {
              const leaving = !inScopeAfter(pending, scope, t);
              return (
                <tr key={`${t.connection_code}.${t.object_schema}.${t.object_name}`} className={leaving ? "leaving" : ""}>
                  <td>
                    {t.object_schema}.{t.object_name}
                    {t.is_locked && <span className="tag">locked</span>}
                    {!t.table_is_active && <span className="tag">switched off in the catalog</span>}
                  </td>
                  <td>{t.zone_code}</td>
                  <td>{t.system_code}</td>
                  {canChange && (
                    <td>{!leaving && <button onClick={() => onRemove(t)}>Remove</button>}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
