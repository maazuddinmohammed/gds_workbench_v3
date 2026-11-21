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
};
export type Project = {
  project_id: number;
  project_name: string;
  project_description: string | null;
  project_version: number;
  is_locked: boolean;
};
