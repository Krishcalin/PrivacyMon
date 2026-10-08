import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";

const ENVIRONMENTS = ["prod", "uat", "dev"];
const DB_KINDS: { value: string; label: string; port: string }[] = [
  { value: "postgres", label: "PostgreSQL", port: "5432" },
  { value: "mysql", label: "MySQL", port: "3306" },
  { value: "oracle", label: "Oracle", port: "1521" },
  { value: "mssql", label: "SQL Server", port: "1433" },
];
const HOSTINGS = ["on_prem", "cloud"];
const USER_BASES = ["", "employees", "customers", "vendors", "public"];
const LIFECYCLES = ["draft", "active", "decommissioned"];

export function Applications() {
  const [showForm, setShowForm] = useState(false);
  const [showTarget, setShowTarget] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["applications"], queryFn: api.applications });

  return (
    <>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>Applications</h1>
        <div className="spacer" />
        <button onClick={() => setShowForm(true)}>Register application</button>
        <button className="primary" onClick={() => setShowTarget(true)}>Register scan target</button>
      </div>
      <p className="crumbs">Every application assessed under the DPDP Act 2023 is registered here.</p>

      <div className="card">
        {isLoading ? (
          <p className="muted">Loading…</p>
        ) : !data || data.applications.length === 0 ? (
          <p className="empty">No applications yet. Register one to begin.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Name</th><th>Environment</th><th>Hosting</th><th>Internet</th><th>Users</th><th>Lifecycle</th><th>Tags</th></tr>
            </thead>
            <tbody>
              {data.applications.map((a) => (
                <tr key={a.id} className="clickable">
                  <td><Link to={`/applications/${a.id}`}>{a.name}</Link></td>
                  <td className="muted">{a.environment}</td>
                  <td className="muted">{a.hosting}</td>
                  <td>{a.internet_facing ? "Yes" : "No"}</td>
                  <td className="muted">{a.user_base ?? "—"}</td>
                  <td><span className="chip gray">{a.lifecycle}</span></td>
                  <td>{a.tags.map((t) => <span key={t} className="chip gray" style={{ marginRight: 4 }}>{t}</span>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showForm && <RegisterForm onClose={() => setShowForm(false)} />}
      {showTarget && <ScanTargetForm onClose={() => setShowTarget(false)} />}
    </>
  );
}

function ScanTargetForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [f, setF] = useState({
    name: "", kind: "postgres", host: "", port: "5432", database: "",
    username: "", password: "", environment: "prod", presence_only: true,
  });
  const set = (k: string, v: unknown) => setF((s) => ({ ...s, [k]: v }));
  const setKind = (value: string) =>
    setF((s) => ({ ...s, kind: value, port: DB_KINDS.find((k) => k.value === value)!.port }));

  const mutation = useMutation({
    mutationFn: () =>
      api.registerScanTarget({
        name: f.name.trim(),
        environment: f.environment,
        kind: f.kind,
        host: f.host.trim(),
        port: Number(f.port) || 5432,
        database: f.database.trim(),
        username: f.username.trim(),
        password: f.password,
        presence_only: f.presence_only,
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      onClose();
      navigate(`/applications/${r.application_id}`);
    },
  });

  const ready = f.name.trim() && f.host.trim() && f.database.trim() && f.username.trim() && f.password;

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Register scan target</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          PrivacyMon connects with a read-only account to detect which fields hold personal
          data (PAN, Voter ID, DOB, mobile, …). With presence-only on, no value — not even a
          masked fragment — leaves the target.
        </p>
        <label>Application name</label>
        <input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="HR Portal" />
        <label>Database engine</label>
        <select value={f.kind} onChange={(e) => setKind(e.target.value)}>
          {DB_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
        <div className="row">
          <div style={{ flex: 2 }}>
            <label>Host / IP address</label>
            <input className="mono" value={f.host} onChange={(e) => set("host", e.target.value)} placeholder="10.0.2.15" />
          </div>
          <div style={{ flex: 1 }}>
            <label>Port</label>
            <input className="mono" value={f.port} onChange={(e) => set("port", e.target.value)} />
          </div>
        </div>
        <label>Database{f.kind === "oracle" ? " / service name" : ""}</label>
        <input className="mono" value={f.database} onChange={(e) => set("database", e.target.value)}
          placeholder={f.kind === "oracle" ? "ORCLPDB1" : "appdb"} />
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Read-only username</label>
            <input className="mono" value={f.username} onChange={(e) => set("username", e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Read-only password</label>
            <input className="mono" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} />
          </div>
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={f.presence_only}
            onChange={(e) => set("presence_only", e.target.checked)} />
          Presence-only (record fields detected, never any value)
        </label>
        {mutation.isError && <p style={{ color: "var(--crit)" }}>{(mutation.error as Error).message}</p>}
        <div className="row" style={{ marginTop: 18, justifyContent: "flex-end" }}>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!ready || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Registering…" : "Register target"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RegisterForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: "", description: "", environment: "prod", hosting: "cloud",
    internet_facing: false, user_base: "", lifecycle: "active", tags: "",
  });

  const mutation = useMutation({
    mutationFn: () =>
      api.registerApplication({
        name: form.name.trim(),
        description: form.description.trim() || null,
        environment: form.environment,
        hosting: form.hosting,
        internet_facing: form.internet_facing,
        user_base: form.user_base || null,
        lifecycle: form.lifecycle,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      onClose();
    },
  });

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Register application</h2>
        <label>Name</label>
        <input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Customer Portal" />
        <label>Description</label>
        <textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={2} />
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Environment</label>
            <select value={form.environment} onChange={(e) => set("environment", e.target.value)}>
              {ENVIRONMENTS.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Hosting</label>
            <select value={form.hosting} onChange={(e) => set("hosting", e.target.value)}>
              {HOSTINGS.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
        </div>
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>User base</label>
            <select value={form.user_base} onChange={(e) => set("user_base", e.target.value)}>
              {USER_BASES.map((x) => <option key={x} value={x}>{x || "—"}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Lifecycle</label>
            <select value={form.lifecycle} onChange={(e) => set("lifecycle", e.target.value)}>
              {LIFECYCLES.map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
        </div>
        <label>Tags (comma-separated)</label>
        <input value={form.tags} onChange={(e) => set("tags", e.target.value)} placeholder="payroll, customer-facing" />
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={form.internet_facing}
            onChange={(e) => set("internet_facing", e.target.checked)} />
          Internet-facing
        </label>
        {mutation.isError && <p style={{ color: "var(--crit)" }}>{(mutation.error as Error).message}</p>}
        <div className="row" style={{ marginTop: 18, justifyContent: "flex-end" }}>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!form.name.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Registering…" : "Register"}
          </button>
        </div>
      </div>
    </div>
  );
}
