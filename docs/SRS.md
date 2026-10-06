# DPIA Platform — SRS & Architecture

Oct 6, 2026 · @Krishnendu De

## 1. Introduction

The DPIA Platform discovers personal data inside custom-developed applications and turns the findings into a Data Protection Impact Assessment mapped to the Digital Personal Data Protection (DPDP) Act, 2023. Version 1 scans both application source code and live databases, scores each finding for confidence and sensitivity, and produces a per-application DPIA report plus a portfolio view of privacy risk.

### 1.1 Purpose

Give the privacy office and application owners one place to answer three questions for every in-house application: what personal data does it hold, where exactly does it sit (table, column, file, API), and is it handled in line with the DPDP Act and internal policy. The output is evidence an auditor or the Data Protection Board can be shown.

### 1.2 Scope

- In scope (v1): applications registered in the platform; connectors for Git repositories and relational databases (PostgreSQL, Oracle, MS SQL Server, MySQL); detection of Indian personal identifiers listed in section 4; DPIA questionnaire, risk register and report generation; role-based web UI.
- In scope (later phases): OpenAPI specs, application logs, file shares and document stores, SAP and other packaged systems via read-only extracts, CI/CD pipeline integration.
- Out of scope: data masking or remediation inside the target systems; consent management; acting as the system of record for consent or data principal requests.

### 1.3 Regulatory context

