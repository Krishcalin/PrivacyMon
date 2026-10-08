// Custom detector management (SRS FR-4.7, admin only). An admin defines extra detectors
// — a PII category, a tier, an optional regex, an optional named validator, and column
// -name context keywords — which merge into every scan's detector chain. The server
// validates each definition by compiling it, so a bad regex or unknown validator is
// rejected with a clear message.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CreateDetectorBody } from "../lib/api";

const CATEGORIES = [
  "aadhaar", "pan", "passport", "voter_id", "driving_licence", "gstin",
  "bank_account", "ifsc", "payment_card", "upi_id", "mobile", "email",
  "pin_code", "vehicle_reg", "epf_uan", "dob", "person_name", "address",
  "gender", "health", "biometric", "caste_religion_political", "children_data",
  "photo_id",
];
const TIERS = ["low", "medium", "high", "critical"];

export function Detectors() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["custom-detectors"],
    queryFn: () => api.customDetectors(),
  });
  const [showNew, setShowNew] = useState(false);

  const del = useMutation({
    mutationFn: (id: string) => api.deleteDetector(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["custom-detectors"] }),
  });

  if (isLoading) return <div className="card">Loading detectors…</div>;
  if (error) return <div className="card"><p className="muted">Admin access required.</p></div>;

  const rows = data?.detectors ?? [];

  return (
    <div>
      <div className="toolbar">
        <h1 style={{ margin: 0, fontSize: 22 }}>Custom detectors</h1>
        <div className="spacer" />
        <button className="btn primary" onClick={() => setShowNew(true)}>New detector</button>
      </div>
      <p className="muted" style={{ marginTop: 4 }}>
        These run alongside the built-in pack on every scan. A detector fires on a regex
        match, a validated pattern, or an exact column-name keyword.
      </p>

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Category</th><th>Tier</th><th>Pattern</th><th>Validator</th><th>Name keywords</th><th /></tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.category}</td>
                <td><span className={`chip tier-${d.tier}`}>{d.tier}</span></td>
                <td className="mono" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{d.pattern ?? "—"}</td>
                <td className="mono">{d.validator ?? "—"}</td>
                <td className="muted">{(d.context_positive ?? []).join(", ") || "—"}</td>
                <td className="right">
                  <button className="btn" disabled={del.isPending} onClick={() => del.mutate(d.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="empty">No custom detectors. The built-in pack still runs.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {showNew && <NewDetectorModal validators={data?.validators ?? []} onClose={() => setShowNew(false)} />}
    </div>
  );
}

function NewDetectorModal({ validators, onClose }: { validators: string[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<CreateDetectorBody>({ category: "pan", tier: "high" });
  const [keywords, setKeywords] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.createDetector({
      ...form,
      pattern: form.pattern || null,
      validator: form.validator || null,
      context_positive: keywords.split(",").map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["custom-detectors"] }); onClose(); },
    onError: (e) => setErr(e instanceof Error ? e.message : "failed"),
  });

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>New detector</h2>
        <div className="grid cols-2" style={{ gap: 10 }}>
          <div>
            <label>Category</label>
            <select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label>Tier</label>
            <select value={form.tier} onChange={(e) => setForm((f) => ({ ...f, tier: e.target.value }))}>
              {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <label>Regex pattern (optional)</label>
        <input className="mono" value={form.pattern ?? ""} placeholder="EMP\d{6}"
          onChange={(e) => setForm((f) => ({ ...f, pattern: e.target.value }))} />
        <label>Validator (optional)</label>
        <select value={form.validator ?? ""} onChange={(e) => setForm((f) => ({ ...f, validator: e.target.value }))}>
          <option value="">None</option>
          {validators.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
        <label>Column-name keywords (comma-separated)</label>
        <input value={keywords} placeholder="employee_code, emp_id"
          onChange={(e) => setKeywords(e.target.value)} />
        <p className="muted" style={{ fontSize: 12 }}>
          A detector with neither a pattern nor a validator needs at least one keyword.
        </p>
        {err && <div className="login-error">{err}</div>}
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="btn primary" disabled={create.isPending} onClick={() => { setErr(null); create.mutate(); }}>
            Create
          </button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
