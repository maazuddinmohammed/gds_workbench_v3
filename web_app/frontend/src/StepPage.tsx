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

function RelationshipsView({ ctx, picks, setPicks, version }: ViewProps) {
  const scope = useRecords(ctx, "project_input_scope", version);
  const links = useRecords(ctx, "analysis_result", version);
  const from = (l: Row) => `${l.from_object_schema}.${l.from_object_name}`;
  const rows = scope
    .filter((s) => s.is_active)
    .map((s) => ({ ...s, links: links.filter((l) => l.is_active && from(l) === tableKey(s)).length }));
  return (
    <div className="columns">
      <section className="card">
        <h3>Tables: pick some, or Run for all</h3>
        <Records rows={rows} rowKey={tableKey} selected={picks} onSelect={setPicks} columns={["object_name", "links"]}
          labels={{ object_name: "Table", links: "Links from it" }} />
      </section>
      <section className="card">
        <h3>Links</h3>
        <Records
          rows={links.map((l) => ({ ...l, from: `${l.from_object_name}.${l.from_attribute_name}`, to: `${l.to_object_name}.${l.to_attribute_name}` }))}
          rowKey={(l) => `${l.from}>${l.to}`}
          columns={["from", "to", "relationship_kind", "inferred_cardinality", "validation_result"]}
          labels={{ relationship_kind: "Kind", inferred_cardinality: "Cardinality", validation_result: "Validation" }}
          empty="No links yet."
        />
      </section>
    </div>
  );
}

function SubjectAreasView({ ctx, detail, version }: ViewProps) {
  const areas = useRecords(ctx, "subject_area", version);
  const tables = useRecords(ctx, "subject_area_table", version);
  const scope = useRecords(ctx, "project_input_scope", version);
  if (detail) {
    return (
      <section className="card">
        <h2><a href="#/step/subject-areas">Subject areas</a> / {detail}</h2>
        <p>{areas.find((a) => a.subject_area_name === detail)?.subject_area_definition as string}</p>
        <Records rows={tables.filter((t) => t.subject_area_name === detail)} rowKey={tableKey} columns={["object_name", "object_schema"]}
          labels={{ object_name: "Table", object_schema: "Schema" }} />
      </section>
    );
  }
  const used = new Set(tables.filter((t) => t.is_active).map(tableKey));
  const unassigned = scope.filter((s) => s.is_active && !used.has(tableKey(s)));
  return (
    <section className="card">
      <Records
        rows={areas.map((a) => ({ ...a, tables: tables.filter((t) => t.is_active && t.subject_area_name === a.subject_area_name).length }))}
        rowKey={(a) => String(a.subject_area_name)}
        onOpen={(a) => ctx.go(`#/step/subject-areas/${a.subject_area_name}`)}
        columns={["subject_area_name", "subject_area_definition", "tables"]}
        labels={{ subject_area_name: "Area", subject_area_definition: "Definition", tables: "Tables" }}
        empty="No subject areas yet."
      />
      {unassigned.length > 0 && <p className="warning">In no area ({unassigned.length}): {unassigned.map((s) => s.object_name).join(", ")}</p>}
    </section>
  );
}