The DPDP Rules, 2025 were notified on 13 November 2025 and the substantive obligations on Data Fiduciaries (notice and consent, security safeguards, breach reporting, Significant Data Fiduciary duties) take effect 18 months later, in May 2027 ([AZB & Partners](https://www.azbpartners.com/?p=87799)). A Data Fiduciary must know what personal data it processes before it can meet any of these duties, which is the gap this platform fills. Section 10 of the Act requires Significant Data Fiduciaries to carry out periodic DPIAs, and the platform is built so the same workflow can be run as a voluntary good-practice assessment where that designation does not apply. The platform also records the CERT-In, ISO/IEC 27001 and ISO/IEC 27701 control references relevant to each finding so one assessment serves several frameworks.

### 1.4 Definitions

| Term | Meaning in this document |
| --- | --- |
| Application | A custom-developed system registered in the platform, with one or more data sources |
| Data source | A connector instance: a Git repo, a database schema, later a spec or log path |
| Finding | One detected instance of a personal data category at a specific location, with confidence and evidence |
| PII category | A class of personal data the detectors recognise (Aadhaar, PAN, name, DOB and so on) |
| DPIA | The assessment record for one application: data inventory, questionnaire, risks, treatments, report |
| Data Fiduciary / Data Principal | As defined in the DPDP Act, 2023 |
| Evidence snippet | A masked extract proving a finding, stored with the finding, never the raw value |

## 2. Overall description

The platform is a self-hosted web application: a React front end, a FastAPI back end, background scan workers and a PostgreSQL 16 database, deployed on-premise so that no application data or credentials leave the organisation.

### 2.1 Product perspective

It sits beside existing security tooling rather than replacing it. Source-code findings complement SAST (which looks for vulnerabilities, not data categories); database findings complement DAM or DLP (which watch access and movement, not inventory). The platform reads from target systems and never writes to them.

### 2.2 User roles

| Role | Who | Can do |
| --- | --- | --- |
| Platform Admin | ISD / platform team | Manage users, connectors, detector packs, global settings; all data |
| Privacy Officer / DPO | Privacy office | Create and review DPIAs for any application, approve risk treatments, publish reports, tune detector thresholds |
| Application Owner | Business or IT owner of an application | Register their application, add data sources, run scans, answer the questionnaire, view and comment on findings for their applications only |
| Auditor | Internal audit, external assessor | Read-only access to published DPIAs, findings, audit log and exports |
| Scan Operator | DBA / DevOps delegate | Configure and run scans for assigned applications without seeing the questionnaire or risk register |

### 2.3 Assumptions and constraints

- Read-only database accounts are provisioned for the platform on each target database; the platform never requests write privileges.
- Git repositories are reachable over HTTPS or SSH from the worker network with a deploy token or read-only key.
- Target systems carry production-like data; scanning is scheduled in low-load windows and row sampling is capped (default 1,000 rows per column) so a scan does not become a bulk extract.
- The platform runs in an Indian data centre; no component calls external APIs during a scan.
- Browser support: current Chrome and Edge on the corporate desktop image.
- Oracle and MS SQL connectors depend on vendor client libraries being licensed and installed on the worker image.

## 3. Functional requirements

Requirements are numbered FR-x.y and tagged M (must have in v1), S (should have in v1) or L (later phase). Each is written so it can be turned into an acceptance test.

### 3.1 Application registry

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1.1 | Register an application with name, description, business unit, owner, technical contact, environment (prod / UAT / dev), hosting (on-prem / cloud), internet-facing flag, user base (employees / customers / vendors / public), approximate record count | M |
| FR-1.2 | Attach one or more data sources (section 3.2) to an application | M |
| FR-1.3 | Tag applications (for example CII, customer-facing, payroll) and filter the inventory by tag, owner, risk tier | M |
| FR-1.4 | Bulk import applications from CSV or from the CMDB via API | S |
| FR-1.5 | Application lifecycle states: Draft, Active, Decommissioned; decommissioned apps keep their DPIA history | S |

### 3.2 Connectors and data sources

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-2.1 | Git connector: clone or pull a repository (HTTPS token or SSH key), walk the tree, respect .gitignore and a platform-level ignore list (binaries, vendored libraries, node\_modules, build output) | M |
| FR-2.2 | Git connector: parse Python, Java, C#, JavaScript/TypeScript, SQL and PL/SQL files for identifiers (field, column, variable, parameter names), string literals, ORM models, DTOs and migration scripts | M |
| FR-2.3 | Database connector: connect read-only to PostgreSQL, Oracle, MS SQL Server, MySQL; enumerate schemas, tables, views, columns, data types, comments, row counts | M |
| FR-2.4 | Database connector: sample rows per column with a configurable cap and strategy (TABLESAMPLE or random offset), run detectors on sampled values, never persist raw values | M |
| FR-2.5 | Database connector: capture grants and roles on tables that hold personal data, so the inventory shows who can read them | S |
| FR-2.6 | Connector test button validates credentials and reachability before saving | M |
| FR-2.7 | OpenAPI / Swagger connector: parse request and response schemas and example payloads | L |
| FR-2.8 | Log and file-share connectors: scan files by path or share with the same detectors | L |
| FR-2.9 | Connector SDK: a new connector is a Python class implementing enumerate() and sample(); no core change needed | M |

### 3.3 Scan execution

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-3.1 | Start a scan on demand for an application, a single data source, or a schedule (cron) | M |
| FR-3.2 | Scans run in background workers; the API returns a job ID immediately | M |
| FR-3.3 | Live progress (tables scanned / total, files scanned / total, findings so far) streamed to the UI | M |
| FR-3.4 | Scan profiles: Quick (schema and names only), Standard (plus sampling), Deep (higher sample cap, NER enabled) | M |
| FR-3.5 | Incremental scan: only changed files (git diff since last commit scanned) and new or altered tables | S |
| FR-3.6 | Pause, resume and cancel a running scan; partial results are kept | S |
| FR-3.7 | Concurrency and rate limits per connector so a scan does not load a production database | M |

### 3.4 PII detection

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-4.1 | Detect the identifiers and categories specified in section 4 using pattern, checksum, dictionary and NER detectors | M |
| FR-4.2 | Each finding carries: category, confidence (0–1), sensitivity tier, location (repo/file/line or schema/table/column), masked evidence, detector that fired, scan job | M |
| FR-4.3 | Column-name and variable-name context raises or lowers confidence (section 4.4) | M |
| FR-4.4 | Co-occurrence detection: a table or record that holds two or more identifiers of different categories is flagged as a combined identity record with raised sensitivity | M |
| FR-4.5 | Detect whether a column holding personal data is stored encrypted, hashed or tokenised (entropy and format heuristics) and record it | S |
| FR-4.6 | Reviewer actions on a finding: Confirm, Mark false positive, Reclassify category, Suppress with justification; suppressions persist across scans | M |
| FR-4.7 | Custom detectors: admin can add a regex plus optional validator and context keywords through the UI without a release | M |
| FR-4.8 | Detector packs versioned; a finding records the pack version that produced it | S |

### 3.5 Data inventory and lineage

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-5.1 | Auto-generate a data inventory per application: PII category × location × volume (row count) × protection state × readers | M |
| FR-5.2 | Owner can annotate inventory entries with purpose, source of the data (collected directly / from another system) and downstream recipients | M |
| FR-5.3 | Cross-application view: which applications share the same PII category and, where detectable from foreign keys or matching column names, the same data | S |
| FR-5.4 | Export inventory as CSV and XLSX | M |

### 3.6 DPIA workflow

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-6.1 | Create a DPIA for an application; it pulls the current data inventory as its starting point | M |
| FR-6.2 | Questionnaire (section 5.2) presented to the Application Owner section by section, with save-as-draft, inline guidance and required-field validation | M |
| FR-6.3 | Workflow states: Draft → Submitted → Under review → Changes requested → Approved → Published; each transition recorded with actor and timestamp | M |
| FR-6.4 | Privacy Officer can comment on any answer and request changes; owner sees comments inline | M |
| FR-6.5 | Risk engine computes inherent and residual risk per application from inventory and answers (section 5.3); Privacy Officer can override with justification | M |
| FR-6.6 | Risk register per DPIA: risk, DPDP reference, likelihood, impact, treatment, owner, due date, status | M |
| FR-6.7 | Re-assessment trigger: a new scan that adds a PII category, or a change in internet-facing or user-base attributes, flags the DPIA as Needs review | S |
| FR-6.8 | Annual re-assessment reminder per application, configurable | S |

### 3.7 Reporting and dashboards

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-7.1 | DPIA report per application as HTML, PDF and DOCX: summary, data inventory, DPDP compliance matrix, risks and treatments, sign-offs | M |
| FR-7.2 | Portfolio dashboard: applications ranked by residual risk, PII category heat map, open risks by age, scan coverage (applications scanned in last N days) | M |
| FR-7.3 | Trend view: findings and risk score per application over time | S |
| FR-7.4 | Scheduled report delivery by email (PDF attachment or link) | S |
| FR-7.5 | Report templates editable by Admin (logo, headers, section order) | S |

### 3.8 Administration and integration

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-8.1 | SSO via OIDC or SAML against the corporate IdP; local accounts only for break-glass | M |
| FR-8.2 | Role assignment per user and per application (an owner of app A has no access to app B) | M |
| FR-8.3 | Immutable audit log of every create, update, approve, export and credential use, searchable and exportable | M |
| FR-8.4 | Credential store for connector secrets, encrypted at rest; integration with HashiCorp Vault or CyberArk as the backing store | S |
| FR-8.5 | REST API with token auth for CI/CD: trigger a scan on a repo and fail the pipeline if new high-sensitivity findings appear | S |
| FR-8.6 | Webhooks / email on scan completion, new critical finding, DPIA state change | S |
| FR-8.7 | Retention policy: findings older than N scans are summarised and raw evidence snippets purged | S |

## 4. PII detection specification

Every detector is a Python class with four parts: a pattern (what a value looks like), a validator (checksum or structural test), a context list (column, field and variable names that raise or lower confidence) and a sensitivity tier. Regex alone over-matches badly on Indian data (a 12-digit UAN looks like an Aadhaar, a 10-digit order number like a mobile), so no finding is produced on pattern alone except where noted.

### 4.1 Structured identifiers

| Category | Pattern | Validator | Context keywords (positive) | Tier |
| --- | --- | --- | --- | --- |
| Aadhaar | `[2-9]\d{3}\s?\d{4}\s?\d{4}` (12 digits, first 2–9) | Verhoeff checksum on 12th digit; masked form `X{4}\s?X{4}\s?\d{4}` accepted at lower confidence | aadhaar, aadhar, uid, uidai, adhar | Critical |
| Aadhaar VID | 16 digits | Verhoeff checksum | vid, virtual\_id | Critical |
| PAN | `[A-Z]{5}\d{4}[A-Z]` | 4th char in P C H F A T B L J G; 5th char matches first letter of a nearby surname or entity name when available | pan, pan\_no, permanent\_account, tax\_id | High |
| Passport | `[A-PR-WY][1-9]\d\s?\d{4}[1-9]` | Structural only | passport, ppt\_no, travel\_doc | High |
| Voter ID (EPIC) | `[A-Z]{3}\d{7}` | Structural only; context required | epic, voter, election | High |
| Driving licence | `[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}` | State code in RTO list; year 1950–current | dl, driving, licence, license | High |
| GSTIN | `\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]` | State code 01–38; embedded PAN valid; mod-36 check digit | gst, gstin | Medium (business, but embeds PAN) |
| Bank account | 9–18 digits | Context required; IFSC in same record raises to High confidence | account, acct, a\_c, bank | High |
| IFSC | `[A-Z]{4}0[A-Z0-9]{6}` | Bank code in RBI list | ifsc, branch | Low (locator, not personal) |
| Payment card | 13–19 digits | Luhn checksum; IIN range | card, cc, pan (ambiguous: resolve by length) | High |
| UPI ID | `[\w.\-]{2,256}@[a-zA-Z]{2,64}` | Handle in known PSP list (okaxis, ybl, paytm, upi, oksbi …) | upi, vpa | High |
| Mobile | \`(+91\[-\\s\]? | 0)?\[6-9\]\\d{9}\` | Context required unless +91 or 0 prefix present | mobile, phone, msisdn, contact, cell |
| Email | RFC 5322 simplified | Domain has a dot; not a system address (noreply, admin@) | email, mail | Medium |
| PIN code | `[1-9]\d{5}` | First digit maps to a postal region | pin, pincode, postal, zip | Low (address component) |
| Vehicle registration | `[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}` | State code list | vehicle, reg\_no, rc | Medium |
| EPF UAN | 12 digits | Fails Verhoeff (distinguishes from Aadhaar); context required | uan, pf, epf | Medium |
| Date of birth | Date formats dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd, dd-Mon-yyyy | Year implies age 0–110 | dob, birth, born, date\_of\_birth | Medium |

### 4.2 Unstructured categories (NER and dictionary)

| Category | Method | Tier |
| --- | --- | --- |
| Person name | spaCy `en_core_web_trf` PERSON entities, boosted by a dictionary of common Indian given names and surnames (Bengali, Hindi, Tamil and other regional lists), column names first\_name, surname, applicant\_name, father\_name, spouse\_name | Low alone; raised when combined |
| Address | NER GPE/LOC/FAC plus Indian address tokens (Road, Lane, Nagar, Para, Sarani, Marg, Gali, Colony, Block, Sector, PO, PS, Dist) and a PIN code within 120 characters | Medium |
| Gender | Dictionary (M/F/Male/Female/Other/Transgender) in a column named gender, sex | Low |
| Health | Dictionary of diagnoses, medicines, blood groups, disability terms; ICD-10 codes | Critical |
| Biometric | Column types bytea/BLOB with names fingerprint, iris, face, template, photo; image MIME in files | Critical |
| Caste, religion, political affiliation | Dictionary in columns named category, caste, religion, community | Critical |
| Children's data | DOB implying age under 18, or columns named minor, guardian, student\_class | Critical |
| Photographs and scanned IDs | Image files and BLOB columns alongside identity columns | High |

### 4.3 Sensitivity tiers

| Tier | Meaning | Examples |
| --- | --- | --- |
| Critical | Irreversible harm if exposed; special handling expected | Aadhaar, biometric, health, caste/religion, children's data |
| High | Direct identity or financial theft risk | PAN, passport, voter ID, DL, bank account, card, UPI |
| Medium | Enables contact, profiling or correlation | Mobile, email, address, DOB, vehicle number |
| Low | Weak identifier on its own | Name alone, PIN code, gender, IFSC |

Co-occurrence rule: a table, record or file holding identifiers from two or more categories is raised one tier (Low+Low → Medium, Medium+High → Critical) and labelled a combined identity record.

### 4.4 Confidence model

Confidence is a number from 0 to 1 computed per finding, not per match, so a column is one finding with a hit rate rather than a thousand findings.

```latex
C = \min\left(1,\; B + K_{ctx} + H \cdot 0.3 - N_{ctx}\right)
```

| Symbol | Meaning | Values |
| --- | --- | --- |
| B | Base score of the detector that fired | Pattern only 0.35 · pattern + validator 0.70 · NER 0.45 · dictionary 0.40 |
| K\_ctx | Positive context: column, field or variable name matches the detector's keyword list | +0.25 (exact), +0.15 (partial) |
| H | Hit rate: fraction of sampled non-null values that match | 0–1 (schema-only scans use 0) |
| N\_ctx | Negative context: name suggests a different meaning (order\_id, invoice\_no, txn\_ref, seq) | −0.30 |

Thresholds: C ≥ 0.80 shown as Likely; 0.50–0.79 Needs review; below 0.50 hidden by default but kept. Thresholds are per tier and adjustable by the Privacy Officer. A reviewer's Confirm sets C = 1.0 and False positive sets C = 0 for that location in all later scans until the column changes type or name.

### 4.5 Protection state heuristics

For each column flagged Medium or above, the sampler records whether values look plain, hashed (fixed length 32/40/64 hex), encrypted (high entropy, base64 or bytea, length not matching the identifier) or tokenised (consistent format but fails validator). Plain Critical identifiers in a column are the highest-priority finding the platform produces.

## 5. DPDP Act 2023 mapping and DPIA structure

The DPIA turns scanner output into evidence against each obligation of the Act. Discovery answers the "what and where"; the questionnaire supplies the "why and how"; the control library joins the two so every risk cites the section it would breach. Rule numbers below follow the DPDP Rules, 2025 as notified and should be re-checked against the gazette text before the control library is frozen.

### 5.1 Control library

| Ref | Obligation | What the platform checks | Evidence source |
| --- | --- | --- | --- |
| S.4, S.6 | Processing only with consent or for a legitimate use; consent free, specific, informed, unambiguous, withdrawable | A lawful basis is recorded for every PII category in the inventory; consent capture and withdrawal path described | Questionnaire B + inventory |
| S.5, Rule 3 | Notice to the Data Principal in plain language, available in English and Eighth Schedule languages | Notice text or link attached; categories in notice match categories found by scan | Questionnaire C + diff against inventory |
| S.7 | Legitimate uses (employment, state functions, medical emergency, legal obligation) | Where no consent, the legitimate use is named and fits | Questionnaire B |
| S.8(2) | Processing by a Data Processor only under a valid contract | Processor list with contract reference per PII category shared | Questionnaire F |
| S.8(3) | Accuracy and completeness where data affects a decision | Correction mechanism described | Questionnaire H |
| S.8(4), S.8(5), Rule 6 | Reasonable security safeguards: encryption, masking or tokenisation, access control, logging and monitoring, backups, log retention | Protection state per column (section 4.5); grants captured by connector; owner's answers on access review and monitoring | Scan + Questionnaire E |
| S.8(6), Rule 7 | Breach intimation to the Data Protection Board and affected Data Principals | Incident procedure, contact list, 72-hour reporting path documented | Questionnaire J |
| S.8(7), Rule 8 | Erasure when purpose is served or consent withdrawn; retention periods | Retention period per PII category; purge job or procedure named | Questionnaire D + inventory |
| S.8(9), S.8(10), S.13 | Grievance redressal mechanism and published contact | Grievance channel and SLA documented | Questionnaire H |
| S.9, Rule 10 | Children's data: verifiable parental consent, no tracking or targeted advertising | Age of user base; under-18 indicators from scan; consent flow | Scan + Questionnaire I |
| S.10, Rule 12 | Significant Data Fiduciary duties: DPO in India, independent audit, periodic DPIA, algorithmic due diligence | SDF status recorded at organisation level; DPIA cadence enforced | Admin settings + workflow |
| S.11, S.12, S.14, Rule 13 | Rights of access, correction, erasure, nomination | Procedure and system capability to locate and act on one principal's data across the application | Questionnaire H |
| S.16, Rule 14 | Transfer of personal data outside India | Hosting location, SaaS and processor jurisdictions | Questionnaire G |
| S.33, Schedule | Penalties up to ₹250 crore for failure of security safeguards | Used in risk impact scoring | Risk engine |

Each control also carries a cross-reference to ISO/IEC 27701:2019 (clauses 7 and 8), ISO/IEC 27001:2022 Annex A (A.5.34 privacy and PII protection, A.8.10 information deletion, A.8.11 data masking, A.8.12 DLP) and CERT-In directions, so one DPIA feeds the ISMS and PIMS audits.

### 5.2 Questionnaire sections

| Section | Answered by | Core questions |
| --- | --- | --- |
| A. Processing overview | Owner | Business purpose; data principals (employees, consumers, vendors, public); record volumes; how data enters the system |
| B. Lawful basis and consent | Owner, reviewed by DPO | Basis per PII category; how consent is captured, recorded and withdrawn; consent manager used |
| C. Notice and transparency | Owner | Privacy notice exists, where shown, languages, last updated; matches inventory |
| D. Minimisation and retention | Owner | Is each category necessary for the purpose; retention period; deletion mechanism; archived copies |
| E. Security safeguards | Owner with IT | Encryption at rest and in transit; masking in non-production; access control model; privileged access; logging and monitoring; backup protection |
| F. Processors and sharing | Owner | Internal systems and external parties receiving data; contracts; purpose of sharing |
| G. Cross-border | Owner | Hosting location; any processing or support outside India |
| H. Data principal rights and grievance | Owner | Can the system find, export, correct and erase one person's data; grievance channel and SLA |
| I. Children's data | Owner | Does the system knowingly or possibly hold under-18 data; parental consent; no profiling |
| J. Breach readiness | Owner with ISD | Incident plan covers this application; Board and principal notification path; last tabletop |
| K. Automated decisions | Owner | Any scoring, profiling or automated decision; human review |

Each answer is one of: Yes with evidence, Partial, No, Not applicable with justification. The platform pre-fills what the scan already knows (categories, volumes, protection state, readers) so the owner confirms rather than types.

### 5.3 Risk engine

Inherent risk is computed from the inventory; residual risk applies the control effectiveness derived from questionnaire answers.

```latex
R_{inherent} = \sum_{c \in categories} W_c \cdot V_c \cdot E_{app}
```

```latex
R_{residual} = R_{inherent} \cdot (1 - \eta_{controls})
```

| Factor | Values |
| --- | --- |
| W\_c tier weight | Low 1 · Medium 2 · High 4 · Critical 8 |
| V\_c volume band | <1k rows 1 · 1k–10k 2 · 10k–100k 3 · 100k–1M 4 · >1M 5 |
| E\_app exposure multiplier | ×1.5 internet-facing · ×1.3 external users (consumers/public) · ×1.5 Critical or High data stored plain · ×1.3 read grants beyond the application service account · ×1.2 processors outside India |
| η\_controls effectiveness | 0 to 0.8, from section E, D, H and J answers weighted; Yes with evidence counts full, Partial half, No zero |

Residual score is banded into Very high, High, Medium and Low; the bands are configurable and shown on the portfolio dashboard. Each DPDP control marked No or Partial also produces a line in the risk register with its section reference, so the register is both a risk list and a compliance gap list.

## 6. Non-functional requirements

| ID | Area | Requirement |
| --- | --- | --- |
| NFR-1 | Scan throughput | Standard profile scans a 500-table schema with 1,000-row sampling per column in under 60 minutes on one worker (4 vCPU); a 200k-line repository in under 15 minutes |
| NFR-2 | Target load | Database sampling limited to one connection per target, statement timeout 30 s, configurable pause between tables; CPU impact on the target below 5% in a load test |
| NFR-3 | API latency | 95th percentile under 500 ms for list and detail endpoints with 100k findings in the database |
| NFR-4 | Scale | 500 applications, 2,000 data sources, 10 million findings over three years without schema change; findings table partitioned by scan job |
| NFR-5 | Concurrency | 50 concurrent UI users; 8 parallel scan jobs per worker node; workers scale horizontally |
| NFR-6 | Availability | 99.5% during business hours; a worker crash loses at most the table or file in progress, which is retried |
| NFR-7 | Security | OWASP ASVS Level 2; all traffic TLS 1.2 or higher; secrets never in logs or API responses; dependency scanning in CI; the platform itself passes the organisation's VAPT before go-live |
| NFR-8 | Privacy of the platform | No raw personal data value stored; evidence masked at ingestion; sampled rows held in worker memory only and discarded after detection |
| NFR-9 | Auditability | Every state change, export and credential use written to an append-only audit table with actor, timestamp, before and after; retained 7 years |
| NFR-10 | Data residency | All components deployed in India; no outbound calls except to configured targets, the IdP and the mail relay |
| NFR-11 | Maintainability | Python 3.12, type-hinted, 80% unit test coverage on detectors and risk engine; detector test suite with positive and negative Indian sample sets |
| NFR-12 | Observability | Structured JSON logs, Prometheus metrics (scan duration, findings per minute, queue depth), OpenTelemetry traces |
| NFR-13 | Accessibility | WCAG 2.1 AA for the web UI |
| NFR-14 | Backup and recovery | Nightly PostgreSQL backup, RPO 24 h, RTO 4 h; connector credentials recoverable only through the vault, never from backups |
| NFR-15 | Browser | Current Chrome and Edge; responsive down to 1280 px width (desktop tool, no mobile layout in v1) |

## 7. System architecture

Three tiers with a hard boundary in the middle: the UI and API never hold a connector credential or a raw sampled value; only the scan workers do, and they discard the sample once the detectors have run.

&#91;embedded content: platform components · UI, API, queue, workers, targets, stores\]

The browser talks only to the API; the API enqueues work on Redis; workers pull jobs, read targets with read-only credentials fetched from the vault, and write masked findings back to PostgreSQL.

### 7.1 Components

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web UI | React 18, TypeScript, Vite, TanStack Query, TanStack Table, Recharts, shadcn/ui | Screens in section 10; receives scan progress over SSE |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | REST resources in section 9; authentication via OIDC; per-application authorisation; audit log writes |
| Queue | Redis 7 | Celery broker and result backend; pub/sub channel per scan job for progress events |
| Scan workers | Celery, Python 3.12, GitPython, SQLAlchemy sync engines + vendor drivers (psycopg, oracledb, pyodbc, mysqlclient), spaCy, Tree-sitter | Connector execution, detection, co-occurrence analysis, protection-state heuristics, risk computation, report rendering |
| Platform database | PostgreSQL 16 | All platform state; findings partitioned by scan\_job\_id; row-level security keyed on application for owner role |
| Secrets vault | HashiCorp Vault or CyberArk via a provider interface; fallback to AES-256-GCM envelope encryption in PostgreSQL | Connector credentials, API tokens |
| Report store | Local volume or S3-compatible object store (MinIO) | Rendered PDF and DOCX, versioned per DPIA publication |
| Report renderer | Jinja2 templates → HTML; WeasyPrint for PDF; python-docx for DOCX | Runs inside workers |

### 7.2 Scan pipeline

1. API validates the request, writes a `scan_jobs` row in state Queued and publishes a Celery task with the job ID.
2. Worker claims the task, fetches the connector credential from the vault, sets state Running and opens one connection or clone.
3. Enumerate: the connector lists units of work (tables, or files) and writes them to `scan_units` so progress is resumable.
4. For each unit: schema-level detectors run on names and types first; then, in Standard or Deep profile, the sampler pulls up to the cap of non-null values per column and streams them through the detector chain.
5. Detector chain: structured pattern detectors (compiled regex, Hyperscan optional) → validators → dictionary matchers → NER (Deep profile, or Standard when a text column exceeds 40 characters average).
6. Aggregation: matches per column collapse into one finding with hit rate, confidence, protection state and up to three masked evidence snippets.
7. Co-occurrence pass over the unit's findings sets the combined-identity flag and tier uplift.
8. Findings are written in a batch per unit; a progress event is published; the sample buffer is cleared.
9. On completion the worker recomputes the application's inventory and inherent risk, marks any approved DPIA Needs review if categories changed, sets state Completed and fires webhooks.

### 7.3 Detector plugin model

Detectors live in `detectors/` as subclasses of `BaseDetector` declaring `category`, `tier`, `pattern`, `validate(value)`, `context_positive`, `context_negative`. Packs are directories with a `pack.yaml` manifest and a test fixture of positive and negative samples; the test suite refuses a pack whose precision on the fixture falls below 0.95. Custom detectors created in the UI (FR-4.7) are stored in the database and compiled into the same chain at scan start.

## 8. Data model

PostgreSQL 16 holds four groups of tables: registry, scanning, assessment and platform. All primary keys are UUID v7 (time-ordered) and every mutable table carries `created_at`, `updated_at`, `created_by`, `updated_by`.

### 8.1 Registry

| Table | Key columns | Notes |
| --- | --- | --- |
| `business_units` | id, name, parent\_id | Hierarchy for roll-up dashboards |
| `applications` | id, name, description, business\_unit\_id, owner\_user\_id, tech\_contact\_user\_id, environment, hosting, internet\_facing bool, user\_base enum, approx\_records bigint, lifecycle enum, tags text\[\] | GIN index on tags |
| `data_sources` | id, application\_id, kind enum (git, postgres, oracle, mssql, mysql, openapi, filesystem), display\_name, connection jsonb (no secrets), credential\_ref text, scan\_profile\_default, schedule\_cron, last\_scan\_job\_id | `credential_ref` is a vault path or an envelope-encrypted key id, never the secret |

### 8.2 Scanning

| Table | Key columns | Notes |
| --- | --- | --- |
| `detector_packs` | id, name, version, source enum (builtin, custom), manifest jsonb, active bool | A finding points at the pack version that produced it |
| `detectors` | id, pack\_id, category, tier, pattern, validator, context\_positive text\[\], context\_negative text\[\], base\_score numeric | Custom detectors (FR-4.7) live here with source = custom |
| `scan_jobs` | id, data\_source\_id, application\_id, profile, state enum, started\_at, finished\_at, units\_total, units\_done, findings\_count, error text, triggered\_by | State machine: Queued, Running, Paused, Completed, Failed, Cancelled |
| `scan_units` | id, scan\_job\_id, kind (table, file), locator text, state, rows\_sampled, duration\_ms | Resumability and per-table timings |
| `findings` | id, scan\_job\_id, application\_id, data\_source\_id, unit\_id, category, tier, confidence numeric(4,3), hit\_rate numeric(4,3), locator jsonb (schema, table, column or path, line), protection\_state enum, combined\_identity bool, evidence jsonb (max 3 masked snippets), detector\_id, pack\_version, review\_state enum, reviewed\_by, reviewed\_at, suppression\_id | Partitioned by `scan_job_id` (LIST, one partition per job created at job start, old partitions detached for archival). Indexes on (application\_id, category, tier), (locator), review\_state |
| `suppressions` | id, application\_id, locator\_match jsonb, category, reason, created\_by, expires\_at | Applied before writing a finding; a matching finding is written with review\_state = suppressed |
| `inventory` | id, application\_id, category, tier, locations\_count, rows\_estimate bigint, protection\_state\_summary jsonb, readers jsonb, purpose, source\_of\_data, recipients, computed\_at | One row per application × category; rebuilt at scan end; owner-annotated columns preserved across rebuilds |

### 8.3 Assessment

| Table | Key columns | Notes |
| --- | --- | --- |
| `questionnaire_templates` | id, version, sections jsonb | Versioned; a DPIA pins the version it was answered against |
| `dpia_assessments` | id, application\_id, template\_version, state enum, inventory\_snapshot jsonb, inherent\_score, residual\_score, risk\_band, submitted\_at, approved\_at, approved\_by, published\_at, report\_object\_key | Snapshot keeps the assessment stable while scans continue |
| `questionnaire_responses` | id, dpia\_id, question\_key, answer enum (yes, partial, no, na), justification, evidence\_refs jsonb, answered\_by, answered\_at | Unique on (dpia\_id, question\_key) |
| `dpia_comments` | id, dpia\_id, question\_key nullable, body, author\_id, resolved bool | Reviewer dialogue |
| `controls` | id, framework enum (dpdp, iso27701, iso27001, certin), reference, title, description, question\_keys text\[\] | The control library of section 5.1 |
| `risks` | id, dpia\_id, title, control\_id, likelihood 1–5, impact 1–5, inherent\_score, treatment enum (mitigate, accept, transfer, avoid), treatment\_plan, owner\_user\_id, due\_date, status enum, residual\_likelihood, residual\_impact | Risk register |
| `dpia_transitions` | id, dpia\_id, from\_state, to\_state, actor\_id, note, at | Workflow history |

### 8.4 Platform

| Table | Key columns | Notes |
| --- | --- | --- |
| `users` | id, idp\_subject, email, display\_name, active | Provisioned on first SSO login (JIT) |
| `roles` and `user_roles` | user\_id, role enum, application\_id nullable | Global role when application\_id is null; owner and operator roles are per application |
| `api_tokens` | id, user\_id, name, hashed\_token, scopes text\[\], expires\_at, last\_used\_at | CI/CD and integrations |
| `audit_log` | id, at, actor\_id, action, object\_type, object\_id, before jsonb, after jsonb, ip, request\_id | Append-only: INSERT privilege only for the application role; a trigger rejects UPDATE and DELETE |
| `webhooks` | id, event\_types text\[\], url, secret\_ref, active | Outbound notifications |
| `settings` | key, value jsonb | Thresholds, risk bands, retention, SDF flag |

### 8.5 Masking and retention rules

- Evidence is masked by the detector before it leaves worker memory: Aadhaar keeps the last 4 digits, PAN the first 3 and last 1, mobile the last 4, email the first character and the domain, names and addresses are replaced by their shape (`Xxxxx Xxxx`, `nn, Xxxxx Road, nnnnnn`).
- Row-level security on `applications`, `data_sources`, `findings`, `inventory` and `dpia_*` tables, keyed on a session variable set by the API from the user's per-application roles, so an owner query cannot return another application's rows even if the API filter has a bug.
- A nightly job detaches `findings` partitions for jobs older than the retention setting (default 24 months), keeps the aggregated `inventory` history, and drops the partitions after a configurable grace period.

## 9. API specification

REST under `/api/v1`, JSON bodies, OpenAPI 3.1 generated by FastAPI and served at `/api/docs` (disabled in production unless the Admin role is present). Authentication is a bearer JWT from the IdP or a platform API token; authorisation is enforced per application in a dependency that also sets the row-level-security session variable. List endpoints support `?page`, `?page_size` (max 200), `?sort`, and field filters; responses carry `X-Total-Count`.

| Resource | Method and path | Purpose | Roles |
| --- | --- | --- | --- |
| Auth | `GET /auth/me` · `POST /auth/tokens` · `DELETE /auth/tokens/{id}` | Current user and roles; manage API tokens | All; Admin for others' tokens |
| Business units | `GET/POST /business-units` · `PATCH/DELETE /business-units/{id}` | Hierarchy | Admin, DPO |
| Applications | `GET/POST /applications` · `GET/PATCH/DELETE /applications/{id}` · `POST /applications/import` | Registry; CSV import | Owner (own), DPO, Admin |
| Data sources | `GET/POST /applications/{id}/data-sources` · `PATCH/DELETE /data-sources/{id}` · `POST /data-sources/{id}/test` | Connector config; connectivity test (credential never returned) | Owner, Operator, Admin |
| Scans | `POST /data-sources/{id}/scans` · `POST /applications/{id}/scans` · `GET /scans` · `GET /scans/{id}` · `POST /scans/{id}/pause` · `/resume` · `/cancel` | Start and control jobs; body carries `profile` and optional `incremental` | Owner, Operator, DPO, Admin |
| Scan progress | `GET /scans/{id}/events` (text/event-stream) | SSE: `unit_done`, `finding`, `state`, `error` events | Same as Scans |
| Findings | `GET /applications/{id}/findings` · `GET /findings/{id}` · `POST /findings/{id}/review` · `POST /findings/bulk-review` | Filter by category, tier, confidence\_min, review\_state, locator; review body `{action: confirm \| false_positive \| reclassify \| suppress, category?, reason?}` | Owner, DPO, Auditor (read) |
| Suppressions | `GET/POST /applications/{id}/suppressions` · `DELETE /suppressions/{id}` | Persistent false-positive rules | Owner, DPO |
| Inventory | `GET /applications/{id}/inventory` · `PATCH /inventory/{id}` · `GET /applications/{id}/inventory/export?format=csv\|xlsx` | Category × location view with owner annotations | Owner, DPO, Auditor |
| Detectors | `GET /detector-packs` · `GET/POST /detectors` · `PATCH/DELETE /detectors/{id}` · `POST /detectors/{id}/test` | Built-in and custom detectors; test runs a detector against submitted sample strings | Admin, DPO |
| DPIAs | `GET/POST /applications/{id}/dpias` · `GET /dpias/{id}` · `POST /dpias/{id}/transition` | Create, read, move through workflow (`{to: submitted \| under_review \| changes_requested \| approved \| published, note}`) | Owner (create, submit), DPO (review, approve, publish) |
| Responses | `GET /dpias/{id}/responses` · `PUT /dpias/{id}/responses/{question_key}` | Save answers; PUT is idempotent | Owner, DPO |
| Comments | `GET/POST /dpias/{id}/comments` · `PATCH /comments/{id}` | Reviewer dialogue; resolve | Owner, DPO |
| Risks | `GET/POST /dpias/{id}/risks` · `PATCH/DELETE /risks/{id}` · `POST /dpias/{id}/recompute` | Risk register; recompute scores from inventory and answers | Owner (read, propose), DPO |
| Controls | `GET /controls?framework=dpdp` | Control library | All |
| Reports | `POST /dpias/{id}/reports` · `GET /dpias/{id}/reports/{version}?format=pdf\|docx\|html` | Render and fetch; render is async and returns a job id | Owner, DPO, Auditor |
| Dashboard | `GET /dashboard/portfolio` · `GET /dashboard/coverage` · `GET /dashboard/trends?application_id=` | Aggregates for the home screen | All (scoped by role) |
| Admin | `GET/POST /users` · `PUT /users/{id}/roles` · `GET/PUT /settings` · `GET/POST /webhooks` · `GET /audit-log` | Platform administration | Admin; Auditor for audit log |
| Health | `GET /healthz` · `GET /readyz` · `GET /metrics` | Liveness, readiness (DB and Redis), Prometheus | Unauthenticated on the internal network only |

### 9.1 Conventions

- Errors follow RFC 9457 problem details: `{type, title, status, detail, instance, errors[]}`.
- Every mutating request accepts an `Idempotency-Key` header; repeated keys within 24 hours return the original response.
- Finding evidence in any response is already masked; there is no endpoint that returns a raw sampled value.
- Webhook payloads are signed with HMAC-SHA256 over the body using the webhook secret, header `X-DPIA-Signature`.
- CI/CD contract: `POST /data-sources/{id}/scans` with `{profile: "quick", wait: true, fail_on: {tier: "high", new_only: true}}` blocks up to 10 minutes and returns 200 with a summary or 409 when new findings at or above the tier appear.

## 10. Frontend design

A single-page React application organised around the application as the unit of work: every screen after the dashboard lives under one application's route, and the left navigation shows that application's scan, findings, inventory and DPIA state at a glance.

### 10.1 Stack and structure

| Concern | Choice |
| --- | --- |
| Build and language | Vite, React 18, TypeScript strict, ESLint + Prettier |
| Routing | React Router 6, route-level code splitting |
| Server state | TanStack Query with generated typed client from the OpenAPI schema (openapi-typescript + fetch wrapper); SSE handled by a small hook that writes into the query cache |
| UI state | Zustand for cross-screen state (selected application, filters); URL search params for anything shareable |
| Components | shadcn/ui on Radix primitives and Tailwind; TanStack Table for the findings grid (virtualised rows); Recharts for dashboards; react-hook-form + Zod for forms |
| Auth | OIDC PKCE flow in the browser (oidc-client-ts); token kept in memory, refreshed silently |
| Testing | Vitest + React Testing Library; Playwright for the five critical flows (register app, run scan, review finding, complete DPIA, export report) |
| Folder layout | `src/app` (routes, layout), `src/features/<feature>` (api, components, hooks per feature), `src/components/ui` (shared), `src/lib` (client, auth, format) |

### 10.2 Screens

| Screen | Route | What the user sees and does |
| --- | --- | --- |
| Portfolio dashboard | `/` | Applications ranked by residual risk band; PII category heat map (applications × categories); scan coverage gauge; open risks by age; filters by business unit and tag |
| Application inventory | `/applications` | Table of applications with owner, environment, internet-facing, last scan, risk band, DPIA state; create and import actions |
| Application overview | `/applications/:id` | Header card with attributes and lifecycle; tiles for data sources, last scan, findings by tier, inventory categories, DPIA status; activity feed |
| Data sources | `/applications/:id/sources` | Add or edit connector (form adapts to kind); test connection; schedule; last job result |
| Scan launcher and progress | `/applications/:id/scans/:jobId` | Profile picker; live progress bars per unit, findings counter ticking up, log tail; pause, resume, cancel |
| Findings explorer | `/applications/:id/findings` | Virtualised grid: category, tier, confidence, location, hit rate, protection state, review state; faceted filters; row drawer with masked evidence and detector reasoning; single and bulk review actions; group-by table or file |
| Data inventory | `/applications/:id/inventory` | Category × location matrix with volumes and protection state; inline edit of purpose, source, recipients; combined-identity records highlighted; export |
| DPIA workspace | `/applications/:id/dpia/:dpiaId` | Left rail of sections A–K with completion ticks; question cards pre-filled from scan where possible; evidence attach; comment thread per question; submit button gated on required answers |
| Review mode | same route, DPO view | Side-by-side answers and inventory; request-changes with comments; approve and publish |
| Risk register | `/applications/:id/dpia/:dpiaId/risks` | Editable table: risk, DPDP reference, likelihood × impact grid, treatment, owner, due date, status; recompute button; inherent vs residual summary |
| Report preview | `/applications/:id/dpia/:dpiaId/report` | Rendered HTML preview; download PDF or DOCX; version history |
| Detector management | `/admin/detectors` | Packs and detectors list; create custom detector with live test against sample strings; enable or disable per tier |
| Administration | `/admin/users`, `/admin/settings`, `/admin/webhooks`, `/admin/audit` | Role assignment per application; thresholds and risk bands; webhooks; searchable audit log |

### 10.3 Interaction rules

- Owners see only their applications in every list and dashboard; the role is read from the token and enforced again by the API, the UI only hides.
- Evidence is shown masked with a tooltip explaining the masking; there is no reveal control anywhere in the UI.
- Destructive actions (delete data source, suppress finding, cancel scan) use a confirm dialog that states the consequence in one sentence.
- Findings grid keeps filters and sort in the URL so a reviewer can send a colleague the exact view.
- All times shown in IST with the ISO timestamp on hover.

## 11. Security and privacy of the platform

A tool that holds read credentials to every database in the estate and a map of where the Aadhaar numbers are is itself a high-value target, so it is built to the standard it will assess others against.

### 11.1 Authentication and authorisation

- SSO only, via the corporate IdP (OIDC with PKCE for the SPA, client credentials for service accounts); MFA enforced at the IdP. Two local break-glass accounts exist, disabled by default, with passwords in the vault and every use alerted.
- Roles from section 2.2 are stored in the platform, not in IdP groups, so an owner's scope is per application; group-to-role sync from the IdP is optional.
- Authorisation is enforced three times: in the API dependency, in the service layer, and by PostgreSQL row-level security. The UI only hides.
- API tokens are scoped (read:findings, write:scans and so on), expire by default in 90 days, and are shown once at creation.

### 11.2 Credential handling

- Connector secrets go straight from the create or edit form to the vault; the API holds them in memory for the duration of that request only and logs the vault path, never the value.
- Workers fetch a short-lived lease at job start and drop it at job end; Vault dynamic database credentials are preferred where the target supports them, so the platform never holds a standing password.
- Target database accounts are read-only, have `statement_timeout` set, and are restricted to the schemas listed on the data source; the connection test refuses an account that has write or DDL privileges.

### 11.3 Data minimisation inside the platform

- Sampled values live in the worker process only, are masked by the detector that matched them, and the buffer is cleared per unit of work. There is no debug mode that persists raw values.
- Evidence snippets are capped at three per finding and masked per the rules in section 8.5.
- Reports contain masked evidence only; the DOCX and PDF are watermarked with the DPIA id and generation time.
- Database backups are encrypted; the vault is backed up separately, so a restored platform database contains no usable credential.

### 11.4 Application security

- OWASP ASVS Level 2 as the acceptance bar; the platform goes through the organisation's own VAPT before production and after every major release.
- Dependency and container scanning in CI (pip-audit, npm audit, Trivy); SBOM published per release.
- CSP, HSTS, SameSite cookies, CSRF protection on any cookie-based path; input validated by Pydantic on the API and Zod on the client.
- Rate limiting per token and per IP on the API gateway; scan start is limited per data source to prevent accidental load on a target.
- Worker image contains only the drivers needed; no shell tools beyond what Celery requires; runs as a non-root user with a read-only root filesystem.

### 11.5 Audit and monitoring

- Append-only audit log (section 8.4) for every create, update, state transition, export, credential use and login; shipped to the SIEM through the structured log stream.
- Alerts on: break-glass login, credential fetch outside a scan job, export of more than N findings, repeated authorisation failures, a scan against a data source not scanned before.
- Audit log and findings exports are themselves audited.

### 11.6 Legal basis for the platform's own processing

The platform processes masked fragments of personal data for the purpose of protecting that data, which falls within the Data Fiduciary's own security obligations under S.8(5). The processing is recorded in the organisation's record of processing, the platform has its own entry in the application registry, and it is the first application assessed with its own DPIA.

## 12. Deployment and operations

Everything ships as containers from one repository; Docker Compose runs the full stack on a developer laptop and the same images deploy to Kubernetes on-premise.

### 12.1 Topology

| Environment | Layout |
| --- | --- |
| Development | `docker compose up`: web (Vite dev server), api, worker, redis, postgres, minio, a seeded sample PostgreSQL target with synthetic Indian PII, and a sample Git repo mounted from `fixtures/` |
| UAT | Kubernetes namespace: 1 api pod, 1 worker pod, Redis, PostgreSQL (managed or operator-based), MinIO; ingress with corporate TLS; connected to the IdP test realm |
| Production | Kubernetes namespace: 2 api replicas behind the ingress, 2–4 worker replicas with HPA on queue depth, Redis Sentinel or managed Redis, PostgreSQL 16 primary with streaming replica, object storage; worker pods on nodes with network reach to database subnets, api pods without it |

Network policy: only worker pods may reach target database and Git networks; api pods reach PostgreSQL, Redis, the vault, the IdP and the mail relay; the web tier is static files served by the ingress or nginx.

### 12.2 Repository and CI

- Monorepo: `api/`, `worker/` (shares a Python package `dpia_core` with detectors and connectors), `web/`, `infra/` (Compose, Helm chart, Alembic migrations run as a Job), `fixtures/` (synthetic PII datasets and test repos), `docs/`.
- CI on every pull request: lint, type check (mypy, tsc), unit tests, detector precision suite, container build, Trivy scan, Playwright smoke on the Compose stack.
- Release: semantic version tag builds and signs images (cosign), publishes the Helm chart and SBOM; migrations are forward-only and tested against a copy of UAT data.

### 12.3 Operations

| Area | Practice |
| --- | --- |
| Configuration | Environment variables and a mounted `settings.yaml`; secrets only from the vault or Kubernetes secrets sourced from it |
| Logging | JSON to stdout, collected by the cluster agent and shipped to the SIEM; audit events carry `event_type=audit` for routing |
| Metrics and alerting | Prometheus scrape of `/metrics`: queue depth, scan duration, findings per minute, API latency, worker memory; alerts on stuck jobs (Running with no unit progress for 30 minutes), queue backlog, failed scans |
| Backups | Nightly logical backup plus WAL archiving for PostgreSQL; object store versioning; restore drill quarterly |
| Upgrades | Rolling deploy of api; workers drained of running jobs before replacement (Celery warm shutdown), paused jobs resume on the new version |
| Capacity | One worker pod (4 vCPU, 8 GB) handles roughly 8 concurrent Standard scans; spaCy transformer model adds 2 GB per worker, so Deep profile pods are a separate deployment with higher memory |
| Detector pack updates | Packs ship with releases; custom detectors are exported and imported as YAML for promotion from UAT to production |

## 13. Delivery roadmap

Four phases take version 1 to production in roughly 20 weeks with a team of four (one backend, one frontend, one detection/data engineer, one part-time DPO as product owner); week counts are indicative and should be re-planned once the team is confirmed.

&#91;embedded content: delivery roadmap · 4 phases to v1, 3 gates, extensions after\]

Discovery ships before the DPIA workflow so the pilot application has real findings to assess; each gate is a measurable criterion, not a date.

### 13.1 Acceptance criteria per phase

| Phase | Done when |
| --- | --- |
| Foundation | SSO login works against the IdP test realm; an application and a data source can be created and listed per role; migrations and CI pipeline green; Compose stack runs from a clean clone |
| Discovery core | Git and PostgreSQL connectors scan the fixture repo and database; detector pack v1 scores precision ≥ 0.95 and recall ≥ 0.90 on the synthetic Indian PII fixture; a 500-table schema scans in under 60 minutes; findings explorer supports filter, drawer and review actions; live progress visible |
| DPIA workflow | Questionnaire A–K with pre-fill from inventory; risk engine produces inherent and residual scores matching a hand-computed test case; workflow transitions audited; PDF and DOCX report render; portfolio dashboard shows the pilot application; first DPIA approved and published on the pilot application |
| Hardening | Oracle, MS SQL and MySQL connectors pass the same fixture tests; vault integration and row-level security in place; VAPT report with no high or critical open; UAT sign-off from the privacy office and one application owner; Helm chart deploys to the production cluster |
| Extensions | Scoped after v1 from the backlog in section 3 (items marked L) and the open items in section 14 |

## 14. Open items

Decisions that change the build and should be settled before Phase 1 starts.

- [ ] Product name for the platform (used in UI, repo and report headers)
- [ ] Pilot application and its owner: one internet-facing customer application and one HR or payroll system would exercise both consumer and employee data paths
- [ ] Significant Data Fiduciary status: whether the organisation expects to be notified as an SDF, which fixes DPIA cadence and the DPO-in-India control
- [ ] Vault choice: HashiCorp Vault, CyberArk, or envelope encryption in PostgreSQL for v1 with vault in Phase 3
- [ ] Target database list for Phase 1 beyond PostgreSQL: which of Oracle, MS SQL, MySQL carry the most personal data and should move earlier
- [ ] Languages for the detector dictionaries: which regional name lists (Bengali, Hindi, others) and whether Bengali-script data appears in any target
- [ ] NER model: spaCy `en_core_web_trf` on CPU, or a GPU node for Deep profile scans
- [ ] Report branding and sign-off block: who signs a published DPIA (owner, DPO, CISO)
- [ ] Retention of findings: default 24 months proposed; confirm against the records retention schedule
- [ ] CMDB integration for FR-1.4: which system and whether read access is available
- [ ] Team and start date, to convert the indicative week counts in section 13 into a dated plan
- [ ] Open-source release: whether the detector core (`dpia_core`) is published separately as a reusable library
