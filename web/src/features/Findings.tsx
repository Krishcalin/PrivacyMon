import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type Finding, type Tier } from "../lib/api";

const TIERS: Tier[] = ["critical", "high", "medium", "low"];

function locatorLabel(f: Finding): string {
  const l = f.locator || {};
  if (l.path) return `${l.path}${l.line ? `:${l.line}` : ""}`;
  if (l.table) return `${l.schema ? `${l.schema}.` : ""}${l.table}${l.column ? `.${l.column}` : ""}`;
  return "—";
}

export function Findings() {
  const { id = "" } = useParams();
  // Filters live in the URL so a reviewer can share the exact view (SRS 10.3).
  const [params, setParams] = useSearchParams();
  const [selected, setSelected] = useState<Finding | null>(null);

  const tier = params.get("tier") ?? "";
  const category = params.get("category") ?? "";
  const minConf = params.get("min_confidence") ?? "";

  const qs = new URLSearchParams();
  if (tier) qs.set("tier", tier);
  if (category) qs.set("category", category);
  if (minConf) qs.set("min_confidence", minConf);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";

  const { data, isLoading } = useQuery({
    queryKey: ["findings", id, suffix],
    queryFn: () => api.findings(id, suffix),
  });

  const setFilter = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next, { replace: true });
  };

  const categories = Array.from(new Set((data?.findings ?? []).map((f) => f.category))).sort();

  return (
    <>
      <p className="crumbs"><Link to="/applications">Applications</Link> / <Link to={`/applications/${id}`}>Overview</Link> / Findings</p>
      <h1>Findings</h1>

      <div className="toolbar">
        <select value={tier} onChange={(e) => setFilter("tier", e.target.value)} style={{ width: 160 }}>
          <option value="">All tiers</option>
          {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={category} onChange={(e) => setFilter("category", e.target.value)} style={{ width: 200 }}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={minConf} onChange={(e) => setFilter("min_confidence", e.target.value)} style={{ width: 170 }}>
          <option value="">Any confidence</option>
          <option value="0.8">Likely (≥ 0.80)</option>
          <option value="0.5">Needs review (≥ 0.50)</option>
        </select>
        <div className="spacer" />
        <span className="muted">{data ? `${data.total} findings` : ""}</span>
      </div>

      <div className="card">
        {isLoading ? (
          <p className="muted">Loading…</p>
        ) : !data || data.findings.length === 0 ? (
          <p className="empty">No findings match. Run a scan on this application's data sources.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Category</th><th>Tier</th><th>Confidence</th><th>Location</th><th>Protection</th><th>Review</th></tr>
            </thead>
            <tbody>
              {data.findings.map((f) => (
                <tr key={f.id} className="clickable" onClick={() => setSelected(f)}>
                  <td>{f.category}{f.combined_identity && <span className="chip gray" style={{ marginLeft: 6 }}>combined</span>}</td>
                  <td><span className={`chip tier-${f.tier}`}>{f.tier}</span></td>
                  <td className="mono">{f.confidence.toFixed(2)}</td>
                  <td className="mono">{locatorLabel(f)}</td>
                  <td className="muted">{f.protection_state}</td>
                  <td className="muted">{f.review_state}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && <FindingDrawer finding={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function FindingDrawer({ finding, onClose }: { finding: Finding; onClose: () => void }) {
  const f = finding;
  return (
    <div className="scrim" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>{f.category}</h2>
          <span className={`chip tier-${f.tier}`}>{f.tier}</span>
          <div className="spacer" />
          <button onClick={onClose}>Close</button>
        </div>

        <div className="grid cols-2" style={{ gap: 10, margin: "4px 0 14px" }}>
          <div><div className="l muted">Confidence</div><div className="mono">{f.confidence.toFixed(3)}</div></div>
          <div><div className="l muted">Hit rate</div><div className="mono">{f.hit_rate.toFixed(3)}</div></div>
          <div><div className="l muted">Protection</div><div>{f.protection_state}</div></div>
          <div><div className="l muted">Review</div><div>{f.review_state}</div></div>
        </div>

        <h2>Location</h2>
        <p className="mono">{locatorLabel(f)}</p>

        <h2>Evidence <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>(masked)</span></h2>
        {f.evidence.length === 0 ? (
          <p className="muted">No value evidence — detected from the identifier name.</p>
        ) : (
          <ul>
            {f.evidence.map((e, i) => <li key={i} className="mono" title="Masked by the detector; no reveal control exists">{e}</li>)}
          </ul>
        )}

        {f.combined_identity && (
          <p className="muted" style={{ marginTop: 14 }}>
            Part of a combined-identity record — this location holds two or more categories,
            raising its tier (SRS 4.3).
          </p>
        )}
      </aside>
    </div>
  );
}