function modelView(m: "operational" | "dimensional", page: string) {
  return function ModelView({ ctx, detail, picks, setPicks, version }: ViewProps) {
    const areas = useRecords(ctx, "subject_area", version);
    const entities = useRecords(ctx, `${m}_entity`, version);
    const attributes = useRecords(ctx, `${m}_attribute`, version);
    const sources = useRecords(ctx, `${m}_attribute_source`, version);
    const links = useRecords(ctx, `${m}_link`, version);
    const entitySources = useRecords(ctx, `${m}_entity_source`, version);
    const key = (r: Row) => `${r[`${m}_entity_schema_name`]}.${r[`${m}_entity_name`]}`;
    const picked = [...picks][0] ?? "";
    if (detail) {
      const entity = entities.find((e) => key(e) === detail);
      const attrKey = (r: Row) => `${key(r)}.${r[`${m}_attribute_name`]}`;
      const rows = attributes
        .filter((a) => key(a) === detail)
        .map((a) => ({
          ...a,
          sources: sources.filter((s) => attrKey(s) === attrKey(a) && s.is_active)
            .map((s) => `${m === "operational" ? `${s.object_name}.${s.attribute_name}` : `${s.operational_entity_name}.${s.operational_attribute_name}`}${s[`${m}_attribute_source_note`] ? ` (${s[`${m}_attribute_source_note`]})` : ""}`).join("; "),
          link: links.filter((l) => attrKey(l) === attrKey(a) && l.is_active).map((l) => l[`parent_${m}_entity_name`]).join(""),
        }));
      return (
        <section className="card">
          <h2><a href={`#/step/${page}`}>{STEPS[page].title}</a> / {detail}</h2>
          <p>{entity?.[`${m}_entity_definition`] as string}</p>
          <p className="muted">{entity?.[`${m}_entity_grain`] as string} · {String(entity?.[m === "operational" ? "operational_entity_type_code" : "dimensional_entity_type"] ?? "")}{entity?.is_merged ? " · merged" : ""}</p>
          <p className="muted">Sources: {entitySources.filter((s) => key(s) === detail && s.is_active).map((s) => m === "operational" ? `${s.object_schema}.${s.object_name}` : `${s.operational_entity_name}`).join(", ")}</p>
          <Records rows={rows} rowKey={(r) => String(r[`${m}_attribute_name`])}
            columns={[`${m}_attribute_name`, `${m}_attribute_data_type`, "is_surrogate_key", "is_natural_key", "is_nullable", "link", "sources", `${m}_attribute_definition`]}
            labels={{ [`${m}_attribute_name`]: "Attribute", [`${m}_attribute_data_type`]: "Type", is_surrogate_key: "Surrogate", is_natural_key: "Natural key", is_nullable: "Nullable", link: "Links to", sources: "From", [`${m}_attribute_definition`]: "Definition" }} />
        </section>
      );
    }
    return (
      <>
        <section className="card">
          <label>
            Subject area for the Run{" "}
            <select value={picked} onChange={(e) => setPicks(new Set(e.target.value ? [e.target.value] : []))}>
              <option value="">Pick an area</option>
              {areas.filter((a) => a.is_active).map((a) => (
                <option key={String(a.subject_area_name)}>{String(a.subject_area_name)}</option>
              ))}
            </select>
          </label>
        </section>
        <section className="card">
          <Records
            rows={entities.map((e) => ({ ...e, attributes: attributes.filter((a) => key(a) === key(e) && a.is_active).length }))}
            rowKey={key}
            onOpen={(e) => ctx.go(`#/step/${page}/${key(e)}`)}
            columns={[`${m}_entity_name`, `${m}_entity_schema_name`, m === "operational" ? "operational_entity_type_code" : "dimensional_entity_type", `${m}_entity_definition`, "attributes"]}
            labels={{ [`${m}_entity_name`]: "Entity", [`${m}_entity_schema_name`]: "Schema", operational_entity_type_code: "Type", dimensional_entity_type: "Type", [`${m}_entity_definition`]: "Definition", attributes: "Attributes" }}
            empty="No entities yet."
          />
        </section>
      </>
    );
  };
}

const areaRequest = (picks: Set<string>) => ({ subject_area_name: [...picks][0] });
const areaPicked = (picks: Set<string>) => (picks.size ? `area ${[...picks][0]}` : "no area yet");
const areaReady = (picks: Set<string>) => (picks.size ? null : "Pick a subject area first.");

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
  relationships: {
    title: "Relationships",
    about: "The AI finds the links between scope tables, table by table: which column points at which key. It needs columns marked as keys by column enrichment.",
    actions: [{ workflow: "analysis", label: "Run relationships" }],
    request: tablesRequest,
    picked: tablesPicked,
    View: RelationshipsView,
  },
  "subject-areas": {
    title: "Subject Areas",
    about: "The AI groups the scope tables into business areas. Each area then gets its own Silver and Gold Run.",
    actions: [{ workflow: "subject_area", label: "Run subject areas" }],
    request: () => ({}),
    picked: () => "the whole scope",
    View: SubjectAreasView,
  },
  silver: {
    title: "Silver Model",
    about: "The AI builds the operational model for one subject area, working with tools: entities, attributes, where each comes from, and links. Apply one area before running the next.",
    actions: [{ workflow: "operational", label: "Run Silver model" }],
    request: areaRequest,
    picked: areaPicked,
    ready: areaReady,
    View: modelView("operational", "silver"),
  },
  gold: {
    title: "Gold Model",
    about: "The AI builds facts and dimensions for one subject area from its Silver entities, working with tools.",
    actions: [{ workflow: "dimensional", label: "Run Gold model" }],
    request: areaRequest,
    picked: areaPicked,
    ready: areaReady,
    View: modelView("dimensional", "gold"),
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
