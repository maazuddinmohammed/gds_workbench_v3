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


## Checked by the database

Not listed yet. The non-obvious database checks for these tables come in a later small step.

