// The changes waiting to become a draft. "Make draft" saves them as a draft change set; nothing in the project
// changes until a person reviews the draft and presses Apply.

import { useState } from "react";
import { undo } from "./scopeChanges";
import type { Pending } from "./scopeChanges";

type Props = { pending: Pending; onChange: (pending: Pending) => void; onMakeDraft: (title: string) => void };

export function Changes({ pending, onChange, onMakeDraft }: Props) {
  const [title, setTitle] = useState("Scope change");
  if (pending.size === 0) return null;
  return (
    <section className="panel changes">
      <h2>Changes not saved yet ({pending.size})</h2>
      <ul>
        {[...pending.entries()].map(([id, r]) => (
          <li key={id}>
            <span className={r.is_active ? "plus" : "minus"}>{r.is_active ? "Add" : "Take out"}</span>{" "}
            {r.object_schema}.{r.object_name} <span className="muted">({r.system_code})</span>{" "}
            <button onClick={() => onChange(undo(pending, id))}>Undo</button>
          </li>
        ))}
      </ul>
      <label>
        Title <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>{" "}
      <button className="primary" onClick={() => onMakeDraft(title)}>
        Make draft
      </button>
    </section>
  );
}
