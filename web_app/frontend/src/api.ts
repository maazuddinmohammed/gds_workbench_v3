// Talking to the web backend. Every call goes to /api/...; the backend answers with JSON, or with
// {rule_id, message} when core/ refuses (401 not signed in, 403 refused, 404 not found, 422 wrong shape).
//
// Sign-in: on Databricks, the Databricks Apps proxy adds the signed-in person's email to every request
// (X-Forwarded-Email). Locally there is no proxy, so the page adds that header itself with the demo user picked in
// the "Signed in as" picker. Only the local dev build does this (import.meta.env.DEV); the built page never does.

export const DEMO_USERS = [
  { email: "asha@demo.local", label: "Asha (Viewer)" },
  { email: "ben@demo.local", label: "Ben (Developer)" },
  { email: "cara@demo.local", label: "Cara (Tenant Admin)" },
  { email: "sam@demo.local", label: "Sam (Super Admin)" },
];

export const IS_LOCAL = import.meta.env.DEV;
const DEMO_USER_KEY = "gds.demoUser";

export function demoUser(): string {
  return localStorage.getItem(DEMO_USER_KEY) ?? DEMO_USERS[1].email;
}

export function setDemoUser(email: string) {
  localStorage.setItem(DEMO_USER_KEY, email);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly ruleId: string | null,
    message: string,
  ) {
    super(ruleId ? `${ruleId}: ${message}` : message);
  }
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (IS_LOCAL) headers["X-Forwarded-Email"] = demoUser();
  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.rule_id ?? null, data.message ?? response.statusText);
  return data as T;
}

// The shapes the backend sends (from the dataclasses in core/).
export type User = { principal_id: number; email: string; display_name: string; is_super_admin: boolean };
export type Role = "viewer" | "developer" | "tenant_admin";
export type Tenant = {
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
  tenant_visibility: "global" | "private";
  is_data_lake: boolean;
  role: Role;
  permissions: Permission[];
};
export type Project = {
  project_id: number;
  project_name: string;
  project_description: string | null;
  project_version: number;
  is_locked: boolean;
};
export type Permission = "READ" | "CHANGE" | "MANAGE_TENANT";
export type Lock = {
  tenant_id: number;
  locked_by_principal_id: number;
  locked_by_display_name: string;
  expires_time: string;
  purpose: string | null;
};
export type CatalogTable = {
  object_id: number;
  object_schema: string;
  object_name: string;
  zone_code: string;
  object_type_code: string;
  source_tenant_code: string;
  source_tenant_name: string;
  is_global: boolean;
  connection_tenant_code: string;
  connection_code: string;
  system_code: string;
  is_active: boolean;
  can_scope: boolean;
};
export type TablePage = { tables: CatalogTable[]; page: number; total: number; page_size: number };
export type ScopeTable = {
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
  zone_code: string;
  source_tenant_code: string;
  is_active: boolean;
  is_locked: boolean;
  table_is_active: boolean;
};
export type ScopeRecord = {
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
  is_active: boolean;
  is_locked: boolean;
};
export type Problem = {
  rule_id: string;
  message: string;
  record: number | null;
  part: string | null;
  level: "blocks_apply" | "warning";
};
export type Counts = { added: number; changed: number; switched_off: number; unchanged: number };
export type ChangeSet = {
  project_change_set_id: number;
  project_name: string;
  project_change_set_title: string;
  project_change_set_status: "receiving" | "draft" | "applied" | "rejected";
  project_change_set_source: string;
  base_project_version: number;
  project_version: number;
  created_by_display_name: string;
  created_time: string;
  counts: Record<string, Counts>;
};
export type Change = {
  change: "added" | "changed" | "switched_off";
  record: Record<string, unknown>;
  current?: Record<string, unknown> | null;
};
export type ProjectDetail = {
  tenant_code: string;
  project_name: string;
  project_description: string | null;
  project_version: number;
  is_locked: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  project_config: Record<string, any> | null;
  row_counts: Record<string, number>;
};
export type Model = {
  agent_model_id: number;
  agent_model_display_name: string;
  agent_provider_code: string;
  reasoning_effort_codes: string[];
};
export type RunSummary = {
  run_id: number;
  project_workflow: string;
  run_status: "running" | "completed" | "stopped" | "failed";
  started_time: string;
  completed_time: string | null;
  failure_message: string | null;
  project_change_set_id: number | null;
  project_change_set_status: string | null;
  agent_model_display_name: string | null;
  cost_usd: number | null;
};
export type Run = RunSummary & {
  events: { run_event_stage: string; run_event_status: string; run_event_message: string | null; created_time: string }[];
  usage: { calls: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; cost_usd: number | null };
};
export type ChangeSetRow = {
  project_change_set_id: number;
  project_name: string;
  project_change_set_title: string;
  project_change_set_status: string;
  project_change_set_source: string;
  base_project_version: number;
  project_version: number;
  created_by_display_name: string;
  created_time: string;
};
