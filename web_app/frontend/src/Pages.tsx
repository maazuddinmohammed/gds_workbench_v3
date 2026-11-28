// The smaller pages: the project's overview, the tenant's projects and change sets, one change set's review, one Run.

import { useEffect, useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";
import type { ChangeSetRow, Project, RunSummary } from "./api";
import { Review } from "./Review";
import { RunLog } from "./RunPanel";

export function OverviewPage({ ctx }: { ctx: Ctx }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  useEffect(() => {
    api<RunSummary[]>("GET", `/api/projects/${ctx.projectId}/runs`).then(setRuns).catch(ctx.showError);
  }, [ctx.projectId, ctx.project?.project_version]);
  const p = ctx.project;
  if (!p) return null;
  const cfg = p.project_config ?? {};
  const spent = runs.reduce((sum, r) => sum + Number(r.cost_usd ?? 0), 0);
  return (
    <div className="columns">
      <section className="card">
        <h3>How far the project is</h3>
        <table>
          <tbody>
            {Object.entries(p.row_counts).map(([part, n]) => (
              <tr key={part}>
                <td>{part.replaceAll("_", " ")}</td>
                <td>{n}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3>Settings</h3>
        <table>
          <tbody>
            <tr><td>Silver schemas</td><td>{(cfg.operational_schemas ?? []).map((s: { schema_name: string }) => s.schema_name).join(", ")}</td></tr>
            <tr><td>Gold schemas</td><td>{(cfg.dimensional_schemas ?? []).map((s: { schema_name: string }) => s.schema_name).join(", ")}</td></tr>
            <tr><td>SCD type Silver / Gold</td><td>{cfg.operational_entity_scd_type} / {cfg.dimensional_entity_scd_type}</td></tr>
            <tr><td>Samples stored</td><td>{cfg.is_sample_storage_allowed ? `yes, ${cfg.sample_size} per column` : "no"}</td></tr>
          </tbody>
        </table>
      </section>
      <section className="card">
        <h3>Latest Runs <span className="muted">(${spent.toFixed(2)} in the last {runs.length})</span></h3>
        <table>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td><a href={`#/run/${r.run_id}`}>Run {r.run_id}</a></td>
                <td>{r.project_workflow}</td>
                <td className={`status ${r.run_status}`}>{r.run_status}</td>
                <td>{r.project_change_set_id && <a href={`#/change-set/${r.project_change_set_id}`}>Draft {r.project_change_set_id} ({r.project_change_set_status})</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export function ProjectsPage({ ctx, projects, onOpen }: { ctx: Ctx; projects: Project[]; onOpen: (id: number) => void }) {
  return (
    <section className="card">
      <h2>Projects in {ctx.tenant.tenant_name}</h2>
      <table>
        <tbody>
          {projects.map((p) => (
            <tr key={p.project_id}>
              <td>
                <a onClick={() => { onOpen(p.project_id); ctx.go("#/overview"); }}>{p.project_name}</a>
              </td>
              <td className="muted">{p.project_description}</td>
              <td>Version {p.project_version}{p.is_locked ? " · locked" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function ChangeSetsPage({ ctx }: { ctx: Ctx }) {
  const [rows, setRows] = useState<ChangeSetRow[]>([]);
  useEffect(() => {
    api<ChangeSetRow[]>("GET", `/api/tenants/${ctx.tenant.tenant_id}/change-sets`).then(setRows).catch(ctx.showError);
  }, [ctx.tenant.tenant_id]);
  return (
    <section className="card">
      <h2>Change sets in {ctx.tenant.tenant_name}</h2>
      <table>
        <thead>
          <tr><th>#</th><th>Title</th><th>Project</th><th>Status</th><th>Source</th><th>Made by</th><th>Version</th></tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.project_change_set_id}>
              <td><a href={`#/change-set/${c.project_change_set_id}`}>{c.project_change_set_id}</a></td>
              <td>{c.project_change_set_title}</td>
              <td>{c.project_name}</td>
              <td className={`status ${c.project_change_set_status}`}>{c.project_change_set_status}</td>
              <td>{c.project_change_set_source}</td>
              <td>{c.created_by_display_name}</td>
              <td>{c.base_project_version}{c.base_project_version !== c.project_version && c.project_change_set_status === "draft" ? ` (now ${c.project_version})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function ReviewPage({ ctx, changeSetId }: { ctx: Ctx; changeSetId: number }) {
  const [done, setDone] = useState<string | null>(null);
  if (done) return <p className="message">{done} <a onClick={() => history.back()}>Back</a></p>;
  return (
    <Review
      key={changeSetId}
      changeSetId={changeSetId}
      canChange={ctx.canChange}
      onDone={(applied) => {
        setDone(applied ? "Applied. The project moved to its next version." : "Rejected. Nothing in the project changed.");
        ctx.refresh();
      }}
      onClose={() => history.back()}
      onError={ctx.showError}
    />
  );
}

export function RunPage({ ctx, runId }: { ctx: Ctx; runId: number }) {
  return (
    <section className="card">
      <RunLog ctx={ctx} runId={runId} />
    </section>
  );
}
