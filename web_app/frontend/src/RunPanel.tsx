// Pressing Run on a step, and following its log until it ends (design/overview/run.md). The AI settings start from
// the project's defaults; the person may change the model, the effort and add instructions for this Run only.

import { useEffect, useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";
import type { Model, Run } from "./api";

type Props = {
  ctx: Ctx;
  actions: { workflow: string; label: string }[];
  request: Record<string, unknown>;
  picked: string; // what the Run is for, in words, such as "3 tables" or "every table"
  ready?: string | null; // why Run cannot be pressed yet, if so
  noAI?: boolean; // profiling has no model, effort or instructions
  onEnded: () => void;
};

export function RunPanel({ ctx, actions, request, picked, ready, noAI, onEnded }: Props) {
  const [models, setModels] = useState<Model[]>([]);
  const [modelId, setModelId] = useState<number | "">("");
  const [effort, setEffort] = useState("");
  const [extra, setExtra] = useState("");
  const [runId, setRunId] = useState<number | null>(null);

  useEffect(() => {
    api<Model[]>("GET", "/api/models").then(setModels).catch(ctx.showError);
  }, []);

  function start(workflow: string) {
    api<{ run_id: number }>("POST", `/api/projects/${ctx.projectId}/runs`, {
      project_workflow: workflow,
      request,
      agent_model_id: modelId || null,
      reasoning_effort_code: effort || null,
      extra_instructions: extra || null,
    })
      .then((r) => setRunId(r.run_id))
      .catch(ctx.showError);
  }

  const model = models.find((m) => m.agent_model_id === modelId);
  return (
    <section className="card run-panel">
      <div className="run-row">
        <span className="muted">For {picked}</span>
        {!noAI && (<>
        <select value={modelId} onChange={(e) => setModelId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">Project's model</option>
          {models.map((m) => (
            <option key={m.agent_model_id} value={m.agent_model_id}>
              {m.agent_model_display_name}
            </option>
          ))}
        </select>
        <select value={effort} onChange={(e) => setEffort(e.target.value)}>
          <option value="">Project's effort</option>
          {(model?.reasoning_effort_codes ?? ["low", "medium", "high"]).map((code) => (
            <option key={code}>{code}</option>
          ))}
        </select>
        <input className="grow" placeholder="Extra instructions for this Run (optional)" value={extra} onChange={(e) => setExtra(e.target.value)} />
        </>)}
        {ctx.canChange &&
          actions.map((a) => (
            <button key={a.workflow} className="primary" disabled={!!ready} title={ready ?? ""} onClick={() => start(a.workflow)}>
              {a.label}
            </button>
          ))}
      </div>
      {ready && <div className="muted">{ready}</div>}
      {runId !== null && <RunLog ctx={ctx} runId={runId} onEnded={onEnded} />}
    </section>
  );
}

export function RunLog({ ctx, runId, onEnded }: { ctx: Ctx; runId: number; onEnded?: () => void }) {
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => {
    let stop = false;
    const read = () =>
      api<Run>("GET", `/api/runs/${runId}`)
        .then((r) => {
          if (stop) return;
          setRun(r);
          if (r.run_status === "running") setTimeout(read, 2000);
          else onEnded?.();
        })
        .catch(ctx.showError);
    read();
    return () => {
      stop = true;
    };
  }, [runId]);
  if (!run) return null;
  return (
    <div className="run-log">
      <div>
        <strong>Run {run.run_id}</strong> · {run.project_workflow} · <span className={`status ${run.run_status}`}>{run.run_status}</span>
        {run.usage.cost_usd !== null && <span className="muted"> · {run.usage.calls} AI calls, ${Number(run.usage.cost_usd).toFixed(3)}</span>}
        {run.project_change_set_id && (
          <>
            {" "}
            · <a href={`#/change-set/${run.project_change_set_id}`}>Review draft {run.project_change_set_id}</a>
            <span className="muted"> ({run.project_change_set_status})</span>
          </>
        )}
      </div>
      {run.failure_message && <div className="problem">{run.failure_message}</div>}
      <ol>
        {run.events.map((e, i) => (
          <li key={i} className={e.run_event_status === "failed" ? "problem" : ""}>
            <span className="muted">{e.run_event_stage}</span> {e.run_event_message ?? e.run_event_status}
          </li>
        ))}
      </ol>
    </div>
  );
}
