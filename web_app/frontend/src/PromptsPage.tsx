// The prompts a tenant's Runs use, and the text of each version (read only for now: who may save a version, and
// whether a tenant may change a global prompt, wait for Maaz's decision).

import { useEffect, useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";

type PromptRow = { prompt_id: number; prompt_name: string; project_workflow: string; workflow_execution_mode: string;
  is_default: boolean; is_global: boolean; latest_version: number };
type Version = { prompt_version_number: number; system_prompt: string; instruction_prompt: string; created_time: string };

export function PromptsPage({ ctx }: { ctx: Ctx }) {
  const [rows, setRows] = useState<PromptRow[]>([]);
  const [open, setOpen] = useState<{ prompt_name: string; versions: Version[] } | null>(null);
  const base = `/api/tenants/${ctx.tenant.tenant_id}/prompts`;
  useEffect(() => {
    api<PromptRow[]>("GET", base).then(setRows).catch(ctx.showError);
  }, [base]);
  return (
    <div className="columns">
      <section className="card">
        <h2>Prompts</h2>
        <table>
          <tbody>
            {rows.map((p) => (
              <tr key={p.prompt_id}>
                <td><a onClick={() => api<{ prompt_name: string; versions: Version[] }>("GET", `${base}/${p.prompt_id}`).then(setOpen).catch(ctx.showError)}>{p.prompt_name}</a></td>
                <td className="muted">{p.project_workflow}</td>
                <td className="muted">{p.is_global ? "global" : "this tenant"}{p.is_default ? ", default" : ""}</td>
                <td>v{p.latest_version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {open && (
        <section className="card">
          <h2>{open.prompt_name}</h2>
          {open.versions.map((v) => (
            <details key={v.prompt_version_number} open={v === open.versions[0]}>
              <summary>Version {v.prompt_version_number}</summary>
              <h3>System</h3>
              <pre>{v.system_prompt}</pre>
              <h3>Instruction</h3>
              <pre>{v.instruction_prompt}</pre>
            </details>
          ))}
        </section>
      )}
    </div>
  );
}
