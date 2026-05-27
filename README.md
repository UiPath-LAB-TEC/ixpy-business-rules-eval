# business-rule-ui

Local FastAPI + React/TypeScript + SQLite app for diagnosing failed settlement-statement business rules.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend install
```

## Fixture Demo

```bash
. .venv/bin/activate
python scripts/create_fixture_db.py
python scripts/run_migrations.py --db tests/fixtures/settlement_fixture.db
python scripts/run_evaluator.py --db tests/fixtures/settlement_fixture.db --document-root tests/fixtures/docs
BUSINESS_RULE_DB=tests/fixtures/settlement_fixture.db BUSINESS_RULE_DOCUMENT_ROOT=tests/fixtures/docs uvicorn backend.app.main:app --reload
```

In another terminal:

```bash
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173/dashboard`, filter failed documents, open `fail_balancing.pdf`, select a failed rule, click an evidence row, add a note, and reload the review page.

## Configuration

- `BUSINESS_RULE_DB`: SQLite database path.
- `BUSINESS_RULE_DOCUMENT_ROOT`: root directory for safe document serving.
- `BUSINESS_RULE_PAGE_SIZE`: default API pagination size.
- `VITE_API_BASE_URL`: frontend API base URL.

No cloud services, external databases, remote storage, telemetry, or internet access are required at runtime.

## Backend

```bash
. .venv/bin/activate
python scripts/run_migrations.py --db tests/fixtures/settlement_fixture.db
python scripts/run_evaluator.py --db tests/fixtures/settlement_fixture.db
uvicorn backend.app.main:app --reload
```

Important endpoints:

- `GET /api/health`
- `GET /api/runs`
- `GET /api/dashboard`
- `GET /api/documents`
- `GET /api/documents/{filename}`
- `GET /api/evaluations/{filename}`
- `GET /api/evaluations/{filename}/{rule_name}/explanation`
- `GET /api/logs`
- `GET /api/analytics`
- `GET|POST /api/reviews/{filename}/{rule_name}`
- `GET /api/exports/failed-rules.csv`

## Frontend

```bash
npm --prefix frontend run dev
npm --prefix frontend run type-check
npm --prefix frontend run test
npm --prefix frontend run build
```

Pages:

- `/dashboard`
- `/documents`
- `/review/:filename`
- `/analytics`
- `/runs`

## Tests

```bash
. .venv/bin/activate
pytest
npm --prefix frontend run type-check
npm --prefix frontend run test
npm --prefix frontend run build
```

The backend tests create synthetic fixture data and verify migrations, evaluator traces, legacy scorecard SQL compatibility, controlled JSON responses, CSV export, extraction row counts, and review persistence.

