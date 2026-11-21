// The tables you can see from the tenant: its own and every global tenant's (core.catalog.list_tables),
// 50 at a time. Filters for zones, scope-only and switched-off tables.

import { useEffect, useState } from "react";
import { api } from "./api";
import type { TablePage } from "./api";

const ZONES = ["source", "bronze", "silver", "gold"];

type Props = { tenantId: number; onError: (e: unknown) => void };

export function TableList({ tenantId, onError }: Props) {
  const [zones, setZones] = useState<string[]>([]);
  const [scopeOnly, setScopeOnly] = useState(false);
  const [switchedOff, setSwitchedOff] = useState(false);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<TablePage | null>(null);

  useEffect(() => setPage(1), [tenantId, zones, scopeOnly, switchedOff]);

  useEffect(() => {
    const query = new URLSearchParams({ page: String(page) });
    zones.forEach((z) => query.append("zones", z));
    if (scopeOnly) query.set("scope_only", "true");
    if (switchedOff) query.set("include_switched_off", "true");
    api<TablePage>("GET", `/api/tenants/${tenantId}/tables?${query}`).then(setResult).catch(onError);
  }, [tenantId, zones, scopeOnly, switchedOff, page]);

  function toggleZone(zone: string) {
    setZones((now) => (now.includes(zone) ? now.filter((z) => z !== zone) : [...now, zone]));
  }

  const first = result ? (result.page - 1) * result.page_size + 1 : 0;
  const last = result ? first + result.tables.length - 1 : 0;

  return (
    <section className="panel">
      <h2>Tables</h2>
      <div className="filters">
        {ZONES.map((zone) => (
          <label key={zone}>
            <input type="checkbox" checked={zones.includes(zone)} onChange={() => toggleZone(zone)} /> {zone}
          </label>
        ))}
        <label>
          <input type="checkbox" checked={scopeOnly} onChange={(e) => setScopeOnly(e.target.checked)} /> can be in
          scope
        </label>
        <label>
          <input type="checkbox" checked={switchedOff} onChange={(e) => setSwitchedOff(e.target.checked)} /> show
          switched off
        </label>
      </div>
      {result && (
        <>
          <table>
            <thead>
              <tr>
                <th>Table</th>
                <th>Zone</th>
                <th>System</th>
                <th>Owner</th>
              </tr>
            </thead>
            <tbody>
              {result.tables.map((t) => (
                <tr key={t.object_id} className={t.is_active ? "" : "off"}>
                  <td>
                    {t.object_schema}.{t.object_name}
                    {!t.is_active && <span className="tag">switched off</span>}
                  </td>
                  <td>{t.zone_code}</td>
                  <td>{t.system_code}</td>
                  <td>
                    {t.source_tenant_code}
                    {t.is_global && <span className="tag">global</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pager">
            <span className="muted">
              {result.total === 0 ? "No tables" : `${first}–${last} of ${result.total}`}
            </span>
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <button disabled={last >= result.total} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}
