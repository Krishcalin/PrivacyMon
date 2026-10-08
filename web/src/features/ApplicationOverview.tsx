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
              <thead><tr><th>Name</th><th>Kind</th><th /></tr></thead>
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

      {adding && <AddSource appId={id} onClose={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["sources", id] }); }} />}
    </>
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
