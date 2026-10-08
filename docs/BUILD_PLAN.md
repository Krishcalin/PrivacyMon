# PrivacyMon — Build Plan & Status

This maps the four delivery phases in SRS section 13 to concrete increments and
records what is built. Each phase gate (SRS 13.1) is a measurable criterion.

## Phase ordering

Discovery ships before the DPIA workflow so the pilot application has real
findings to assess.

| Phase | Gate (SRS 13.1) | Status |
| --- | --- | --- |
| **Foundation** | SSO login; app + data source CRUD per role; migrations + CI green; Compose stack runs from a clean clone | In progress |
| **Discovery core** | Git + PostgreSQL connectors scan the fixtures; pack precision ≥0.95 and recall ≥0.90; 500-table schema <60 min; findings explorer with filter/drawer/review; live progress | Core engine + platform DB (models, Alembic baseline, RLS) done; connectors next |
| **DPIA workflow** | Questionnaire A–K pre-filled from inventory; risk engine matches a hand-computed case; audited transitions; PDF + DOCX report; portfolio dashboard; first DPIA published | **DONE** — assessment API + console workspace + PDF/DOCX/HTML report; see step 9 |
| **Hardening** | Oracle/MSSQL/MySQL connectors; vault + row-level security; VAPT clean; UAT sign-off; Helm deploy | Not started |

## Done in the current increment

The detection and assessment core — the fully-specified, independently testable
heart of Discovery core and DPIA workflow — plus a minimal Foundation API.

- `dpia_core` library (dependency-free, shared by API and workers):
  - **validators** — Verhoeff (Aadhaar/VID), Luhn + IIN (cards), GSTIN mod-36
    with embedded PAN and state code, PAN holder-type, IFSC, DL/vehicle RTO
    state + year, PIN region, EPF-UAN-fails-Verhoeff, UPI PSP, email role-address
    exclusion, DOB plausibility.
  - **detectors** — 23 detectors across 25 categories (SRS 4.1–4.2), each with
    pattern, validator, positive/negative context and tier; a versioned pack.
  - **engine** — per-column aggregation to one finding with hit rate, the SRS
    confidence formula, protection-state inference, children-from-DOB promotion,
    co-occurrence tier uplift, free-text scanning, summaries.
  - **masking** — per-category evidence masking (SRS 8.5).
  - **controls** — DPDP Act 2023 control library with ISO 27701 / 27001 / CERT-In
    cross-references and the A–K questionnaire (SRS 5.1–5.2).
  - **risk** — inherent/residual scoring, exposure multipliers, control
    effectiveness, bands (SRS 5.3).
- `api` — FastAPI app: `/healthz`, `/readyz`, `/version`, `/controls`,
  `/questionnaire`, `/detectors`, `/detectors/test`.
- `tests` — 49 tests: validators, detector behaviour, confidence, co-occurrence,
  masking, risk (hand-computed case), controls, API, and the precision suite
  (precision 1.00 / recall 1.00 on the current synthetic fixture).
- `fixtures/pii` — checksum-consistent synthetic Indian PII (positives +
  negatives); `fixtures/repo` — a small sample source tree for the Git connector.

## Next increment (Discovery core — connectors & persistence)

1. ~~PostgreSQL platform DB: SQLAlchemy 2 (async) models for the SRS section 8
   schema (registry, scanning, assessment, platform), Alembic baseline migration,
   row-level security policy keyed on application.~~ **DONE** — `platform_db/`:
   23 tables across the four groups with UUID v7 keys and the created/updated audit
   quartet; native PG enums reusing `dpia_core`'s detection enums; `findings`
   LIST-partitioned by `scan_job_id`; GIN indexes on `applications.tags` and
   `findings.locator`; the `0001` Alembic baseline; forced RLS on the nine
   application-scoped tables keyed on two session GUCs; and the append-only
   `audit_log` trigger. Async psycopg 3 session + `set_rls_context` helper. 16 tests
   (structural — no live PostgreSQL in the dev environment).
2. ~~Git connector (`worker/connectors/git.py`): clone/pull, ignore rules, parse
   identifiers + string literals for Python/Java/C#/JS/TS/SQL via `evaluate_text`.~~
   **DONE** — `worker/connectors/`: an SDK contract (`test`/`enumerate`/`scan_unit`,
   FR-2.9), platform + `.gitignore` ignore rules (`ignore.py`), and `GitConnector`
   that scans a working tree two ways — string-literal/comment **values** line by line
   via `evaluate_text`, and **identifiers** via the engine's schema-only path — then
   raises combined-identity records per file. Clone/pull is an injected step (no
   GitPython needed to scan an existing checkout). 12 tests over `fixtures/repo`.
