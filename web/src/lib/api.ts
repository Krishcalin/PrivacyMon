// Typed client for the PrivacyMon API (SRS section 9). Same-origin /api/v1 in dev
// (Vite proxy) and behind the web container's reverse proxy in the stack.
const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

// ── session token (JWT in localStorage) ───────────────────────────────────────
const TOKEN_KEY = "privacymon.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private window) — session stays in memory only */
  }
}

// Raised on a 401 so the shell can drop the stale token and show the login screen.
export class Unauthorized extends Error {}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401) {
    setToken(null);
    throw new Unauthorized("session expired — please sign in again");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// ── types ────────────────────────────────────────────────────────────────────
export type Tier = "low" | "medium" | "high" | "critical";

export interface Application {
  id: string;
  name: string;
  description?: string | null;
  environment: string;
  hosting: string;
  internet_facing: boolean;
  user_base?: string | null;
  approx_records?: number | null;
  lifecycle: string;
  tags: string[];
}

export interface ApplicationOverview extends Application {
  data_sources: number;
  inventory_categories: number;
  findings_by_tier: Partial<Record<Tier, number>>;
  last_scan: { job_id: string; state: string; findings_count: number } | null;
}

export interface DataSource {
  id: string;
  application_id: string;
  kind: string;
  display_name: string;
  connection: Record<string, unknown>;
  credential_configured: boolean;
  scan_profile_default: string;
  schedule_cron?: string | null;
}

export interface Finding {
  id: string;
  category: string;
  tier: Tier;
  confidence: number;
  hit_rate: number;
  locator: { kind?: string; schema?: string; table?: string; column?: string; path?: string; line?: number };
  protection_state: string;
  combined_identity: boolean;
  review_state: string;
  evidence: string[];
}

export interface InventoryRow {
  category: string;
  tier: Tier;
  locations_count: number;
  rows_estimate: number;
  protection_state_summary: Record<string, number>;
  purpose?: string | null;
  source_of_data?: string | null;
  recipients?: string | null;
  retention?: string | null;
}

export type ReviewActionKind = "confirm" | "false_positive" | "reclassify" | "suppress";

export interface ReviewBody {
  action: ReviewActionKind;
  new_category?: string;
  reason?: string;
  suppress_scope?: "column" | "table" | "path";
}

export interface Suppression {
  id: string;
  locator_match: Record<string, unknown>;
  category: string | null;
  reason: string | null;
  created_at: string | null;
}

export interface InventoryEditBody {
  purpose?: string | null;
  source_of_data?: string | null;
  recipients?: string | null;
  retention?: string | null;
}

export interface Portfolio {
  totals: { applications: number; scanned: number; findings: number; by_tier: Partial<Record<Tier, number>> };
  coverage: number;
  categories: string[];
  applications: {
    id: string; name: string; lifecycle: string; environment: string;
    internet_facing: boolean; tags: string[]; categories: string[];
    top_tier: Tier | null; scanned: boolean;
  }[];
}

export interface ScanJob {
  job_id: string;
  state: string;
  units_total: number;
  units_done: number;
  findings_count: number;
}

// The 30-field DPDP processing/DPIA record. Two fields are booleans; the rest are
// optional text. Indexed access keeps the form generic over the field config.
export interface DpiaRecord {
  id: string;
  application_id: string;
  sensitive_high_risk: boolean;
  dpa_signed: boolean;
  [field: string]: string | boolean | null;
}

// ── endpoints ─────────────────────────────────────────────────────────────────
export const api = {
  portfolio: () => http<Portfolio>("/dashboard/portfolio"),
  applications: () => http<{ applications: Application[] }>("/applications"),
  registerApplication: (body: unknown) =>
    http<Application>("/applications", { method: "POST", body: JSON.stringify(body) }),
  application: (id: string) => http<ApplicationOverview>(`/applications/${id}`),
  dataSources: (id: string) =>
    http<{ data_sources: DataSource[] }>(`/applications/${id}/data-sources`),
  addDataSource: (id: string, body: unknown) =>
    http<DataSource>(`/applications/${id}/data-sources`, {
      method: "POST", body: JSON.stringify(body),
    }),
  registerScanTarget: (body: unknown) =>
    http<{ application_id: string; data_source_id: string }>("/scan-targets", {
      method: "POST", body: JSON.stringify(body),
    }),
  testDataSource: (dataSourceId: string) =>
    http<{ ok: boolean; detail: string }>(`/data-sources/${dataSourceId}/test`, {
      method: "POST",
    }),
  findings: (id: string, qs = "") =>
    http<{ total: number; findings: Finding[] }>(`/applications/${id}/findings${qs}`),
  reviewFinding: (findingId: string, body: ReviewBody) =>
    http<{ id: string; review_state: string; category: string }>(
      `/findings/${findingId}/review`, { method: "POST", body: JSON.stringify(body) }),
  reviewFindingsBulk: (id: string, body: ReviewBody & { finding_ids: string[] }) =>
    http<{ reviewed: number; action: string }>(
      `/applications/${id}/findings/review`, { method: "POST", body: JSON.stringify(body) }),
  suppressions: (id: string) =>
    http<{ count: number; suppressions: Suppression[] }>(`/applications/${id}/suppressions`),
  deleteSuppression: (suppressionId: string) =>
    http<void>(`/suppressions/${suppressionId}`, { method: "DELETE" }),
  inventory: (id: string) =>
    http<{ inventory: InventoryRow[] }>(`/applications/${id}/inventory`),
  editInventory: (id: string, category: string, body: InventoryEditBody) =>
    http<InventoryRow>(`/applications/${id}/inventory/${category}`, {
      method: "PUT", body: JSON.stringify(body),
    }),
  startScan: (dataSourceId: string, opts?: { incremental?: boolean; profile?: string }) => {
    const qs = new URLSearchParams();
    if (opts?.incremental) qs.set("incremental", "true");
    if (opts?.profile) qs.set("profile", opts.profile);
    const tail = qs.toString() ? `?${qs.toString()}` : "";
    return http<{ job_id: string; state: string }>(
      `/data-sources/${dataSourceId}/scans${tail}`, { method: "POST" });
  },
  scan: (jobId: string) => http<ScanJob>(`/scans/${jobId}`),
  dpiaRecords: (id: string) =>
    http<{ records: DpiaRecord[] }>(`/applications/${id}/dpia-records`),
  createDpiaRecord: (id: string, body: unknown) =>
    http<DpiaRecord>(`/applications/${id}/dpia-records`, {
      method: "POST", body: JSON.stringify(body),
    }),
  updateDpiaRecord: (recordId: string, body: unknown) =>
    http<DpiaRecord>(`/dpia-records/${recordId}`, {
      method: "PUT", body: JSON.stringify(body),
    }),
  deleteDpiaRecord: (recordId: string) =>
    http<void>(`/dpia-records/${recordId}`, { method: "DELETE" }),

  // ── DPIA assessment workflow ──────────────────────────────────────────────
  createDpia: (appId: string) =>
    http<DpiaSummary>(`/applications/${appId}/dpias`, { method: "POST" }),
  dpias: (appId: string) =>
    http<{ dpias: DpiaSummary[] }>(`/applications/${appId}/dpias`),
  dpia: (id: string) => http<DpiaDetail>(`/dpias/${id}`),
  questionnaire: (id: string) => http<Questionnaire>(`/dpias/${id}/questionnaire`),
  saveResponse: (id: string, qk: string, body: { answer: string; justification?: string }) =>
    http<{ risk_band: string | null }>(`/dpias/${id}/responses/${qk}`, {
      method: "PUT", body: JSON.stringify(body),
    }),
  recomputeDpia: (id: string) =>
    http<DpiaSummary>(`/dpias/${id}/recompute`, { method: "POST" }),
  transitionDpia: (id: string, to: string, note?: string) =>
    http<DpiaSummary>(`/dpias/${id}/transition`, {
      method: "POST", body: JSON.stringify({ to, note }),
    }),
  dpiaRisks: (id: string) => http<{ risks: RiskRow[] }>(`/dpias/${id}/risks`),
  reportUrl: (id: string, format: "html" | "pdf" | "docx") =>
    `${BASE}/dpias/${id}/report?format=${format}`,

  // ── continuous monitoring ─────────────────────────────────────────────────
  setSchedule: (dataSourceId: string, schedule_cron: string | null) =>
    http<{ data_source_id: string; schedule_cron: string | null }>(
      `/data-sources/${dataSourceId}/schedule`, {
        method: "PUT", body: JSON.stringify({ schedule_cron }),
      }),
  changes: (id: string) =>
    http<{ count: number; changes: ChangeEvent[] }>(`/applications/${id}/changes`),
  acknowledgeChange: (changeId: string) =>
    http<{ id: string; acknowledged: boolean }>(
      `/changes/${changeId}/acknowledge`, { method: "POST" }),
  webhooks: () => http<{ count: number; webhooks: WebhookRow[] }>("/admin/webhooks"),
  createWebhook: (body: { url: string; event_types?: string[]; secret?: string }) =>
    http<{ id: string }>("/admin/webhooks", { method: "POST", body: JSON.stringify(body) }),
  deleteWebhook: (id: string) =>
    http<void>(`/admin/webhooks/${id}`, { method: "DELETE" }),

  // ── custom detectors (admin) ──────────────────────────────────────────────
  customDetectors: () =>
    http<CustomDetectorList>("/admin/detectors"),
  createDetector: (body: CreateDetectorBody) =>
    http<{ id: string }>("/admin/detectors", { method: "POST", body: JSON.stringify(body) }),
  deleteDetector: (id: string) =>
    http<void>(`/admin/detectors/${id}`, { method: "DELETE" }),

  // ── auth & admin ──────────────────────────────────────────────────────────
  login: (email: string, password: string) =>
    http<LoginResponse>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  me: () => http<Me>("/auth/me"),
  users: () => http<{ count: number; users: AdminUser[] }>("/admin/users"),
  createUser: (body: {
    email: string; display_name?: string; password: string; global_role?: Role | null;
  }) => http<{ id: string; email: string }>("/admin/users", {
    method: "POST", body: JSON.stringify(body),
  }),
  setRoles: (userId: string, grants: { role: Role; application_id?: string | null }[]) =>
    http<{ ok: boolean; grants: number }>(`/admin/users/${userId}/roles`, {
      method: "PUT", body: JSON.stringify({ grants }),
    }),
};

// A report is fetched with the Bearer header (a plain <a href> cannot send it),
// then handed to the browser as a blob download / tab.
export async function fetchReport(
  id: string,
  format: "html" | "pdf" | "docx",
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/dpias/${id}/report?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    setToken(null);
    throw new Unauthorized("session expired — please sign in again");
  }
  if (!res.ok) throw new Error(`report failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  if (format === "html") {
    window.open(url, "_blank");
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = `dpia-${id}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export interface ChangeEvent {
  id: string;
  at: string | null;
  severity: string;
  summary: string;
  delta: {
    new_categories?: string[];
    escalated?: { category: string; from: string; to: string }[];
    grew?: { category: string; from: number; to: number }[];
    removed_categories?: string[];
    new_critical?: string[];
  };
  acknowledged: boolean;
  scan_job_id: string | null;
}

export interface WebhookRow {
  id: string;
  url: string;
  event_types: string[];
  active: boolean;
  has_secret: boolean;
}

export interface CustomDetector {
  id: string;
  category: string;
  tier: string;
  pattern: string | null;
  validator: string | null;
  context_positive: string[];
  context_negative: string[];
}

export interface CustomDetectorList {
  validators: string[];
  pack_active: boolean;
  count: number;
  detectors: CustomDetector[];
}

export interface CreateDetectorBody {
  category: string;
  tier: string;
  pattern?: string | null;
  validator?: string | null;
  context_positive?: string[];
  context_negative?: string[];
  description?: string;
}

export type Role = "admin" | "dpo" | "owner" | "auditor" | "operator";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: { email: string; display_name: string | null };
}

export interface Me {
  user_id: string;
  email: string;
  display_name: string | null;
  global_roles: Role[];
  application_ids: string[];
  is_global: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  active: boolean;
  has_password: boolean;
  roles: { role: Role; application_id: string | null }[];
}

export interface DpiaSummary {
  id: string;
  application_id: string;
  state: string;
  needs_review: boolean;
  inherent_score: number | null;
  residual_score: number | null;
  risk_band: Tier | "very_high" | null;
}

export interface DpiaDetail extends DpiaSummary {
  application_name: string | null;
  inventory_snapshot: Record<string, { tier: string; locations_count: number }>;
}

export interface Questionnaire {
  dpia_id: string;
  state: string;
  answered: number;
  total: number;
  sections: {
    key: string; title: string; answered_by: string;
    questions: {
      key: string; text: string; guidance: string; affects_risk: boolean;
      answer: string | null; justification: string | null;
      suggestion: { answer: string; justification: string } | null;
    }[];
  }[];
}

export interface RiskRow {
  id: string; title: string; likelihood: number; impact: number;
  treatment: string | null; status: string;
}
