// Editable data-inventory matrix (SRS 3.5 / 10.4). The scan computes category, tier,
// locations and protection; the owner annotates purpose, source, recipients and
// retention in place — these annotations are preserved across re-scans. A second panel
// lists the active suppressions so a reviewer can see and lift them.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type InventoryRow } from "../lib/api";

export function Inventory() {
  const { id = "" } = useParams();
  const inv = useQuery({ queryKey: ["inventory", id], queryFn: () => api.inventory(id) });
  const sup = useQuery({ queryKey: ["suppressions", id], queryFn: () => api.suppressions(id) });

  return (
    <>
      <p className="crumbs">
        <Link to="/applications">Applications</Link> / <Link to={`/applications/${id}`}>Overview</Link> / Data inventory
      </p>
      <h1>Data inventory</h1>
      <p className="muted" style={{ marginTop: -6 }}>
        The scan fills category, tier, locations and protection. Click a cell to edit the
        purpose, source, recipients and retention — your notes are kept across re-scans.
      </p>

      <div className="card" style={{ padding: 0 }}>
        {inv.isLoading ? (
          <p className="muted" style={{ padding: 16 }}>Loading…</p>
        ) : !inv.data || inv.data.inventory.length === 0 ? (
          <p className="empty" style={{ padding: 16 }}>
            No inventory yet. Run a scan on this application's data sources.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Category</th><th>Tier</th><th>Locations</th>
                <th>Purpose</th><th>Source of data</th><th>Recipients</th><th>Retention</th>
              </tr>
            </thead>
            <tbody>
              {inv.data.inventory.map((row) => (
                <InventoryRowEditor key={row.category} applicationId={id} row={row} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2 style={{ marginTop: 24 }}>Suppressions</h2>
      <p className="muted" style={{ marginTop: -6 }}>
        A suppression hides matching findings on every future scan. Lift one to let the
        finding reappear.
      </p>
      <div className="card" style={{ padding: 0 }}>
        {sup.isLoading ? (
          <p className="muted" style={{ padding: 16 }}>Loading…</p>
        ) : !sup.data || sup.data.suppressions.length === 0 ? (
          <p className="empty" style={{ padding: 16 }}>No suppressions.</p>
        ) : (
          <table>
            <thead><tr><th>Match</th><th>Category</th><th>Reason</th><th>Created</th><th /></tr></thead>
            <tbody>
              {sup.data.suppressions.map((s) => (
                <SuppressionRow key={s.id} applicationId={id} id={s.id}
                  match={s.locator_match} category={s.category}
                  reason={s.reason} created={s.created_at} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function InventoryRowEditor({ applicationId, row }: { applicationId: string; row: InventoryRow }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState({
    purpose: row.purpose ?? "",
    source_of_data: row.source_of_data ?? "",
    recipients: row.recipients ?? "",
    retention: row.retention ?? "",
  });
  const dirty =
    draft.purpose !== (row.purpose ?? "") ||
    draft.source_of_data !== (row.source_of_data ?? "") ||
    draft.recipients !== (row.recipients ?? "") ||
    draft.retention !== (row.retention ?? "");

  const save = useMutation({
    mutationFn: () => api.editInventory(applicationId, row.category, {
      purpose: draft.purpose || null,
      source_of_data: draft.source_of_data || null,
      recipients: draft.recipients || null,
      retention: draft.retention || null,
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", applicationId] }),
  });

  const cell = (key: keyof typeof draft) => (
    <td>
      <textarea
        rows={1}
        value={draft[key]}
        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        style={{ minWidth: 150, resize: "vertical" }}
        placeholder="—"
      />
    </td>
  );

  return (
    <tr>
      <td>{row.category}</td>
      <td><span className={`chip tier-${row.tier}`}>{row.tier}</span></td>
      <td className="mono">{row.locations_count}</td>
      {cell("purpose")}
      {cell("source_of_data")}
      {cell("recipients")}
      {cell("retention")}
      <td className="right">
        <button className="btn primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </td>
    </tr>
  );
}

function SuppressionRow({
  applicationId, id, match, category, reason, created,
}: {
  applicationId: string; id: string; match: Record<string, unknown>;
  category: string | null; reason: string | null; created: string | null;
}) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api.deleteSuppression(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suppressions", applicationId] });
      qc.invalidateQueries({ queryKey: ["findings", applicationId] });
    },
  });
  const label = Object.entries(match).map(([k, v]) => `${k}=${v}`).join(" · ") || "any";
  return (
    <tr>
      <td className="mono">{label}</td>
      <td>{category ?? <span className="muted">any</span>}</td>
      <td>{reason ?? <span className="muted">—</span>}</td>
      <td className="muted">{created ? new Date(created).toLocaleDateString() : "—"}</td>
      <td className="right">
        <button className="btn" disabled={del.isPending} onClick={() => del.mutate()}>Lift</button>
      </td>
    </tr>
  );
}
