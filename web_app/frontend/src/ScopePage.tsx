// The scope page (step 4a4): add and take out tables, make a draft, review it and Apply.

import { useEffect, useState } from "react";
import type { Ctx } from "./App";
import { api } from "./api";
import type { ScopeTable } from "./api";
import { Changes } from "./Changes";
import { Review } from "./Review";
import { addTable, removeTable } from "./scopeChanges";
import type { Pending } from "./scopeChanges";
import { ScopeList } from "./ScopeList";
import { TableList } from "./TableList";

export function ScopePage({ ctx }: { ctx: Ctx }) {
  const [scope, setScope] = useState<ScopeTable[] | null>(null); // rows taken out included
  const [pending, setPending] = useState<Pending>(new Map());
  const [draftId, setDraftId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<ScopeTable[]>("GET", `/api/projects/${ctx.projectId}/scope?include_switched_off=true`)
      .then(setScope)
      .catch(ctx.showError);
  }, [ctx.projectId, ctx.project?.project_version]);

  function makeDraft(title: string) {
    api<{ change_set_id: number }>("POST", `/api/projects/${ctx.projectId}/change-sets`, {
      title,
      documents: { project_input_scope: [...pending.values()] },
    })
      .then((r) => setDraftId(r.change_set_id))
      .catch(ctx.showError);
  }

  function reviewed(applied: boolean) {
    setDraftId(null);
    if (applied) {
      setPending(new Map());
      setMessage("Applied. The scope is saved.");
      ctx.refresh();
    } else {
      setMessage("Draft rejected. Your changes are still listed, so you can fix them and make a new draft.");
    }
  }

  const canChange = ctx.canChange && draftId === null;
  return (
    <>
      {message && <p className="message">{message}</p>}
      {draftId !== null && (
        <Review changeSetId={draftId} canChange={ctx.canChange} onDone={reviewed} onClose={() => setDraftId(null)} onError={ctx.showError} />
      )}
      <div className="columns">
        <TableList
          tenantId={ctx.tenant.tenant_id}
          scope={scope}
          pending={pending}
          canChange={canChange}
          onAdd={(t) => scope && setPending(addTable(pending, scope, t))}
          onError={ctx.showError}
        />
        <div>
          {scope && <ScopeList scope={scope} pending={pending} canChange={canChange} onRemove={(row) => setPending(removeTable(pending, scope, row))} />}
          {canChange && <Changes pending={pending} onChange={setPending} onMakeDraft={makeDraft} />}
        </div>
      </div>
    </>
  );
}
