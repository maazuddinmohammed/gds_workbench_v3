# Rules: Runs

A Run is pressing Run on a step. It ends in a draft. Only one Run at a time per tenant. How rules are written:
[rules.md](../rules.md).

## Checked in core/

### RUN-001 · A Run's tenant is its project's tenant
*Refuses the request · Approved*

**What it means.** When a Run starts, the tenant stored on it must be the tenant of the project it runs for.

**Why.** A Run stores its tenant so the database can allow only one running Run per tenant. Nothing else checks
that the two agree; if they did not, two Runs could run in the same tenant.

**What happens.** The Run does not start.

**Example.** A Run for project Retail (tenant Contoso) with tenant Contoso: fine. With tenant Fabrikam: refused.

### RUN-002 · A Run's reasoning effort is one its model allows
*Refuses the request · Approved*

**What it means.** Each AI model lists the reasoning efforts it accepts. A Run, and a project's default AI
settings, may only ask for one of those, or for none.

**Why.** Another value would make the AI call fail halfway through the Run.

**What happens.** The Run does not start, or the setting cannot be saved, and the person picks an allowed value.

**Example.** Model GPT X allows low and high. A Run asking for high: fine. Asking for medium, or asking for any
effort when the model allows none: refused.

### RUN-003 · One Run at a time in a tenant
*Refuses the request · Proposed*

**What it means.** A Run starts only when no other Run in the same tenant is running. Before it checks, `core/`
marks a running Run whose Run log has not moved for 30 minutes as failed, because its process has stopped.

**Why.** Metadata belongs to the tenant, and VS Code can link projects, so two Runs at once could build on the same
rows. The database allows one running Run per tenant; this rule gives the person a clear message first, and frees a
tenant whose Run crashed.

**What happens.** The Run does not start, and the person sees whose Run is running.

**Example.** Ben's Silver model Run for Sales is running in ACME, so Asha's mapping Run is refused. If Ben's Run log
has not moved for 30 minutes, it is marked failed and Asha's Run starts.

### RUN-004 · A Run's prompt version belongs to its step
*Refuses the request · Proposed*

**What it means.** The prompt version a Run uses must be a version of a prompt for the same step.

**Why.** A prompt is written for one step's inputs and answer shape. Another step's prompt would get the wrong
inputs and give an answer that cannot be saved.

**What happens.** The Run does not start, and the person picks a prompt for this step.

**Example.** A Silver model Run with a Silver model prompt: fine. With a mapping prompt: refused.

### RUN-005 · A Run's picks exist, are switched on and have what the step needs
*Refuses the request · Proposed*

**What it means.** Each pick must exist in the project and be switched on, and the step must have what it needs:
for example an area with tables and a Silver schema for the Silver model, Silver entities in the area for the Gold
model, and applied mappings for code and validation. Locked picks are not refused: they are skipped before any AI
call, and the log names them.

**Why.** Without these, the AI would be called for nothing, or would make a draft that cannot be applied.

**What happens.** The Run does not start, and the message names what is missing.

**Example.** A Silver model Run for Sales when the project has a Silver schema: fine. When it has none, or Sales has
no tables: refused.

### RUN-006 · An answer fits the step's shape
*Skips the item · Proposed*

**What it means.** Each answer must fit the step's answer shape. An answer that was cut off, refused or does not fit
is not used.

**Why.** A broken answer cannot be turned into draft records, and there are no retries.

**What happens.** That item gets no changes in the draft, and the log names it. The other items carry on.

**Example.** Ten tables in an enrichment Run: nine answers fit, one is cut off. The draft has nine tables, and the
log names the tenth.

### RUN-007 · A Run changes only what it was shown in full, and never a locked row
*Leaves the change out · Proposed*

**What it means.** A Run may change a saved entity only if it was shown that entity in full, in the prompt or by
`get_entity_details`. It never changes a locked row or adds a row under one.

**Why.** An entity the AI has not seen in full would be changed blind, and a locked row was locked to keep it as it is.

**What happens.** In a one shot Run, Python leaves the change out of the draft, and the log says so. In a tool based
Run, the tool refuses the write at once, so the AI knows and carries on.

**Example.** The Sales Run changes entity Customer, which it read in full: fine. It changes Plant without reading it:
refused.

## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

