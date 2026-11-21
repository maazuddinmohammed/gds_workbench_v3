// Reviewing a scope draft: every record with its problems (each naming its rule ID), then Apply or Reject.
// The backend checks everything again on Apply and saves all of it or nothing.

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Problem, ScopeDraft } from "./api";

type Props = {
  changeSetId: number;
  canChange: boolean;
  onDone: (applied: boolean) => void;
  onClose: () => void;
  onError: (e: unknown) => void;
};

export function Review({ changeSetId, canChange, onDone, onClose, onError }: Props) {
  const [draft, setDraft] = useState<ScopeDraft | null>(null);
  const [problems, setProblems] = useState<Problem[]>([]);
  const path = `/api/scope-drafts/${changeSetId}`;

  useEffect(() => {
    api<ScopeDraft>("GET", path)
      .then((d) => {
        setDraft(d);
        setProblems(d.problems);
      })
      .catch(onError);
  }, [path]);

  function decide(action: "apply" | "reject") {
    api<{ applied?: boolean; rejected?: boolean; problems: Problem[] }>("POST", `${path}/${action}`)
      .then((answer) => {
        if (answer.problems.length > 0) setProblems(answer.problems);
        else onDone(action === "apply");
      })
      .catch(onError);
  }

  if (!draft) return null;
  const whole = problems.filter((p) => p.record === null);
  return (
    <section className="panel review">
      <h2>
        Review: {draft.title} <span className="muted">by {draft.created_by_display_name}, on version {draft.base_project_version}</span>
      </h2>
      {whole.map((p) => (
        <p key={p.rule_id} className="problem">
          <strong>{p.rule_id}</strong> {p.message}
        </p>
      ))}
      <table>
        <thead>
          <tr>
            <th>Change</th>
            <th>Table</th>
            <th>System</th>
            <th>Problems</th>
          </tr>
        </thead>
        <tbody>
          {draft.records.map((r, index) => (
            <tr key={index}>
              <td className={r.is_active ? "plus" : "minus"}>{r.is_active ? "Add" : "Take out"}</td>
              <td>
                {r.object_schema}.{r.object_name}
              </td>
              <td>{r.system_code}</td>
              <td>
                {problems
                  .filter((p) => p.record === index)
                  .map((p) => (
                    <div key={p.rule_id} className="problem">
                      <strong>{p.rule_id}</strong> {p.message}
                    </div>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="actions">
        {canChange && (
          <>
            <button className="primary" disabled={problems.length > 0} onClick={() => decide("apply")}>
              Apply
            </button>
            <button onClick={() => decide("reject")}>Reject</button>
          </>
        )}
        <button onClick={onClose}>Close</button>
        {problems.length > 0 && <span className="muted">Fix the problems before Apply: reject this draft and make a new one.</span>}
      </div>
    </section>
  );
}
