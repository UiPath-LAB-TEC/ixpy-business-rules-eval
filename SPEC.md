# Business Rule Failure Analysis UI

This implementation follows the repository-level `SPEC.md` and goal files. It is a local-first FastAPI, React/TypeScript, and SQLite application for settlement-statement business-rule review.

## Contract

- SQLite is the system of record.
- `extraction` rows are read-only.
- `business_rule_eval` keeps the legacy scorecard columns: `filename`, `rule_name`, `expected_total`, `actual_total`, `rule_passed`.
- Structured run, result, detail, log, document, and review records explain failed rules without requiring raw log inspection.
- Coordinates are optional. When absent, evidence falls back to filename, field ID, field, row/column index, raw value, normalized value, and evidence role.

