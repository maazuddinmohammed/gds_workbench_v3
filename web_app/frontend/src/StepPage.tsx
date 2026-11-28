// One page per workflow step, from one frame: what the step is, Run for what you picked, the step's latest Runs with
// their drafts, and what is saved now. Each step adds only its own view (what you pick and what is listed).

import { useEffect, useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";
import type { RunSummary } from "./api";
import { Records } from "./Records";
import type { Row } from "./Records";
import { RunPanel } from "./RunPanel";

type ViewProps = { ctx: Ctx; detail?: string; picks: Set<string>; setPicks: (p: Set<string>) => void; version: number };

type StepDef = {
  title: string;
  about: string;
  actions: { workflow: string; label: string }[];
  request: (picks: Set<string>) => Record<string, unknown>;
  picked: (picks: Set<string>) => string;
  ready?: (picks: Set<string>) => string | null;
  View: (props: ViewProps) => React.ReactNode;
};

export function useRecords(ctx: Ctx, part: string, version: number) {
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => {
    api<Row[]>("GET", `/api/projects/${ctx.projectId}/records/${part}`).then(setRows).catch(ctx.showError);
  }, [ctx.projectId, part, version, ctx.project?.project_version]);
  return rows;
}

const tableKey = (r: Row) => `${r.object_schema}.${r.object_name}`;
const tablesRequest = (picks: Set<string>) =>
  picks.size === 0
    ? {}
    : { tables: [...picks].map((k) => ({ object_schema: k.split(".")[0], object_name: k.split(".").slice(1).join(".") })) };
const tablesPicked = (picks: Set<string>) => (picks.size === 0 ? "every table in scope" : `${picks.size} picked tables`);

function EnrichmentView({ ctx, detail, picks, setPicks, version }: ViewProps) {
  const scope = useRecords(ctx, "project_input_scope", version);
  const enriched = useRecords(ctx, "object_enrichment", version);
  const columns = useRecords(ctx, "attribute_enrichment", version);
  const profiles = useRecords(ctx, "attribute_profile", version);
  const byTable = new Map(enriched.map((e) => [tableKey(e), e]));
  if (detail) {
    const table = byTable.get(detail);
    const profile = new Map(profiles.filter((p) => tableKey(p) === detail).map((p) => [p.attribute_name, p]));
    const rows = columns
      .filter((c) => tableKey(c) === detail)
      .map((c) => ({ ...profile.get(c.attribute_name), ...c }));
    return (
      <section className="card">
        <h2>
          <a href="#/step/enrichment">Enrichment</a> / {detail}
        </h2>
        <p>{(table?.object_definition as string) ?? <span className="muted">No definition yet.</span>}</p>
        <p className="muted">{table?.object_grain as string}</p>
        <Records
          rows={rows.length ? rows : profiles.filter((p) => tableKey(p) === detail)}
          rowKey={(r) => String(r.attribute_name)}
          columns={["attribute_name", "attribute_definition", "attribute_inferred_data_type", "is_natural_key", "is_surrogate_key",
            "is_foreign_key_candidate", "is_nullable", "is_pii", "distinct_count", "null_count", "sample_values"]}
          labels={{ attribute_name: "Column", attribute_definition: "Definition", attribute_inferred_data_type: "Type", is_natural_key: "Natural key",
            is_surrogate_key: "Surrogate", is_foreign_key_candidate: "Points elsewhere", is_nullable: "Nullable", is_pii: "Personal",
            distinct_count: "Distinct", null_count: "Nulls", sample_values: "Samples" }}
          empty="No columns enriched yet: run column enrichment for this table."
        />
      </section>
    );
  }
  const rows = scope
    .filter((s) => s.is_active)
    .map((s) => ({ ...s, ...byTable.get(tableKey(s)), columns: columns.filter((c) => tableKey(c) === tableKey(s)).length }));
  return (
    <section className="card">
      <Records
        rows={rows}
        rowKey={tableKey}
        selected={picks}
        onSelect={setPicks}
        onOpen={(r) => ctx.go(`#/step/enrichment/${tableKey(r)}`)}
        columns={["object_name", "system_code", "object_definition", "object_grain", "columns"]}
        labels={{ object_name: "Table", system_code: "Connection system", object_definition: "Definition", object_grain: "Grain", columns: "Columns enriched" }}
        empty="Nothing in scope yet."
      />
    </section>
  );
}

export const STEPS: Record<string, StepDef> = {
  enrichment: {
    title: "Enrichment",
    about: "The AI defines each table (definition and Grain), then its columns: definition, real type, keys, nullability and personal data. Run tables first, review and apply, then columns.",
    actions: [
      { workflow: "object_enrichment", label: "Run table enrichment" },
      { workflow: "attribute_enrichment", label: "Run column enrichment" },
    ],
    request: tablesRequest,
    picked: tablesPicked,
    View: EnrichmentView,
  },
};

export function StepPage({ ctx, stepKey, detail }: { ctx: Ctx; stepKey: string; detail?: string }) {
  const step = STEPS[stepKey];
  const [picks, setPicks] = useState<Set<string>>(new Set());
  const [version, setVersion] = useState(0);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const workflows = step.actions.map((a) => a.workflow);

  useEffect(() => {
    api<RunSummary[]>("GET", `/api/projects/${ctx.projectId}/runs`)
      .then((all) => setRuns(all.filter((r) => workflows.includes(r.project_workflow)).slice(0, 5)))
      .catch(ctx.showError);
  }, [ctx.projectId, version, ctx.project?.project_version]);

  const waiting = runs.filter((r) => r.project_change_set_status === "draft");
  return (
    <>
      <p className="about">{step.about}</p>
      {waiting.map((r) => (
        <div key={r.run_id} className="banner">
          Draft {r.project_change_set_id} from Run {r.run_id} ({r.project_workflow}) is waiting for review.{" "}
          <a href={`#/change-set/${r.project_change_set_id}`}>Review draft</a>
        </div>
      ))}
      <RunPanel
        ctx={ctx}
        actions={step.actions}
        request={step.request(picks)}
        picked={step.picked(picks)}
        ready={step.ready?.(picks)}
        onEnded={() => setVersion((v) => v + 1)}
      />
      {runs.length > 0 && (
        <section className="card">
          <h3>Latest Runs</h3>
          <table>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td>
                    <a href={`#/run/${r.run_id}`}>Run {r.run_id}</a>
                  </td>
                  <td>{r.project_workflow}</td>
                  <td className={`status ${r.run_status}`}>{r.run_status}</td>
                  <td className="muted">{r.agent_model_display_name}</td>
                  <td className="muted">{r.cost_usd !== null ? `$${Number(r.cost_usd).toFixed(3)}` : ""}</td>
                  <td>
                    {r.project_change_set_id && (
                      <a href={`#/change-set/${r.project_change_set_id}`}>
                        Draft {r.project_change_set_id} ({r.project_change_set_status})
                      </a>
                    )}
                  </td>
                  <td className="muted">{r.failure_message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <step.View ctx={ctx} detail={detail} picks={picks} setPicks={setPicks} version={version} />
    </>
  );
}
