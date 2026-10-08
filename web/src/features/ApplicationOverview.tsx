import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type Tier } from "../lib/api";

const TIERS: Tier[] = ["critical", "high", "medium", "low"];

export function ApplicationOverview() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const app = useQuery({ queryKey: ["application", id], queryFn: () => api.application(id) });
  const sources = useQuery({ queryKey: ["sources", id], queryFn: () => api.dataSources(id) });

  const testConn = useMutation({
    mutationFn: (dsId: string) => api.testDataSource(dsId),
    onSuccess: (r, dsId) => setTestResult((s) => ({ ...s, [dsId]: r.ok ? "✓ reachable" : `✗ ${r.detail}` })),
  });

  // Poll the active scan until it reaches a terminal state, then refresh overview.
  useQuery({
    queryKey: ["scan", activeJob],
    queryFn: () => api.scan(activeJob!),
    enabled: !!activeJob,
    refetchInterval: (q) => {
      const st = q.state.data?.state;
      if (st && ["completed", "failed", "cancelled"].includes(st)) {
        qc.invalidateQueries({ queryKey: ["application", id] });
        setActiveJob(null);
        return false;
      }
      return 1200;
    },
  });

  const startScan = useMutation({
    mutationFn: (dsId: string) => api.startScan(dsId),
    onSuccess: (r) => setActiveJob(r.job_id),
  });

  if (app.isLoading) return <p className="muted">Loading…</p>;
  if (app.error) return <p className="muted">Could not load: {(app.error as Error).message}</p>;
  if (!app.data) return null;
  const a = app.data;

  return (
    <>
      <p className="crumbs"><Link to="/applications">Applications</Link> / {a.name}</p>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>{a.name}</h1>
        {a.internet_facing && <span className="chip gray">internet-facing</span>}
        <span className="chip gray">{a.lifecycle}</span>
        <div className="spacer" />
        <Link className="btn" to={`/applications/${id}/dpias`}>DPIA assessment</Link>
        <Link className="btn" to={`/applications/${id}/dpia`}>DPIA records</Link>
        <Link className="btn" to={`/applications/${id}/inventory`}>Data inventory</Link>
        <Link className="btn" to={`/applications/${id}/findings`}>View findings</Link>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat"><div className="n">{a.environment}</div><div className="l">Environment</div></div>
        <div className="card stat"><div className="n">{a.data_sources}</div><div className="l">Data sources</div></div>
        <div className="card stat"><div className="n">{a.inventory_categories}</div><div className="l">PII categories</div></div>
        <div className="card stat"><div className="n">{a.last_scan?.findings_count ?? 0}</div><div className="l">Last-scan findings</div></div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Findings by tier</h2>
          <div className="row">
            {TIERS.map((t) => (
              <div key={t} className="card" style={{ flex: 1, textAlign: "center", padding: 12 }}>
                <div className="n" style={{ fontSize: 22, fontWeight: 700 }}>{a.findings_by_tier[t] ?? 0}</div>
                <span className={`chip tier-${t}`}>{t}</span>
              </div>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 12 }}>
            Last scan: {a.last_scan ? `${a.last_scan.state}` : "never run"}.
          </p>
        </div>

        <div className="card">
          <div className="toolbar">
            <h2 style={{ margin: 0 }}>Data sources</h2>
            <div className="spacer" />
            <button onClick={() => setAdding(true)}>Add source</button>
          </div>
          {sources.data && sources.data.data_sources.length > 0 ? (
            <table>
              <thead><tr><th>Name</th><th>Kind</th><th>Schedule</th><th /></tr></thead>
              <tbody>
                {sources.data.data_sources.map((d) => {
                  const c = d.connection as Record<string, unknown>;
                  const locator = c.path
                    ? String(c.path)
                    : c.host
                      ? `${c.host}:${c.port ?? 5432}/${c.database ?? ""}`
                      : String(c.dsn ?? "");
                  return (
                    <tr key={d.id}>
                      <td>
                        {d.display_name}
                        {c.presence_only ? <span className="chip gray" style={{ marginLeft: 6 }}>presence-only</span> : null}
                        <div className="mono muted">{locator}</div>
                        {testResult[d.id] && <div className="muted" style={{ fontSize: 12 }}>{testResult[d.id]}</div>}
                      </td>
                      <td><span className="chip gray">{d.kind}</span></td>
                      <td><ScheduleCell appId={id} dataSourceId={d.id} cron={d.schedule_cron ?? null} /></td>
                      <td className="right">
                        <button disabled={testConn.isPending} onClick={() => testConn.mutate(d.id)}>Test</button>{" "}
                        <button className="primary" disabled={startScan.isPending || !!activeJob}
                          onClick={() => startScan.mutate(d.id)}>
                          {activeJob ? "Scanning…" : "Scan"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <p className="empty">No data sources. Add a Git repo or database to scan.</p>
          )}
          {activeJob && <p className="muted" style={{ marginTop: 10 }}>Scan running… progress updates on completion.</p>}
        </div>
      </div>

      <ChangesPanel appId={id} />

      {adding && <AddSource appId={id} onClose={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["sources", id] }); }} />}
    </>
  );
}

// Common cron presets plus a free-text field; empty clears the schedule.
const CRON_PRESETS: { label: string; value: string }[] = [
  { label: "Off", value: "" },
  { label: "Hourly", value: "0 * * * *" },
  { label: "Daily 02:00", value: "0 2 * * *" },
  { label: "Weekly (Mon 03:00)", value: "0 3 * * 1" },
  { label: "Every 15 min", value: "*/15 * * * *" },
];

function ScheduleCell({ appId, dataSourceId, cron }: { appId: string; dataSourceId: string; cron: string | null }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(cron ?? "");
  const preset = CRON_PRESETS.find((p) => p.value === value) ? value : "__custom";

  const save = useMutation({
    mutationFn: (v: string) => api.setSchedule(dataSourceId, v.trim() || null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources", appId] }),
  });

  return (
    <div style={{ minWidth: 180 }}>
      <select
        value={preset}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "__custom") return;
          setValue(v);
          save.mutate(v);
        }}
        style={{ marginBottom: 4 }}
      >
        {CRON_PRESETS.map((p) => <option key={p.label} value={p.value}>{p.label}</option>)}
        <option value="__custom">Custom…</option>
      </select>
      <div style={{ display: "flex", gap: 4 }}>
        <input className="mono" value={value} placeholder="cron (off)"
          onChange={(e) => setValue(e.target.value)} style={{ fontSize: 12 }} />
        <button className="btn" disabled={save.isPending || value === (cron ?? "")}
          onClick={() => save.mutate(value)}>Set</button>
      </div>
      {save.isError && <div className="muted" style={{ fontSize: 11, color: "var(--crit)" }}>
        {(save.error as Error).message}</div>}
    </div>
  );
}

