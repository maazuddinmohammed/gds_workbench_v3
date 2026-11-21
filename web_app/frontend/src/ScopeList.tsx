// The tables in the project's scope now (core.projects.current_scope). Changing it comes in step 4a4c.

import { useEffect, useState } from "react";
import { api } from "./api";
import type { ScopeTable } from "./api";

type Props = { projectId: number; version: number; onError: (e: unknown) => void };

export function ScopeList({ projectId, version, onError }: Props) {
  const [scope, setScope] = useState<ScopeTable[] | null>(null);

  useEffect(() => {
    api<ScopeTable[]>("GET", `/api/projects/${projectId}/scope`).then(setScope).catch(onError);
  }, [projectId, version]);

  return (
    <section className="panel">
      <h2>In scope</h2>
      {scope?.length === 0 && <p className="muted">Nothing in scope yet.</p>}
      {scope && scope.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th>Zone</th>
              <th>System</th>
            </tr>
          </thead>
          <tbody>
            {scope.map((t) => (
              <tr key={`${t.connection_code}.${t.object_schema}.${t.object_name}`}>
                <td>
                  {t.object_schema}.{t.object_name}
                  {t.is_locked && <span className="tag">locked</span>}
                  {!t.table_is_active && <span className="tag">switched off in the catalog</span>}
                </td>
                <td>{t.zone_code}</td>
                <td>{t.system_code}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