3. ~~PostgreSQL connector: read-only enumerate schemas/tables/columns + capped
   row sampling → `evaluate_column`; grants capture.~~ **DONE** —
   `worker/connectors/postgres.py`: read-only, time-bounded session; enumerates user
   schemas/tables/columns (types + comments); samples a capped set of rows per table
   and runs `evaluate_column` per column (value + name); `table_grants` for FR-2.5.
   Detection logic separated as `_rows_to_findings` (6 DB-free unit tests) with a live
   integration test gated on a target DSN.
4. ~~Celery + Redis scan pipeline (SRS 7.2) with SSE progress; inventory rebuild +
   inherent risk at scan end.~~ **DONE** — `worker/pipeline.py` `run_job` persists a
   connector's findings into a per-job `findings` partition, commits progress per unit,
   rebuilds the `inventory` (upsert preserving owner annotations) and computes inherent
   risk, writing as the trusted owner role. A Celery app (`worker/celery_app.py`) +
   task (`worker/tasks.py`) over Redis run scans in the background; the API
   (`api/app/scans.py`) starts a scan (`POST /data-sources/{id}/scans`), reports status
   (`GET /scans/{id}`), streams progress (`GET /scans/{id}/events`, SSE), and
   pause/resume/cancel flip the job state the worker reads between units (resume skips
   completed units, never double-writing). Validated live end to end through the
   worker: Git scan 38 findings, sample-target Postgres scan 13.
5. ~~React SPA shell: portfolio dashboard, application registry, findings explorer
   (SRS section 10).~~ **DONE** — `web/`: Vite + React 18 + TypeScript (strict) +
   React Router 6 + TanStack Query, a typed API client, and a clean hand-written
   design system. Screens: **portfolio dashboard** (stat tiles, scan-coverage gauge,
   findings-by-tier bars, applications-by-exposure table, PII category heat map),
   **application registry** with a register-application form, **application overview**
   (attributes, data sources with add + scan and live progress polling, tier tiles),
   and the **findings explorer** (faceted filters kept in the URL, masked-evidence
   row drawer). Served by `web/Dockerfile` (nginx builds the SPA and reverse-proxies
   `/api` to the API — same-origin, SSE-friendly). Backed by new console endpoints in
   `api/app/console.py` (register/list applications, add/list data sources, findings,
   inventory, portfolio aggregate). The SRS's shadcn/Recharts/OIDC polish and the
   remaining §10 screens (DPIA workspace, risk register, reports, admin) are later work.
7. **DONE — DPIA processing records (the 30-field "DPIA Fields" sheet).** A new
   `dpia_records` table (migration `0002`, application-scoped RLS) holds the 30 DPDP
   parameters per processing activity; `api/app/dpia.py` is the CRUD; the console
   screen `/applications/:id/dpia` captures them in a grouped form. These are recorded
   per in-scope application alongside the scan-discovered inventory.
8. **DONE — admin registers and scans a target application with read-only
   credentials.** The admin opens the console, clicks **Register scan target**, and
   gives the application name, host/IP, port, database, read-only username and
   password. The password is encrypted at rest with AES-256-GCM (`platform_db/crypto.py`,
   the SRS 7.1 v1 vault default; master key from `PRIVACYMON_MASTER_KEY`) and stored as
   the data source's `credential_ref` — never in clear, never returned. A **Test**
   button opens a read-only connection; **Scan** runs the worker, which decrypts the
   credential transiently, connects read-only, and in **presence-only** mode records
   which columns hold which PII category (PAN, Voter ID, DOB, mobile, …) with no value —
   not even a masked fragment — leaving the target. Endpoints `POST /scan-targets`,
   `POST /data-sources/{id}/test`; connector flag `presence_only`.
   **All four in-scope engines are supported** — PostgreSQL (psycopg connector),
   and MySQL / Oracle / SQL Server through one SQLAlchemy-reflection connector
   (`worker/connectors/sql.py`) that shares the same `detect.scan_columns` detection.
   The console form picks the engine (with its default port); the factory builds the
   right driver URL (psycopg / pymysql / oracledb-thin / pymssql). PostgreSQL and MySQL
   are validated live end to end; Oracle and SQL Server use the identical code path and
   their drivers are installed, but are not exercised here (no instances).
6. ~~docker-compose dev stack wired end to end with a seeded sample target DB.~~
   **DONE** — `infra/api.Dockerfile` + `infra/worker.Dockerfile` + `infra/.env(.example)`;
   `docker compose -f infra/docker-compose.yml --profile full up` brings up Postgres,
   Redis, the API (migrates on start), the Celery worker, and a seeded `sample-target`
   Postgres (`infra/sample-target-init.sql`). The RLS isolation, the append-only audit
   trigger and the `findings` partition were verified against the live database (a
   non-superuser `privacymon_app` role, provisioned by `infra/init-db.sql`, is required
   for RLS to apply — a superuser bypasses it). Both images set `PYTHONPATH=/app` so
   Celery's pool workers resolve the packages.

