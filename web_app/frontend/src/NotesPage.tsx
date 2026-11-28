// Notes: what the tenant knows and wants, which each step reads by type (design/shared/notes-and-prompt-builder.md).
// Adding or changing a Note makes a draft, reviewed and applied like any change.

import { useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";
import { Records } from "./Records";
import type { Row } from "./Records";
import { useRecords } from "./StepPage";

const TYPES = ["source_information", "enrichment_requirement", "analysis_requirement", "subject_area_requirement",
  "operational_model_requirement", "dimensional_model_requirement", "kpi_requirement", "reporting_requirement",
  "mapping_requirement", "code_requirement", "validation_requirement", "agent"];

export function NotesPage({ ctx }: { ctx: Ctx }) {
  const groups = useRecords(ctx, "context_group", 0);
  const notes = useRecords(ctx, "context_record", 0);
  const [group, setGroup] = useState("");
  const [type, setType] = useState(TYPES[0]);
  const [system, setSystem] = useState("");
  const [text, setText] = useState("");

  function add() {
    const saved = groups.find((g) => String(g.context_group_name).toLowerCase() === group.trim().toLowerCase());
    const next = Math.max(0, ...notes.filter((n) => n.context_group_name === saved?.context_group_name).map((n) => Number(n.context_record_number))) + 1;
    const documents: Record<string, Row[]> = {
      context_record: [{ context_group_name: group.trim(), context_record_number: next, context_record_text: text.trim() }],
    };
    if (!saved) documents.context_group = [{ context_group_name: group.trim(), context_type_code: type, system_code: system.trim() || null }];
    api<{ change_set_id: number }>("POST", `/api/projects/${ctx.projectId}/change-sets`, { title: `Note in ${group.trim()}`, documents })
      .then((r) => ctx.go(`#/change-set/${r.change_set_id}`))
      .catch(ctx.showError);
  }

  return (
    <>
      <p className="about">Notes are facts and requirements the AI reads. Each step reads only its own types; a group for one system goes in only when a Run involves that system.</p>
      {ctx.canChange && (
        <section className="card run-row">
          <input placeholder="Group, such as KICS facts" value={group} onChange={(e) => setGroup(e.target.value)} />
          <select value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
          <input placeholder="System code (empty: whole project)" value={system} onChange={(e) => setSystem(e.target.value)} />
          <input className="grow" placeholder="The Note" value={text} onChange={(e) => setText(e.target.value)} />
          <button className="primary" disabled={!group.trim() || !text.trim()} onClick={add}>Add Note</button>
        </section>
      )}
      <section className="card">
        <Records
          rows={notes.map((n) => ({ ...n, ...groups.find((g) => g.context_group_name === n.context_group_name) }))}
          rowKey={(r) => `${r.context_group_name}#${r.context_record_number}`}
          columns={["context_group_name", "context_type_code", "system_code", "context_record_number", "context_record_text"]}
          labels={{ context_group_name: "Group", context_type_code: "Type", system_code: "System", context_record_number: "#", context_record_text: "Note" }}
          empty="No Notes yet."
        />
      </section>
    </>
  );
}
