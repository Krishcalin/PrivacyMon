import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Tier } from "../lib/api";

const TIER_ORDER: Tier[] = ["critical", "high", "medium", "low"];

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["portfolio"],
    queryFn: api.portfolio,
  });

  if (isLoading) return <p className="muted">Loading portfolio…</p>;
  if (error) return <p className="muted">Could not load: {(error as Error).message}</p>;
  if (!data) return null;

  const { totals, coverage, categories, applications } = data;

  return (
    <>
      <h1>Portfolio</h1>
      <p className="crumbs">Personal-data exposure across every registered application.</p>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat"><div className="n">{totals.applications}</div><div className="l">Applications</div></div>
        <div className="card stat"><div className="n">{totals.findings}</div><div className="l">Findings</div></div>
        <div className="card stat">
          <div className="n" style={{ color: "var(--crit)" }}>{totals.by_tier.critical ?? 0}</div>
          <div className="l">Critical findings</div>
        </div>
        <div className="card stat">
          <div className="n">{Math.round(coverage * 100)}%</div>
          <div className="l">Scan coverage</div>
          <div className="gauge-track" style={{ marginTop: 8 }}>
            <div className="gauge-fill" style={{ width: `${coverage * 100}%` }} />
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Findings by sensitivity tier</h2>
          {TIER_ORDER.map((t) => {
            const n = totals.by_tier[t] ?? 0;
            const pct = totals.findings ? (n / totals.findings) * 100 : 0;
            return (
              <div key={t} style={{ margin: "10px 0" }}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span><span className={`dot tier-${t}`} />{t}</span>
                  <span className="mono">{n}</span>
                </div>
                <div className="bar"><span className={`tier-${t}`} style={{ width: `${pct}%`, background: `var(--${t === "critical" ? "crit" : t === "high" ? "high" : t === "medium" ? "med" : "low"})` }} /></div>
              </div>
            );
          })}
        </div>

        <div className="card">
          <h2>Applications by exposure</h2>
          <table>
            <thead><tr><th>Application</th><th>Env</th><th>Top tier</th><th className="right">Categories</th></tr></thead>
            <tbody>
              {applications.map((a) => (
                <tr key={a.id} className="clickable">
                  <td><Link to={`/applications/${a.id}`}>{a.name}</Link>{a.internet_facing && <span className="chip gray" style={{ marginLeft: 8 }}>internet-facing</span>}</td>
                  <td className="muted">{a.environment}</td>
                  <td>{a.top_tier ? <span className={`chip tier-${a.top_tier}`}>{a.top_tier}</span> : <span className="muted">—</span>}</td>
                  <td className="right mono">{a.categories.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>PII category heat map</h2>
        {categories.length === 0 ? (
          <p className="empty">No categories detected yet. Register an application and run a scan.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Application</th>
                  {categories.map((c) => <th key={c} className="right" style={{ fontSize: 10.5 }}>{c}</th>)}
                </tr>
              </thead>
              <tbody>
                {applications.map((a) => (
                  <tr key={a.id}>
                    <td><Link to={`/applications/${a.id}`}>{a.name}</Link></td>
                    {categories.map((c) => (
                      <td key={c} className="right">
                        {a.categories.includes(c)
                          ? <span className={`dot tier-${a.top_tier ?? "low"}`} title={`${a.name}: ${c}`} />
                          : <span className="muted">·</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
