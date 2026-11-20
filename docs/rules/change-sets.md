# Rules: Change sets

Every change (a Run, a VS Code push, a hand edit) first becomes a draft change set. A person reviews it and
presses Apply or Reject. Apply saves the whole draft in one transaction, or nothing. Project change sets change
one project; metadata change sets change one tenant's catalog. How rules are written: [rules.md](../rules.md).

## Checked in core/

### CHANGE-SET-001 · Only a draft can be applied or rejected
*Blocks Apply · Approved*

**What it means.** Apply and Reject work only on a change set whose status is draft. One still receiving, or one
already applied or rejected, cannot be applied or rejected.

**Why.** The database knows the four statuses but not which moves between them are allowed. Without this rule a
half-arrived push could be applied, or the same draft applied twice.

**What happens.** The Apply or Reject is refused and the person sees the change set's current status.

**Example.** Ben clicks Apply twice. The first click applies the draft; the second finds it already applied and
does nothing.

### CHANGE-SET-002 · A project draft applies only on the version it was built on
*Blocks Apply · Approved*

**What it means.** Every project has a version number that goes up by one on each Apply. A draft records the
version it was built on. It can be applied only if the project is still at that version.

**Why.** A draft built on old data would quietly undo changes that were applied after it was made.

**What happens.** The Apply is refused. The person makes a new draft from the current project (a new Run, or
pull and push again). The old draft can be rejected.

**Example.** Ben and Asha both have Retail drafts built on version 7. Asha applies hers, so Retail is at 8.
Ben's Apply is refused, because his draft does not know about Asha's changes.

### CHANGE-SET-003 · A change set changes only its own project, or its own tenant's catalog
*Blocks Apply · Approved*

**What it means.** Only the change set itself knows its project (project change sets) or tenant (metadata change
sets). Its records carry no database ids: each names its row by natural key (see
[natural-keys.md](natural-keys.md)). `core/` looks every natural key up only inside that project, or that
tenant's catalog. A key that matches a row there changes that row; a key that matches nothing adds a new row there.

**Why.** A push from the wrong local folder, or a mistake in a Run, must never change another project's or
tenant's rows.

**What happens.** A record can only ever reach rows of its own project or catalog. A record that points at
something outside it (for example a source table the tenant cannot see) is a problem, and the draft cannot be
applied until it is fixed.

**Example.** A Retail draft has entity `silver.Customer`. If Retail has that entity, the draft updates it; if
not, it adds it to Retail. Project HR's `silver.Customer` is never looked at.

### CHANGE-SET-004 · A locked project cannot change
*Refuses the request · Approved*

**What it means.** When a project is locked, nobody can press Run, push from VS Code, edit by hand or apply a
draft for it. A Tenant Admin locks and unlocks a project on the admin page; that is not a project change.

**Why.** The project lock makes a whole project read-only, for example once it has been handed over.

**What happens.** The request is refused with "Retail is locked", and the person asks a Tenant Admin to unlock
it. Drafts made before the lock stay, but cannot be applied until the project is unlocked.

**Example.** Retail is locked. Ben presses Run and is refused. A draft he made yesterday cannot be applied either.

### CHANGE-SET-005 · A Run or a VS Code push cannot change a locked row
*Blocks Apply · Approved*

**What it means.** Rows such as a scope table, an entity or a mapping can be locked one by one. A draft made by
a Run or a VS Code push cannot change or delete a locked row. A hand edit in the web app can, which is how a row
is unlocked.

**Why.** A person locks a row to keep it exactly as it is, while Runs and pushes keep working on the rest.

**What happens.** The draft cannot be applied while it touches a locked row. Remove that change from the draft,
or unlock the row by hand first.

**Example.** Entity Customer is locked. A Silver model Run's draft that leaves Customer alone and adds entity
Order is fine. A VS Code push that renames or deletes Customer is stopped.

### CHANGE-SET-006 · A push becomes a draft only when every piece has arrived
*Refuses the request · Proposed*

**What it means.** A large push from VS Code arrives in numbered pieces, section by section. `core/` joins the
pieces into the draft only when all pieces of every section are in. Until then the change set stays receiving.

**Why.** Joining with a piece missing would quietly drop records, and the draft would look complete when it is not.

**What happens.** The change set stays receiving and cannot be reviewed or applied. The Bridge sends the missing
pieces again, or the person pushes again.

**Example.** The operational attribute section is sent as pieces 1 to 3. With all three in, it becomes a draft.
With only pieces 1 and 3 in, it stays receiving.

### CHANGE-SET-007 · A metadata draft applies only on the catalog version it was built on
*Blocks Apply · Proposed*

**What it means.** The same as CHANGE-SET-002, for a tenant's catalog. The tenant gets a catalog version that
goes up on each metadata Apply, and a metadata draft records the version it was built on.

**Why.** Without it, an old catalog draft could quietly undo catalog changes applied after it was made. The
tenant lock lowers the risk but does not remove it, because drafts outlive the lock.

**What happens.** The same as CHANGE-SET-002: the Apply is refused and the person makes a new draft. This needs
two new columns (a catalog version on the tenant and a base version on the metadata change set), added in their
own small step once this rule is approved.

**Example.** Contoso's catalog is at version 3 and Ben pushes a catalog change. Asha applies hers first, so the
catalog is at 4. Ben's draft, built on 3, is refused.

### CHANGE-SET-011 · A locked catalog cannot change
*Refuses the request · Proposed*

**What it means.** A Tenant Admin can lock a tenant's catalog on the admin page. While it is locked, nobody can
push, hand edit or apply a metadata change set for that tenant. Project work goes on as usual.

**Why.** The catalog changes rarely, and a mistaken change there affects every project in the tenant. Locking it
means nobody changes it by accident.

**What happens.** The request is refused with "Contoso's catalog is locked", and the person asks a Tenant Admin
to unlock it. Metadata drafts made before the lock stay, but cannot be applied until it is unlocked. This needs
one new column, `core.tenant.is_catalog_locked`, added in its own small step once this rule is approved.

**Example.** Contoso's catalog is locked. Ben pushes new columns for `bronze.orders` from VS Code and is refused.
He can still Run and apply drafts for project Retail.

## Checked by the database

Obvious checks (required fields, values from a fixed list such as status and source, keys) are not listed.

### CHANGE-SET-008 · An applied or rejected change set says who decided and when
*Database (`ck_project_change_set_decided`, `ck_metadata_change_set_decided`) · In the schema*

Who pressed Apply or Reject, and when, are filled in exactly when the status is applied or rejected, and empty
otherwise. Every decision has a name and a time on it.

### CHANGE-SET-009 · Every section of a change set is a list
*Database (`ck_project_change_set_documents`, `ck_metadata_change_set_documents`) · In the schema*

Each section holds a JSON list of records, one list per table. The project settings section is a single record,
because a project has one settings row. `core/` can then read every section the same way.

### CHANGE-SET-010 · A pushed piece lands in one known place, once
*Database (`ck_*_stage_chunk_section_name`, `ck_*_stage_chunk_index`, `uq_*_stage_chunk_section_index`) · In the schema*

Each piece of a push names a section that exists, has a number between 1 and the section's piece count, and each
number can arrive only once. A piece cannot land in the wrong section or be counted twice.
