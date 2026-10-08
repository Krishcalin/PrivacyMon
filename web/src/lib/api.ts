// Typed client for the PrivacyMon API (SRS section 9). Same-origin /api/v1 in dev
// (Vite proxy) and behind the web container's reverse proxy in the stack.
const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
  findings: (id: string, qs = "") =>
    http<{ total: number; findings: Finding[] }>(`/applications/${id}/findings${qs}`),
  inventory: (id: string) =>
    http<{ inventory: InventoryRow[] }>(`/applications/${id}/inventory`),
  startScan: (dataSourceId: string) =>
    http<{ job_id: string; state: string }>(`/data-sources/${dataSourceId}/scans`, {
      method: "POST",
    }),
  scan: (jobId: string) => http<ScanJob>(`/scans/${jobId}`),
};
