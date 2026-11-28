// Reviewing a draft change set of any kind of record: how many records add, change or switch off a row in each part,
// each change next to what is saved now, and every problem with its rule ID. Then Apply or Reject.
// The backend works everything out again on Apply and saves all of it or nothing.

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Change, ChangeSet, Problem } from "./api";

type Props = {
  changeSetId: number;
  canChange: boolean;
  onDone: (applied: boolean) => void;
  onClose: () => void;
  onError: (e: unknown) => void;
};

export function Review({ changeSetId, canChange, onDone, onClose, onError }: Props) {
  const [changeSet, setChangeSet] = useState<ChangeSet | null>(null);
  const [changes, setChanges] = useState<Record<string, Change[]>>({});
  const [problems, setProblems] = useState<Problem[]>([]);
  const path = `/api/change-sets/project/${changeSetId}`;
  const [loaded, setLoaded] = useState(0);

  function takeOut(part: string, record: number) {
    api("POST", `${path}/take-out`, { part, record }).then(() => setLoaded((n) => n + 1)).catch(onError);
  }

  useEffect(() => {
    api<ChangeSet>("GET", path)
      .then(async (cs) => {
        setChangeSet(cs);
        const lists: Record<string, Change[]> = {};
        for (const part of Object.keys(cs.counts)) {
          lists[part] = (await api<{ changes: Change[] }>("GET", `${path}/changes?part=${part}`)).changes;
        }
        setChanges(lists);
        setProblems((await api<{ problems: Problem[] }>("GET", `${path}/problems`)).problems);
      })
      .catch(onError);
  }, [path, loaded]);

  function decide(action: "apply" | "reject") {
    api<{ problems: Problem[] }>("POST", `${path}/${action}`)
      .then((answer) => {
        if (answer.problems.length > 0) setProblems(answer.problems);
        else onDone(action === "apply");
      })
      .catch(onError);
  }

  if (!changeSet) return null;
  const blocking = problems.some((p) => p.level === "blocks_apply");
  const loose = problems.filter((p) => p.record === null);
  return (
    <section className="panel review">
      <h2>
        Review: {changeSet.project_change_set_title}{" "}
        <span className="muted">
          by {changeSet.created_by_display_name}, on version {changeSet.base_project_version}
        </span>
      </h2>
      {loose.map((p, i) => (
        <p key={i} className={p.level === "warning" ? "warning" : "problem"}>
          <strong>{p.rule_id}</strong> {p.message}
        </p>
      ))}
      {Object.entries(changes).map(([part, list]) => (
        <div key={part}>
          <h3>
            {part}{" "}
            <span className="muted">
              {Object.entries(changeSet.counts[part])
                .filter(([, n]) => n > 0)
                .map(([kind, n]) => `${n} ${kind.replace("_", " ")}`)
                .join(", ")}
            </span>
          </h3>
          <table>
            <tbody>
              {list.map((c, i) => (
                <tr key={i}>
                  <td className={c.change === "switched_off" ? "minus" : "plus"}>{c.change.replace("_", " ")}</td>
                  <td>
                    {Object.entries(c.record).map(([field, value]) => (
                      <div key={field}>
                        <span className="muted">{field}</span> {JSON.stringify(value)}
                        {c.current && field in c.current && (
                          <span className="muted"> (now {JSON.stringify(c.current[field])})</span>
                        )}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {problems
        .filter((p) => p.record !== null)
        .map((p, i) => (
          <div key={i} className={p.level === "warning" ? "warning" : "problem"}>
            <strong>{p.rule_id}</strong> {p.part} record {p.record}: {p.message}{" "}
            {canChange && changeSet.project_change_set_status === "draft" && p.part && p.record !== null && (
              <button onClick={() => takeOut(p.part as string, p.record as number)}>Take this record out</button>
            )}
          </div>
        ))}
      <div className="actions">
        {canChange && (
          <>
            <button className="primary" disabled={blocking} onClick={() => decide("apply")}>
              Apply
            </button>
            <button onClick={() => decide("reject")}>Reject</button>
          </>
        )}
        <button onClick={onClose}>Close</button>
        {blocking && <span className="muted">Fix the problems before Apply: reject this draft and make a new one.</span>}
      </div>
    </section>
  );
}
