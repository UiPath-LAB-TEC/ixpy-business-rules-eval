# Implementation Summary

## Scope

Built `business-rule-ui` as a local FastAPI + React/TypeScript + SQLite app. The app reads immutable `extraction` rows, preserves the legacy `business_rule_eval` scorecard contract, writes structured runs/results/evidence/logs/reviews, and provides dashboard, documents, review, analytics, runs/logs, rules, settings, CSV export, and safe document-serving surfaces.

## Contract Notes

- Source extraction contract observed from examples: `filename`, `document_id`, `document_type_id`, `field_id`, `field`, `is_missing`, `field_value`, `confidence`, `ocr_confidence`, `is_correct`, `row_index`, `column_index`, `page_range`, and `page_count`.
- Example DBs did not include coordinate columns. The evaluator introspects optional coordinate aliases and the synthetic fixture includes `page_number`, `x`, `y`, `width`, and `height`.
- Missing coordinates are handled with deterministic fallback fields: filename, field ID, field, row/column index, raw value, normalized value, and evidence role.
- `extraction` is never updated or deleted.

## Fixture DB

- Path: `tests/fixtures/settlement_fixture.db`
- Document root: `tests/fixtures/docs`
- Synthetic documents: `pass_balanced.pdf`, `fail_balancing.pdf`, `warning_parse.pdf`, `no_rule.pdf`
- Current extraction row count after fixture generation: 57

## Changed Files

- Backend: `backend/app/config.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/app/routes/*`, `backend/app/services/query.py`, `backend/app/models/schemas.py`
- SQL: `backend/app/sql/migrations/001_business_rule_core.sql`, `backend/app/sql/views/001_reporting_views.sql`, `backend/app/sql/seeds/001_rule_definitions.sql`
- Evaluator: `business_rules/settlement_statement.py`
- Scripts: `scripts/create_fixture_db.py`, `scripts/run_migrations.py`, `scripts/run_evaluator.py`
- Frontend: `frontend/src/App.tsx`, `frontend/src/api/*`, `frontend/src/pages/*`, `frontend/src/components/document-viewer/*`, `frontend/src/components/rule-evidence/*`, `frontend/src/styles.css`, `frontend/vite.config.ts`, `frontend/playwright.config.ts`
- Tests: `tests/backend/*`, `tests/integration/*`, `frontend/src/App.test.tsx`, `frontend/e2e/demo.spec.ts`
- Docs/config: `README.md`, `SPEC.md`, `.env.example`, `.gitignore`, `requirements.txt`, `frontend/package.json`, `frontend/package-lock.json`

## Verification Results

- `python scripts/create_fixture_db.py`: created synthetic fixture DB and safe fixture docs.
- `python scripts/run_migrations.py --db tests/fixtures/settlement_fixture.db`: applied `001_business_rule_core.sql`.
- `python scripts/run_evaluator.py --db tests/fixtures/settlement_fixture.db --document-root tests/fixtures/docs`: wrote `run_id=1`.
- `sqlite3 tests/fixtures/settlement_fixture.db 'SELECT COUNT(*) FROM extraction; PRAGMA integrity_check; SELECT COUNT(*), SUM(rule_passed=0) FROM business_rule_eval;'`: `57`, `ok`, `12|4`.
- `pytest -q`: `4 passed`.
- `npm --prefix frontend run type-check`: passed.
- `npm --prefix frontend run test`: `3 passed`.
- `npm --prefix frontend run build`: passed, Vite production build completed with PDF.js worker assets.
- `npm --prefix frontend run e2e`: `1 passed`; dashboard, documents, review, analytics, and runs/logs had no browser console errors, and review note persisted after reload.
- `curl 'http://127.0.0.1:8000/api/documents?status=failed'`: failed document summaries returned controlled JSON with non-inflated rule counts.

## Demo Path

1. `python scripts/create_fixture_db.py`
2. `python scripts/run_migrations.py --db tests/fixtures/settlement_fixture.db`
3. `python scripts/run_evaluator.py --db tests/fixtures/settlement_fixture.db --document-root tests/fixtures/docs`
4. `BUSINESS_RULE_DB=tests/fixtures/settlement_fixture.db BUSINESS_RULE_DOCUMENT_ROOT=tests/fixtures/docs uvicorn backend.app.main:app --reload`
5. `npm --prefix frontend run dev`
6. Open `http://127.0.0.1:5173/dashboard`, open `fail_balancing.pdf`, select `credit_amounts_equal_subtotal_credits`, click an evidence row, save a review note, and reload.

## Known Gaps

- None against `GOAL_ACCEPTANCE.md`.
- Fixture documents are synthetic one-page PDFs, not customer settlement statements.
