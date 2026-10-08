import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type DpiaRecord } from "../lib/api";

type FieldType = "text" | "textarea" | "bool";
type Field = [key: string, label: string, type: FieldType];

// The 30 DPDP "DPIA Fields", grouped for a readable form.
const GROUPS: { title: string; fields: Field[] }[] = [
  { title: "Identification", fields: [
    ["inventory_id", "Inventory ID", "text"],
    ["business_function", "Business Function", "text"],
    ["data_owner", "Data Owner", "text"],
    ["source_system", "Source System", "text"],
    ["target_systems", "Target System(s)", "text"],
  ] },
  { title: "Data", fields: [
    ["data_principal_type", "Data Principal Type", "text"],
    ["data_category", "Data Category", "text"],
    ["data_elements", "Data Elements", "textarea"],
    ["sensitive_high_risk", "Sensitive / High-Risk", "bool"],
    ["purpose_of_processing", "Purpose of Processing", "textarea"],
    ["legal_basis", "Legal Basis", "text"],
  ] },
  { title: "Retention & Deletion", fields: [
    ["retention_period", "Retention Period", "text"],
    ["deletion_trigger", "Deletion Trigger (Erasure)", "text"],
    ["log_retention", "Log Retention", "text"],
  ] },
  { title: "Security", fields: [
    ["encryption_status", "Encryption Status", "text"],
    ["hosting_location", "Hosting Location (Territorial Application)", "text"],
    ["technical_safeguards", "Technical Safeguards", "textarea"],
    ["organizational_safeguards", "Organizational Safeguards", "textarea"],
    ["security_certifications", "Security Certifications", "text"],
  ] },
  { title: "Processor & Contracts", fields: [
    ["processor_involved", "Processor Involved", "text"],
    ["dpa_signed", "DPA Signed", "bool"],
    ["audit_rights", "Audit Rights", "text"],
    ["breach_sla", "Breach SLA", "text"],
  ] },
  { title: "Rights & Governance", fields: [
    ["consent_withdrawal_mode", "Consent Withdrawal Mode", "text"],
    ["dpo_approval", "DPO Approval", "text"],
    ["data_principal_rights", "Rights as a Data Principal", "textarea"],
    ["children_data_protection", "Protection of Children's Data", "textarea"],
    ["grievance_redressal", "Grievance Redressal Mechanism", "textarea"],
    ["cross_border_transfers", "Cross-Border Data Transfers", "text"],
    ["tracking_cookies", "Tracking Technologies and Cookies", "textarea"],
  ] },
];
const ALL: Field[] = GROUPS.flatMap((g) => g.fields);

export function DpiaRecords() {
  const { id = "" } = useParams();
  const [editing, setEditing] = useState<DpiaRecord | null | "new">(null);
  const { data, isLoading } = useQuery({
    queryKey: ["dpia-records", id],
    queryFn: () => api.dpiaRecords(id),
  });

  return (
    <>
      <p className="crumbs"><Link to="/applications">Applications</Link> / <Link to={`/applications/${id}`}>Overview</Link> / DPIA records</p>
      <div className="toolbar">
        <h1 style={{ margin: 0 }}>DPIA records</h1>
        <div className="spacer" />
        <button className="primary" onClick={() => setEditing("new")}>Add DPIA record</button>
      </div>
      <p className="crumbs">The 30 DPDP Act 2023 processing parameters recorded per processing activity.</p>

      <div className="card">
        {isLoading ? (
          <p className="muted">Loading…</p>
        ) : !data || data.records.length === 0 ? (
          <p className="empty">No DPIA records yet. Add one to capture the processing parameters.</p>
        ) : (
          <table>
            <thead><tr><th>Inventory ID</th><th>Business function</th><th>Legal basis</th><th>Sensitive</th><th>DPO approval</th><th /></tr></thead>
            <tbody>
              {data.records.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => setEditing(r)}>
                  <td className="mono">{(r.inventory_id as string) || "—"}</td>
                  <td>{(r.business_function as string) || "—"}</td>
                  <td className="muted">{(r.legal_basis as string) || "—"}</td>
                  <td>{r.sensitive_high_risk ? <span className="chip tier-high">yes</span> : <span className="muted">no</span>}</td>
                  <td className="muted">{(r.dpo_approval as string) || "—"}</td>
                  <td className="right"><button onClick={(e) => { e.stopPropagation(); setEditing(r); }}>Edit</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing !== null && (
        <RecordForm appId={id} record={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

function RecordForm({ appId, record, onClose }: { appId: string; record: DpiaRecord | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Record<string, string | boolean>>(() => {
    const init: Record<string, string | boolean> = {};
    for (const [key, , type] of ALL) {
      init[key] = type === "bool" ? Boolean(record?.[key]) : ((record?.[key] as string) ?? "");
    }
    return init;
  });

  const mutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {};
      for (const [key, , type] of ALL) {
        body[key] = type === "bool" ? Boolean(form[key]) : ((form[key] as string).trim() || null);
      }
      return record
        ? api.updateDpiaRecord(record.id, body)
        : api.createDpiaRecord(appId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dpia-records", appId] });
      onClose();
    },
  });

  const remove = useMutation({
    mutationFn: () => api.deleteDpiaRecord(record!.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["dpia-records", appId] }); onClose(); },
  });

  const set = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" style={{ width: "min(760px, 94vw)" }} onClick={(e) => e.stopPropagation()}>
        <h2>{record ? "Edit DPIA record" : "New DPIA record"}</h2>
        {GROUPS.map((g) => (
          <div key={g.title} style={{ marginTop: 14 }}>
            <div className="l muted" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6, marginBottom: 8, fontWeight: 700 }}>{g.title}</div>
            <div className="grid cols-2" style={{ gap: 10 }}>
              {g.fields.map(([key, label, type]) => (
                <div key={key} style={{ gridColumn: type === "textarea" ? "1 / -1" : "auto" }}>
                  {type === "bool" ? (
                    <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 18 }}>
                      <input type="checkbox" style={{ width: "auto" }} checked={Boolean(form[key])}
                        onChange={(e) => set(key, e.target.checked)} />
                      {label}
                    </label>
                  ) : (
                    <>
                      <label>{label}</label>
                      {type === "textarea"
                        ? <textarea rows={2} value={form[key] as string} onChange={(e) => set(key, e.target.value)} />
                        : <input value={form[key] as string} onChange={(e) => set(key, e.target.value)} />}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
        {mutation.isError && <p style={{ color: "var(--crit)" }}>{(mutation.error as Error).message}</p>}
        <div className="row" style={{ marginTop: 20, justifyContent: "space-between" }}>
          <div>{record && <button onClick={() => remove.mutate()} style={{ color: "var(--crit)" }}>Delete</button>}</div>
          <div className="row">
            <button onClick={onClose}>Cancel</button>
            <button className="primary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
              {mutation.isPending ? "Saving…" : "Save record"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
