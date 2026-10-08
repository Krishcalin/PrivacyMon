import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fetchReport } from "../lib/api";

const ANSWERS = ["", "yes", "partial", "no", "na"];
const ANSWER_LABEL: Record<string, string> = {
  "": "—", yes: "Yes", partial: "Partial", no: "No", na: "N/A",
};
const NEXT: Record<string, { to: string; label: string; danger?: boolean }[]> = {
  draft: [{ to: "submitted", label: "Submit for review" }],
  submitted: [{ to: "under_review", label: "Begin review" }],
  under_review: [{ to: "approved", label: "Approve" }, { to: "changes_requested", label: "Request changes", danger: true }],
  changes_requested: [{ to: "submitted", label: "Re-submit" }],
  approved: [{ to: "published", label: "Publish" }],
  published: [],
};

// ── DPIA list for one application ─────────────────────────────────────────────
export function DpiaList() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["dpias", id], queryFn: () => api.dpias(id) });
  const create = useMutation({
    mutationFn: () => api.createDpia(id),
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ["dpias", id] }); navigate(`/dpias/${d.id}`); },
  });

  return (
    <>
      <p className="crumbs"><Link to="/applications">Applications</Link> / <Link to={`/applications/${id}`}>Overview</Link> / DPIA assessments</p>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>DPIA assessments</h1>
        <div className="spacer" />
        <button className="primary" disabled={create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "Creating…" : "Start DPIA"}
        </button>
      </div>
      <div className="card">
        {isLoading ? <p className="muted">Loading…</p>
          : !data || data.dpias.length === 0 ? <p className="empty">No DPIA yet. Start one — it pulls the current inventory.</p>
            : (
              <table>
                <thead><tr><th>State</th><th>Inherent</th><th>Residual</th><th>Band</th><th /></tr></thead>
                <tbody>
                  {data.dpias.map((d) => (
                    <tr key={d.id} className="clickable" onClick={() => navigate(`/dpias/${d.id}`)}>
                      <td><span className="chip gray">{d.state}</span></td>
                      <td className="mono">{d.inherent_score ?? "—"}</td>
                      <td className="mono">{d.residual_score ?? "—"}</td>
                      <td>{d.risk_band ? <span className={`chip tier-${d.risk_band === "very_high" ? "critical" : d.risk_band}`}>{d.risk_band}</span> : "—"}</td>
                      <td className="right"><Link to={`/dpias/${d.id}`}>Open</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
      </div>
    </>
  );
}

// ── the workspace ─────────────────────────────────────────────────────────────
export function DpiaWorkspace() {
  const { dpiaId = "" } = useParams();
  const qc = useQueryClient();
  const dpia = useQuery({ queryKey: ["dpia", dpiaId], queryFn: () => api.dpia(dpiaId) });
  const q = useQuery({ queryKey: ["questionnaire", dpiaId], queryFn: () => api.questionnaire(dpiaId) });
  const risks = useQuery({ queryKey: ["dpia-risks", dpiaId], queryFn: () => api.dpiaRisks(dpiaId) });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["dpia", dpiaId] });
    qc.invalidateQueries({ queryKey: ["dpia-risks", dpiaId] });
    qc.invalidateQueries({ queryKey: ["questionnaire", dpiaId] });
  };

  const transition = useMutation({
    mutationFn: (to: string) => api.transitionDpia(dpiaId, to),
    onSuccess: refresh,
  });

  if (dpia.isLoading || q.isLoading) return <p className="muted">Loading…</p>;
  if (!dpia.data || !q.data) return <p className="muted">Not found.</p>;
  const d = dpia.data;
  const appId = d.application_id;

  return (
    <>
      <p className="crumbs"><Link to="/applications">Applications</Link> / <Link to={`/applications/${appId}`}>Overview</Link> / <Link to={`/applications/${appId}/dpias`}>DPIAs</Link> / Assessment</p>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>DPIA — {d.application_name}</h1>
        <span className="chip gray">{d.state}</span>
        <div className="spacer" />
        <button className="btn" onClick={() => fetchReport(dpiaId, "html")}>HTML</button>
        <button className="btn" onClick={() => fetchReport(dpiaId, "pdf")}>PDF</button>
        <button className="btn" onClick={() => fetchReport(dpiaId, "docx")}>DOCX</button>
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat"><div className="n">{d.inherent_score ?? "—"}</div><div className="l">Inherent risk</div></div>
        <div className="card stat"><div className="n">{d.residual_score ?? "—"}</div><div className="l">Residual risk</div></div>
        <div className="card stat">
          <div className="n">{d.risk_band ? <span className={`chip tier-${d.risk_band === "very_high" ? "critical" : d.risk_band}`}>{d.risk_band}</span> : "—"}</div>
          <div className="l">Risk band</div>
        </div>
        <div className="card stat"><div className="n">{q.data.answered}/{q.data.total}</div><div className="l">Answered</div></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="toolbar">
          <h2 style={{ margin: 0 }}>Workflow</h2>
          <div className="spacer" />
          {(NEXT[d.state] ?? []).map((t) => (
            <button key={t.to} className={t.danger ? "" : "primary"}
              disabled={transition.isPending} onClick={() => transition.mutate(t.to)}
              style={t.danger ? { color: "var(--crit)" } : undefined}>{t.label}</button>
          ))}
          {d.state === "published" && <span className="muted">Published ✓</span>}
        </div>
        {transition.isError && <p style={{ color: "var(--crit)" }}>{(transition.error as Error).message}</p>}
      </div>

      {risks.data && risks.data.risks.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Risk register</h2>
          <table>
            <thead><tr><th>Risk</th><th>L×I</th><th>Treatment</th><th>Status</th></tr></thead>
            <tbody>
              {risks.data.risks.map((r) => (
                <tr key={r.id}>
                  <td>{r.title}</td>
                  <td className="mono">{r.likelihood}×{r.impact} = {r.likelihood * r.impact}</td>
                  <td className="muted">{r.treatment ?? "—"}</td>
                  <td><span className="chip gray">{r.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>Questionnaire (A–K)</h2>
      {q.data.sections.map((sec) => (
        <div className="card" key={sec.key} style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>{sec.key}. {sec.title} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· {sec.answered_by}</span></h3>
          {sec.questions.map((qq) => (
            <QuestionRow key={qq.key} dpiaId={dpiaId} q={qq} onSaved={refresh} />
          ))}
        </div>
      ))}
    </>
  );
}

function QuestionRow({ dpiaId, q, onSaved }: {
  dpiaId: string;
  q: { key: string; text: string; guidance: string; affects_risk: boolean; answer: string | null; justification: string | null; suggestion: { answer: string; justification: string } | null };
  onSaved: () => void;
}) {
  const [answer, setAnswer] = useState(q.answer ?? "");
  const [just, setJust] = useState(q.justification ?? "");
  useEffect(() => { setAnswer(q.answer ?? ""); setJust(q.justification ?? ""); }, [q.answer, q.justification]);

  const save = useMutation({
    mutationFn: (payload: { answer: string; justification: string }) =>
      api.saveResponse(dpiaId, q.key, { answer: payload.answer || "na", justification: payload.justification }),
    onSuccess: onSaved,
  });

  const applySuggestion = () => {
    if (!q.suggestion) return;
    setAnswer(q.suggestion.answer);
    setJust(q.suggestion.justification);
    save.mutate({ answer: q.suggestion.answer, justification: q.suggestion.justification });
  };

  return (
    <div style={{ borderTop: "1px solid var(--border)", padding: "10px 0" }}>
      <div className="row" style={{ alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <div><b>{q.key}</b> — {q.text} {q.affects_risk && <span className="chip gray" title="Feeds the residual-risk calculation">affects risk</span>}</div>
          {q.suggestion && answer === "" && (
            <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
              Suggested: {q.suggestion.justification} <a onClick={applySuggestion} style={{ cursor: "pointer" }}>use</a>
            </div>
          )}
        </div>
        <select value={answer} style={{ width: 130 }}
          onChange={(e) => { setAnswer(e.target.value); save.mutate({ answer: e.target.value, justification: just }); }}>
          {ANSWERS.map((a) => <option key={a} value={a}>{ANSWER_LABEL[a]}</option>)}
        </select>
      </div>
      <textarea rows={2} placeholder="Justification / detail" value={just}
        onChange={(e) => setJust(e.target.value)}
        onBlur={() => { if (just !== (q.justification ?? "")) save.mutate({ answer, justification: just }); }}
        style={{ marginTop: 6 }} />
    </div>
  );
}
