import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

const ENVIRONMENTS = ["prod", "uat", "dev"];
const HOSTINGS = ["on_prem", "cloud"];
const USER_BASES = ["", "employees", "customers", "vendors", "public"];
const LIFECYCLES = ["draft", "active", "decommissioned"];

export function Applications() {
  const [showForm, setShowForm] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["applications"], queryFn: api.applications });

  return (
    <>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>Applications</h1>
        <div className="spacer" />
        <button className="primary" onClick={() => setShowForm(true)}>Register application</button>
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
    </>
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
