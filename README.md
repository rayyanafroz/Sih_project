# AICTE VerifyAI

Evidence-first AI pre-scrutiny for AICTE Extension of Approval (EoA) applications, built for Smart India
Hackathon 2026 (SIH26261).

The system reads uploaded documents (PDF text layer or OCR), extracts fields together with their page location,
and checks them against configurable rules, simulated AICTE records and simulated issuing-authority registries.
Every finding is shown with its evidence. **AI finds and organises the evidence; the authorised officer makes the
decision.** Nothing in the system approves or rejects an application on its own.

> All institutions, documents and records are synthetic, and every external source is a clearly labelled
> simulation. No real government system is accessed.

## Quick start

```bash
./run.sh --reset      # first run: installs dependencies, seeds demo data, serves http://127.0.0.1:8000
./run.sh              # later runs (keeps the current database)
./run.sh --dev        # development: API on :8000 + Vite hot reload on http://localhost:5173
```

Requirements: Python 3.11+, Node 20+, and **Tesseract OCR** for scanned documents
(`sudo pacman -S tesseract tesseract-data-eng` · `sudo apt install tesseract-ocr` · `brew install tesseract`).
Without Tesseract the app still runs; scanned files are flagged for manual review instead of being read.

| Account | Role | Can |
|---|---|---|
| `scrutiny@verifyai.demo` | Scrutiny Officer | create applications, upload, run pre-scrutiny, act on findings, record an outcome |
| `verification@verifyai.demo` | Verification Officer | refresh and re-run source verification, record manual confirmation |
| `admin@verifyai.demo` | Administrator | edit rules, thresholds, categories and verification-source modes; see the global audit log |

Password for all demo accounts: `demo1234`.

## Try it

1. Sign in as the Scrutiny Officer and open **EoA-2026-4821** (a draft with no documents).
2. On the **Documents** tab, upload the files in `backend/demo_data/EoA-2026-4821/` (all except `manifest.json`).
3. Click **Run AI pre-scrutiny**, then review the findings. Each shows the highlighted source on the page,
   the rule and version that raised it, and a recommended next step.
4. Act on a finding with a note, check the **Verification** tab, then sign in as the Verification Officer to
   refresh a pending source or record a manual confirmation.
5. Sign in as the Administrator, change a rule on **Rules & Settings**, and re-run. Results use the new rule version.
6. Record an outcome as the Scrutiny Officer and review the **Audit trail**.

`./run.sh --reset` restores the starting state at any time.

## What's inside

```
backend/   FastAPI + SQLAlchemy (SQLite by default; set VERIFYAI_DATABASE_URL for PostgreSQL)
  app/pipeline/      text layer / OCR → classification → field extraction with bounding boxes → page rendering
  app/engines/       check library and rules runner; rules themselves live in the database
  app/verification/  issuing-authority verification engine (simulated registries, six statuses)
  app/records/       adapter for AICTE institutional records (simulated approved intake, payment ledger)
  app/demo/          synthetic dataset, document generator, demo seeding
  seed/              rules.json and document_types.json: the initial configuration
  demo_data/         generated synthetic documents, with manifest.json listing expected values
  tests/             API end-to-end journey and unit tests
frontend/  Vite + React + TypeScript
```

## Configurable requirements

Requirements are configuration, not code. On **Rules & Settings** the Administrator can enable or disable any
rule and change its severity, thresholds (for example the expiry warning window or the name-similarity
threshold), applicable application categories and regulatory reference. New required-document rules can be added.
Every save creates a new rule version with a recorded reason, every validation result stores the rule version it
used, and every change is audited. The evaluation date for expiry checks and the mode of each verification source
(online, asynchronous, unavailable) are set on the same page.

## Safeguards

- Anomaly findings are worded as potential anomalies and state that they are not proof; nothing is labelled forged.
- Differences against records are worded as needing verification and note that an innocent explanation is possible.
- Only a Scrutiny Officer can record an outcome, with a written reason; recommending approval while critical
  findings are open requires explicit acknowledgement.
- Role-based access is enforced on the server; sign-ins, document views, rule changes, verification attempts and
  officer actions are written to an audit trail.

## Limitations

- Extraction uses keyword classification and pattern templates, tuned on the synthetic documents. Unfamiliar layouts
  would need more templates or an LLM-assisted extractor.
- Issuing-authority and AICTE records are simulated behind adapter interfaces, so real integrations can replace them.
- Infrastructure review checks evidence completeness and certificate figures; it does not analyse photographs.
- Passwords are hashed and sessions use signed tokens, but encryption at rest and in transit is left to deployment.

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q
```

The end-to-end test uploads the synthetic EoA-2026-4821 documents through the API and runs pre-scrutiny. It asserts
that exactly the seeded issues are found and that field extraction is at least 95% accurate on the synthetic set
(currently 100%). It also covers verification statuses, officer actions, rectification (replace a document and
re-run), rule versioning, role permissions and the audit trail.

## Configuration

Environment variables (or `backend/.env`), all prefixed `VERIFYAI_`: `DATABASE_URL`, `STORAGE_DIR`, `SECRET_KEY`
(a random key is generated into `backend/data/` if unset), `STEP_DELAY` (progress-screen pacing, default 0.6 s),
`DEMO_MODE` (shows demo accounts and the demo-documents shortcut; turn off for any real deployment) and `TESSERACT_CMD`.
