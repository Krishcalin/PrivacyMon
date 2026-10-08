// Platform-admin user management (SRS 11.1). Lists users with their roles,
// creates a user with an optional global role, and edits a user's global roles.
// Per-application roles (Owner/Operator) are granted on the application itself,
// so this screen manages the three global roles (Admin, DPO, Auditor).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AdminUser, type Role } from "../lib/api";

const GLOBAL_ROLES: Role[] = ["admin", "dpo", "auditor"];
const ROLE_LABEL: Record<Role, string> = {
  admin: "Platform Admin",
  dpo: "Data Protection Officer",
  auditor: "Auditor (read-only)",
  owner: "Application Owner",
  operator: "Scan Operator",
};

export function Users() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => api.users(),
  });

  const [showNew, setShowNew] = useState(false);

  if (isLoading) return <div className="card">Loading users…</div>;
  if (error) {
    return (
      <div className="card">
        <p className="muted">You do not have access to user administration.</p>
      </div>
    );
  }

  const users = data?.users ?? [];

  return (
    <div>
      <div className="toolbar">
        <h1 style={{ margin: 0, fontSize: 22 }}>Users &amp; roles</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setShowNew(true)}>
          New user
        </button>
      </div>

      <div className="card" style={{ marginTop: 14, padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Name</th>
              <th>Global roles</th>
              <th>Scoped grants</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRow key={u.id} user={u} qc={qc} />
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No users yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showNew && <NewUserModal onClose={() => setShowNew(false)} />}
    </div>
  );
}

function UserRow({ user, qc }: { user: AdminUser; qc: ReturnType<typeof useQueryClient> }) {
  const current = new Set(user.roles.filter((r) => !r.application_id).map((r) => r.role));
  const scoped = user.roles.filter((r) => r.application_id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Set<Role>>(new Set(current));

  const save = useMutation({
    mutationFn: () => {
      // Keep existing per-application grants; replace only the global set.
      const grants = [
        ...Array.from(draft).map((role) => ({ role, application_id: null as string | null })),
        ...scoped.map((r) => ({ role: r.role, application_id: r.application_id })),
      ];
      return api.setRoles(user.id, grants);
    },
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });

  function toggle(role: Role) {
    setDraft((prev) => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  }

  return (
    <tr>
      <td className="mono">{user.email}</td>
      <td>{user.display_name ?? "—"}</td>
      <td>
        {editing ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {GLOBAL_ROLES.map((r) => (
              <label key={r} style={{ margin: 0, display: "flex", gap: 6, alignItems: "center", textTransform: "none" }}>
                <input
                  type="checkbox"
                  style={{ width: "auto" }}
                  checked={draft.has(r)}
                  onChange={() => toggle(r)}
                />
                {ROLE_LABEL[r]}
              </label>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending}>
                Save
              </button>
              <button className="btn" onClick={() => { setDraft(new Set(current)); setEditing(false); }}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            {[...current].length ? (
              [...current].map((r) => (
                <span key={r} className="chip">
                  {ROLE_LABEL[r]}
                </span>
              ))
            ) : (
              <span className="muted">none</span>
            )}
            <button className="btn" style={{ padding: "2px 8px" }} onClick={() => setEditing(true)}>
              Edit
            </button>
          </span>
        )}
      </td>
      <td>{scoped.length ? `${scoped.length} application(s)` : <span className="muted">—</span>}</td>
      <td>
        <span className={user.active ? "chip" : "chip gray"}>{user.active ? "active" : "disabled"}</span>
      </td>
    </tr>
  );
}

function NewUserModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role | "">("");
  const [err, setErr] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.createUser({
        email: email.trim().toLowerCase(),
        display_name: name.trim() || undefined,
        password,
        global_role: role || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    },
    onError: (e) => setErr(e instanceof Error ? e.message : "failed"),
  });

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>New user</h2>
        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <label>Display name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} />
        <label>Temporary password (min 8 chars)</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <label>Global role (optional)</label>
        <select value={role} onChange={(e) => setRole(e.target.value as Role | "")}>
          <option value="">No global role (per-application only)</option>
          <option value="admin">{ROLE_LABEL.admin}</option>
          <option value="dpo">{ROLE_LABEL.dpo}</option>
          <option value="auditor">{ROLE_LABEL.auditor}</option>
        </select>
        {err && <div className="login-error">{err}</div>}
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button
            className="btn primary"
            disabled={create.isPending || password.length < 8 || !email}
            onClick={() => { setErr(null); create.mutate(); }}
          >
            Create
          </button>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