## Open items carried from SRS section 14 (decide before/with Foundation)

- Product name confirmed as **PrivacyMon** (used in UI, repo, report headers).
- SDF status (fixes DPIA cadence and the DPO-in-India control).
- Vault choice — defaulting to AES-256-GCM envelope encryption in PostgreSQL for
  v1, HashiCorp Vault / CyberArk in Hardening (SRS 7.1).
- Pilot application + owner; target DB priority among Oracle/MSSQL/MySQL.
- NER model (spaCy `en_core_web_trf` CPU vs GPU) for the Deep profile.
- Regional name dictionaries to load; report sign-off block; findings retention.

## DPIA assessment & report (option 1)

**DONE.** The assessment half of the product, closing the loop from scan to signed DPIA.

- **API** (`api/app/assessment.py`): create a DPIA (snapshots the current inventory),
  the A–K questionnaire with per-question yes/partial/no/na + justification and
  **pre-fill suggestions from the scan** (children's data, plain high/critical, user
  base, hosting, critical categories), save responses, **recompute** inherent/residual
  risk from the inventory snapshot + answers (reusing `dpia_core.risk`) and rebuild the
  auto gap-derived **risk register**, audited **workflow transitions** (Draft →
  Submitted → Under review → Changes requested → Approved → Published), and comments.
- **Report** (`api/app/report.py`): a DPIA as **HTML** (pure Python), **PDF**
  (WeasyPrint) and **Word** (python-docx) — application, inventory, risk, register,
  the full A–K answers and a sign-off block. HTML always available; PDF/DOCX libraries
  are imported lazily (and installed in the API image with WeasyPrint's system libs).
- **Console**: a DPIA list per application and a workspace (`web/src/features/Dpia.tsx`)
  with the risk KPIs, the workflow buttons, the risk register, the A–K questionnaire
  with apply-suggestion, and HTML/PDF/DOCX download — linked from the overview.

Validated live end to end: create → answer D/E/H/J → recompute (band + 6 gap risks) →
transition to Published → download a valid PDF/DOCX/HTML, all through the console proxy.

## Authentication, roles & RLS enforcement (option 2)

**DONE.** Local username/password auth with signed-JWT sessions guards the whole API,
and every data read runs as the non-superuser `privacymon_app` role so Postgres RLS
scopes owners to their own applications (the DB-level enforcement the Foundation set up
is now actually driven by the signed-in principal).

- **Auth** (`api/app/auth.py`): PBKDF2-HMAC-SHA256 passwords (stdlib — no new native
  dep), PyJWT HS256 bearer tokens (12 h), a `Principal` resolving global roles
  (Admin/DPO/Auditor) and per-application roles (Owner/Operator), the `current_user`
  dependency and a `require_global` guard, a one-time env-driven **admin bootstrap** on
  an empty users table (no default credential), and the `/auth/login`, `/auth/me`,
  `/admin/users` endpoints. An `idp_subject` column is reserved so an OIDC provider plugs
  in later.
- **Enforcement**: `main.py` guards the scans/console/dpia/assessment/report routers with
  `Depends(current_user)`; `console.py` reads go through `db.scoped_session(principal)`
  (the `privacymon_app` role + per-request RLS context), registering an application
  auto-grants the caller **Owner**, and adding a data source asserts access; `assessment.py`
  restricts **approve/publish** to a DPO or Admin.
- **Scoped session** (`api/app/db.py` + `platform_db/session.py`): `scoped_session` opens
  the restricted-role engine and `set_rls_context_sync` sets the signed-in principal's
  application-id set as the RLS context for the request.
- **Migration 0003**: `users.password_hash` (idempotent, offline-safe).
- **Console**: a session provider (`web/src/lib/auth.tsx`), the Bearer header on every
  API call with a 401 → login drop and a token-aware report download (`lib/api.ts`), a
  **login screen**, a **Users & roles** admin screen (create users, edit the three global
  roles) and a user menu + sign-out with role-aware navigation in the shell.

Validated live on the Docker stack: unauthenticated request → 401; bootstrap-admin login
→ JWT; an Owner sees only its own application (RLS fail-closed, a foreign application
returns 404 with no existence leak) while the global Admin sees all; an Owner's
approve → 403; a non-admin hitting `/admin/users` → 403; a bad password → 401.
