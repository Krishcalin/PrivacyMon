# PrivacyMon

PrivacyMon is a self-hosted platform that discovers personal data inside
custom-developed applications and turns the findings into a Data Protection
Impact Assessment (DPIA) mapped to India's **Digital Personal Data Protection
(DPDP) Act, 2023**. It scans application source code and live databases, scores
each finding for confidence and sensitivity, and produces a per-application DPIA
report plus a portfolio view of privacy risk.

See [`docs/SRS.md`](docs/SRS.md) for the full software requirements and
architecture, and [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) for the phased
delivery plan and current status.

## Why

A Data Fiduciary must know what personal data it processes before it can meet
any DPDP obligation (notice and consent, security safeguards, breach reporting,
Significant Data Fiduciary duties). PrivacyMon answers three questions for every
in-house application: **what** personal data it holds, **where** it sits (table,
column, file), and whether it is handled in line with the Act.

## Repository layout (monorepo)

```
PrivacyMon/
├── dpia_core/        # Dependency-free detection + risk + DPDP-control library
│   ├── detectors/    #   validators, structured + dictionary detectors, pack
│   ├── engine.py     #   per-column aggregation, confidence, co-occurrence
│   ├── risk.py       #   inherent / residual risk engine (SRS 5.3)
│   └── controls.py   #   DPDP Act 2023 control library + DPIA questionnaire
├── api/              # FastAPI backend (SRS section 9)
├── worker/           # Celery scan workers + connectors   (next increment)
├── web/              # React 18 + TypeScript SPA          (next increment)
├── infra/            # docker-compose dev stack, Helm      (scaffolding)
├── fixtures/         # synthetic Indian PII + sample repo
├── tests/            # pytest suite (detectors, risk, API, precision)
└── docs/             # SRS, build plan
```

`dpia_core` is intentionally pure Python with no heavy dependencies, so it is
shared by the API and the scan workers and can be published as a standalone
library (SRS section 14).

## What works today (Phase 1 increment)

- **Indian PII detection** for 25 categories (Aadhaar with Verhoeff, PAN, GSTIN
  with mod-36 and embedded-PAN checks, payment card with Luhn, UPI, IFSC,
  driving licence, voter ID, passport, mobile, email, PIN, vehicle, EPF UAN,
  DOB, plus dictionary/NER categories: name, address, gender, health,
  caste/religion, children's data, and biometric/photo by column metadata).
- **Confidence model** `C = min(1, B + K_ctx + H·0.3 − N_ctx)` with the SRS
  base scores, positive/negative column-name context, hit rate, and the
  Likely / Needs-review / Hidden bands (SRS 4.4).
- **Protection-state heuristics** (plain / hashed / encrypted / tokenised) and
  **co-occurrence** uplift for combined-identity records (SRS 4.3, 4.5).
- **Evidence masking** at detection time; raw values never leave memory (SRS 8.5).
- **DPDP Act 2023 control library** and the A–K DPIA questionnaire (SRS 5.1, 5.2).
- **Risk engine**: inherent and residual scoring with exposure multipliers and
  control-effectiveness (SRS 5.3).
- **FastAPI endpoints**: health, version, controls, questionnaire, detector
  listing and a detector-test endpoint, all backed by `dpia_core`.
- **Precision suite** on a synthetic Indian PII fixture (SRS acceptance 13.1).

## Quickstart

```bash
# From the repo root
python -m pip install -r requirements-dev.txt    # or: pip install fastapi pydantic pytest httpx

# Run the test suite (detectors, confidence, risk, controls, API, precision)
python -m pytest

# Run the API locally
python -m uvicorn api.app.main:app --reload
# then open http://127.0.0.1:8000/api/v1/docs
```

Try the detector-test endpoint:

```bash
curl -s http://127.0.0.1:8000/api/v1/detectors/test \
  -H 'content-type: application/json' \
  -d '{"samples":["2341 2341 2340"],"column_name":"aadhaar_number"}'
```

## Safety and privacy of the platform

PrivacyMon reads from target systems and never writes to them. Database accounts
are read-only, row sampling is capped, sampled values live only in worker memory,
and evidence is masked before storage. The platform is designed to the standard
it assesses others against (SRS section 11).

## License

MIT — see [`LICENSE`](LICENSE).