function ChangesPanel({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const changes = useQuery({ queryKey: ["changes", appId], queryFn: () => api.changes(appId) });
  const ack = useMutation({
    mutationFn: (changeId: string) => api.acknowledgeChange(changeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["changes", appId] }),
  });

  if (changes.isLoading) return null;
  const rows = changes.data?.changes ?? [];

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2 style={{ marginTop: 0 }}>Monitoring timeline</h2>
      <p className="muted" style={{ marginTop: -6 }}>
        Material changes detected between scans. A flagged change marks the application's
        DPIAs for re-review.
      </p>
      {rows.length === 0 ? (
        <p className="empty">No changes detected yet.</p>
      ) : (
        <table>
          <thead><tr><th>When</th><th>Severity</th><th>Change</th><th /></tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} style={{ opacity: c.acknowledged ? 0.55 : 1 }}>
                <td className="muted">{c.at ? new Date(c.at).toLocaleString() : "—"}</td>
                <td><span className={`chip ${c.severity === "high" ? "tier-high" : "tier-medium"}`}>{c.severity}</span></td>
                <td>{c.summary}</td>
                <td className="right">
                  {c.acknowledged
                    ? <span className="muted">acknowledged</span>
                    : <button className="btn" disabled={ack.isPending} onClick={() => ack.mutate(c.id)}>Acknowledge</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AddSource({ appId, onClose }: { appId: string; onClose: () => void }) {
  const [kind, setKind] = useState("git");
  const [name, setName] = useState("");
  const [locator, setLocator] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      api.addDataSource(appId, {
        kind,
        display_name: name.trim() || (kind === "git" ? "repository" : "database"),
        connection: kind === "git" ? { path: locator } : { dsn: locator },
      }),
    onSuccess: onClose,
  });

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Add data source</h2>
        <label>Kind</label>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="git">Git repository</option>
          <option value="postgres">PostgreSQL database</option>
        </select>
        <label>Display name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="app repo" />
        <label>{kind === "git" ? "Repository path (reachable by the worker)" : "Connection DSN"}</label>
        <input className="mono" value={locator} onChange={(e) => setLocator(e.target.value)}
          placeholder={kind === "git" ? "/app/fixtures/repo" : "postgresql://user:pass@host:5432/db"} />
        {mutation.isError && <p style={{ color: "var(--crit)" }}>{(mutation.error as Error).message}</p>}
        <div className="row" style={{ marginTop: 18, justifyContent: "flex-end" }}>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!locator.trim() || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Adding…" : "Add source"}
          </button>
        </div>
      </div>
    </div>
  );
}
