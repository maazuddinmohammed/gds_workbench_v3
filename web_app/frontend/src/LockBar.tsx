// The tenant lock: who holds it and until when, with Take, Release (your own) and Override (someone else's).
// Changes need the lock (ACCESS-003). Ending someone else's lock is always an explicit, confirmed choice.

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Lock, Tenant, User } from "./api";

type Props = { tenant: Tenant; user: User; onChange: (lock: Lock | null) => void; onError: (e: unknown) => void };

export function LockBar({ tenant, user, onChange, onError }: Props) {
  const [lock, setLock] = useState<Lock | null>(null);
  const [minutes, setMinutes] = useState(60);
  const canChange = tenant.permissions.includes("CHANGE");
  const path = `/api/tenants/${tenant.tenant_id}/lock`;

  function show(next: Lock | null) {
    setLock(next);
    onChange(next);
  }

  useEffect(() => {
    api<{ lock: Lock | null }>("GET", path).then((r) => show(r.lock)).catch(onError);
  }, [path]);

  function take() {
    api<{ lock: Lock }>("POST", path, { minutes }).then((r) => show(r.lock)).catch(onError);
  }

  function release() {
    api("DELETE", path).then(() => show(null)).catch(onError);
  }

  function override() {
    const ok = window.confirm(
      `${lock?.locked_by_display_name} holds the lock on ${tenant.tenant_name}. End their lock? ` +
        "It is not handed to you: take it afterwards. Any change they have not applied yet will be refused " +
        "until they take the lock again.",
    );
    if (ok) api("POST", `${path}/override`).then(() => show(null)).catch(onError);
  }

  const mine = lock?.locked_by_principal_id === user.principal_id;
  const until = lock ? new Date(lock.expires_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div className={`lockbar ${mine ? "mine" : lock ? "theirs" : ""}`}>
      {lock === null && <span>Nobody holds the lock on {tenant.tenant_name}.</span>}
      {lock && mine && <span>You hold the lock until {until}.</span>}
      {lock && !mine && (
        <span>
          Locked by {lock.locked_by_display_name} until {until}.
        </span>
      )}
      {canChange && (
        <>
          {(lock === null || mine) && (
            <>
              <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
                {[15, 30, 60, 120, 240].map((m) => (
                  <option key={m} value={m}>
                    {m < 60 ? `${m} minutes` : `${m / 60} hour${m > 60 ? "s" : ""}`}
                  </option>
                ))}
              </select>
              <button onClick={take}>{mine ? "Start my time over" : "Take the lock"}</button>
            </>
          )}
          {lock && mine && <button onClick={release}>Release</button>}
          {lock && !mine && <button onClick={override}>Override</button>}
        </>
      )}
      {!canChange && <span className="muted">Viewers cannot take the lock.</span>}
    </div>
  );
}
