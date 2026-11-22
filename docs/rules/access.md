# Rules: Access

Who may read and change what. These rules hold for the web app, the MCP server and the Bridge alike: all three
ask `core/` before doing anything, so a person gets the same answer wherever they work. The roles, and what each
one may do, are in [design/shared/access.md](../../design/shared/access.md). How rules are written:
[rules.md](../rules.md).

## Checked in core/

### ACCESS-001 · You can only see a tenant you have access to
*Refuses the request · Approved*

**What it means.** You can read a tenant's catalog, projects, drafts and Runs only if you are a member of that
tenant, the tenant is global, or you are a Super Admin. Access has no end date: it lasts until a Tenant Admin
removes it. A user or a tenant that is switched off (`is_active` false) has no access at all.

**Why.** Each tenant holds one team's catalog and projects. Other teams should not see them.

**What happens.** The request is refused with "not found", not "denied". Someone without access cannot even
tell that the tenant or project exists, as in v2.

**Example.** Asha is a Viewer in Contoso. She can open the Contoso project Retail, and the global tenant Shared.
If she opens a Fabrikam project, or a Tenant Admin removed her from Contoso, she gets "not found".

### ACCESS-002 · Every action needs a role that is allowed to do it
*Refuses the request · Approved*

**What it means.** Each action needs one of three permissions: `READ`, `CHANGE` or `MANAGE_TENANT`.
Viewer has `READ`. Developer also has `CHANGE` (take the tenant lock, change the catalog and projects). Tenant
Admin also has `MANAGE_TENANT` (members, roles, MCP access, and the catalog and project locks). The full table is in [design/shared/access.md](../../design/shared/access.md).

**Why.** Not everyone who can look should be able to change things.

**What happens.** The action is refused and the person is told which role it needs.

**Example.** Ben is a Developer in Contoso, so he can apply a scope draft for Retail. If Ben were a Viewer,
pressing Run on Retail's Silver model would be refused: "needs Developer".

### ACCESS-003 · Every change needs the tenant lock, and you must hold it
*Refuses the request · Approved (changed Nov 21, Maaz: you choose how long; anyone who may change can release it)*

**What it means.** Before changing anything in a tenant (pressing Run, pushing from VS Code, editing by hand,
Apply, Reject, for both kinds of change set), you must hold that tenant's lock. When you take it you choose how
long it lasts, from 1 minute to 4 hours (60 minutes if you do not say). Taking it again while you hold it starts
your time over. A lock past its end time counts as no lock. Super Admins follow this too. Reading never needs the
lock.

Anyone who may change the tenant (Developer, Tenant Admin, Super Admin) may release its lock, their own or
someone else's, and then take it. The web app and the plugin ask them to confirm before releasing someone else's
lock; `core/` does not. Releasing is always its own, explicit request. Nothing else ever releases
a lock: taking the lock, a Run, a VS Code push, an Apply or any MCP tool is simply refused while someone else holds
it (Nov 21, Maaz).

**Why.** Two people changing the same tenant at the same time would overwrite each other's work. Letting anyone
release a lock keeps a forgotten lock from blocking the team, as in v2.

**What happens.** The change is refused. If someone else holds the lock, the message says who and until when,
so you can ask them, wait, or release their lock. A time outside 1 minute to 4 hours is refused.

**Example.** Cara holds Contoso's lock until 15:30. Ben presses Apply and sees "Contoso is locked by Cara until
15:30". Ben releases Cara's lock (after confirming) and takes it for 30 minutes; Cara's next change tells her to
take the lock first. If nobody holds the lock and Ben pushes from VS Code, he is told to take the lock first.

### ACCESS-004 · The MCP server and the Bridge need MCP access in that tenant
*Refuses the request · Approved*

**What it means.** Every MCP tool call, and every Bridge pull, check and push, needs the MCP access switch to be
on in that person's membership of the tenant. This holds for every role, Tenant Admins included (v2 let Tenant
Admins skip it; dropped Nov 21, Maaz). Super Admins always have it, because they have no membership to switch.
ACCESS-001 to 003 still apply on top.

**Why.** The tenant decides who may let an AI tool in VS Code read and change its data.

**What happens.** The MCP or Bridge request is refused. The person can still use the web app as usual.

**Example.** Ben is a Developer in Contoso. With MCP access on, he pulls Retail into VS Code. With it off, his
MCP tool calls are refused, but he can still work in the web app.

### ACCESS-010 · Running SQL on Databricks through MCP needs SQL access in that tenant
*Refuses the request · Approved (Nov 21, Maaz; built together with the `execute_databricks_sql` tool)*

**What it means.** The MCP tool that runs a person's own SQL on Databricks (`execute_databricks_sql`) needs a second
switch, SQL access, to be on in that person's membership of the tenant. It works like the MCP access switch: one
yes/no per person and tenant (`security.tenant_principal_access.sql_access_enabled`, a new column, off by default),
set by a Tenant Admin on the admin page. It holds for every role. Super Admins always have it, because they have no
membership to switch. ACCESS-001 and ACCESS-004 still apply on top, so MCP access must be on too. No other tool
needs this switch; profiling does not, because there the server writes the queries.

**Why.** This tool shows real data to an AI tool. A tenant, or the work a person does in it, may not allow that,
so the tenant must be able to switch it off for one person without taking away the rest of MCP.

**What happens.** The tool call is refused with this rule's ID. Everything else the person does through MCP keeps
working.

**Example.** Ben has MCP access in Contoso but SQL access is off. He can take a snapshot and push a change set, but
`execute_databricks_sql` is refused. A Tenant Admin switches SQL access on for Ben, and the same call now runs.

## Checked by the database

Obvious checks (required fields, names not blank, values from a fixed list, keys) are not listed.

### ACCESS-005 · A user's email is stored in one standard form
*Database (`ck_principal_email`) · In the schema*

The email is stored lower case, without spaces around it, and must contain an `@`. The web app finds you by your
email, so `Asha@Contoso.com` and `asha@contoso.com` must be the same user. `core/` lower-cases the email before
saving; anything else is refused by the database.

### ACCESS-006 · One user per email and per Microsoft account
*Database (`uq_principal_email`, `uq_principal_entra_object_id`) · In the schema*

Two users cannot share an email or a Microsoft object ID. Sign-in must find exactly one user; if it found two,
it would not know whose access to use.

### ACCESS-007 · A user has one role in a tenant
*Database (`uq_tenant_principal_access_tenant_principal`) · In the schema*

There is at most one membership row per user and tenant. To change someone's role, change that row; you
cannot add a second one.

### ACCESS-008 · A tenant has at most one lock
*Database (`uq_tenant_lock_tenant`) · In the schema*

This is the database half of ACCESS-003. If two people press "take lock" at the same moment, only one row can
be saved, so only one of them gets the lock and the other is told who has it.

### ACCESS-009 · A tenant lock lasts at most 4 hours
*Database (`ck_tenant_lock_interval`) · In the schema*

A lock must end after it starts, and no more than 4 hours later. A lock someone forgot to release frees
itself the same day. There is no lock history.
