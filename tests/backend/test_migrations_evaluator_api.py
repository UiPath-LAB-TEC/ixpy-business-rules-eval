from __future__ import annotations

import csv
from io import StringIO
import json
import sqlite3

from fastapi.testclient import TestClient

from backend.app.db import apply_migrations
from business_rules.settlement_statement import process_all_documents
from tests.conftest import PARENT, make_fixture


def test_migrations_run_on_empty_database(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE extraction (
            filename TEXT NOT NULL,
            document_id TEXT NOT NULL,
            document_type_id TEXT NOT NULL,
            field_id TEXT,
            field TEXT,
            is_missing BOOLEAN,
            field_value TEXT,
            row_index INTEGER DEFAULT -1,
            column_index INTEGER DEFAULT -1
        )
        """
    )
    conn.commit()
    conn.close()

    applied = apply_migrations(db_path)

    with sqlite3.connect(db_path) as check:
        tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "rule_run" in tables
        assert "business_rule_eval_detail" in tables
        assert "business_rule_review" in tables
        assert "business_rule_annotation" in tables
        assert "training_exception_queue" in tables
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert "001_business_rule_core.sql" in applied


def test_review_annotations_recompute_and_statuses_are_supported(tmp_path, monkeypatch):
    db_path = tmp_path / "annotations.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("modern_doc.pdf", "credit_amounts_equal_subtotal_credits", 250, 275, 0),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    reviewed = client.post(
        "/api/reviews/modern_doc.pdf/credit_amounts_equal_subtotal_credits",
        json={"status": "needs_extraction_fix", "root_cause": "subtotal mismatch", "notes": "bad row"},
    ).json()
    assert reviewed["status"] == "needs_extraction_fix"

    annotation = client.post(
        "/api/reviews/modern_doc.pdf/credit_amounts_equal_subtotal_credits/annotations",
        json={
            "detail_id": 102,
            "detail_type": "included_row",
            "evidence_role": "actual_total",
            "source_field_id": "items",
            "source_field": "credit-amount",
            "row_index": 2,
            "column_index": 1,
            "corrected_amount": 250,
            "include_in_rule": True,
            "root_cause": "subtotal mismatch",
            "notes": "correct credit row amount",
        },
    ).json()
    assert annotation["annotation_id"] > 0
    assert annotation["corrected_amount"] == 250

    annotations = client.get("/api/reviews/modern_doc.pdf/credit_amounts_equal_subtotal_credits/annotations").json()
    assert annotations["total"] == 1
    recomputed = client.post("/api/reviews/modern_doc.pdf/credit_amounts_equal_subtotal_credits/recompute").json()
    assert recomputed["original_result"]["actual_total"] == 275
    assert recomputed["corrected_result"]["actual_total"] == 250
    assert recomputed["corrected_result"]["rule_passed"] is True
    assert recomputed["original"]["actual_total"] == 275
    assert recomputed["corrected"]["actual_total"] == 250

    batch = client.post(
        "/api/annotations/modern_doc.pdf/credit_amounts_equal_subtotal_credits",
        json={"annotations": [{"detail_id": 102, "corrected_amount": 250, "include_row": True, "notes": "frontend payload"}]},
    ).json()
    assert batch["total"] == 1
    frontend_recompute = client.post(
        "/api/annotations/modern_doc.pdf/credit_amounts_equal_subtotal_credits/recompute",
        json={"annotations": [{"detail_id": 102, "corrected_amount": 250, "include_row": True, "notes": "frontend payload"}]},
    ).json()
    assert frontend_recompute["corrected"]["actual_total"] == 250

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0] == 9


def test_explanation_includes_root_cause_suggestions(tmp_path, monkeypatch):
    db_path = tmp_path / "suggestions.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN failure_reason TEXT")
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN details TEXT")
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed, failure_reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "modern_doc.pdf",
                "total_credits_equal_subtotal_credits_plus_due_from_buyer",
                300,
                250,
                0,
                "subtotal mismatch",
                '{"skipped_summary_or_rollup_rows": [{"row_index": 2, "amount": "250.00", "description": "Subtotal credits"}]}',
            ),
        )
        conn.execute(
            """
            UPDATE extraction
            SET field_value = NULL, field_unformatted_value = NULL, validated_field_value = NULL, is_missing = 1
            WHERE filename = ? AND field_id = ?
            """,
            ("modern_doc.pdf", "due-from-buyer-amount"),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    explanation = client.get(
        "/api/evaluations/modern_doc.pdf/total_credits_equal_subtotal_credits_plus_due_from_buyer/explanation"
    ).json()

    suggestion_codes = {item["code"] for item in explanation["root_cause_suggestions"]}
    assert "missing_due_from_buyer" in suggestion_codes
    assert "rollup_row_excluded" in suggestion_codes
    assert "subtotal_mismatch" in suggestion_codes
    assert "Missing due-from-buyer row" in explanation["suggested_root_causes"]


def test_eval_explanation_promotes_diagnosis_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "diagnosis.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    diagnosis = {
        "title": "Aggregate adjustment sign may be reversed",
        "message": "The mismatch is consistent with an aggregate adjustment being interpreted with the wrong sign.",
        "confidence": "medium",
        "reason_code": "aggregate_adjustment_sign_conflict",
        "reason_group": "line_item_offset_or_sign",
        "recommended_action": "Verify whether the aggregate adjustment should be added or subtracted in this settlement statement.",
    }
    diagnosis_evidence = {
        "formula": "sum(debit line items) == subtotal debits",
        "expected_total": "339155.75",
        "actual_total": "338250.75",
        "difference": "905.00",
        "absolute_difference": "905.00",
        "matched_rows": [
            {
                "field_id": "items",
                "row_index": 15,
                "description": "Aggregate Adjustment",
                "amount_field": "Debit Amount",
                "amount": "-452.48",
                "why_relevant": "twice the aggregate adjustment is approximately the gap",
            }
        ],
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN failure_reason TEXT")
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN details TEXT")
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed, failure_reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "modern_doc.pdf",
                "debit_amounts_equal_subtotal_debits",
                339155.75,
                338250.75,
                0,
                "line_item_sum_mismatch",
                json.dumps({"diagnosis": diagnosis, "diagnosis_evidence": diagnosis_evidence}),
            ),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    explanation = client.get("/api/evaluations/modern_doc.pdf/debit_amounts_equal_subtotal_debits/explanation").json()

    assert explanation["result"]["root_cause"] == "line_item_sum_mismatch"
    assert explanation["diagnosis"] == diagnosis
    assert explanation["diagnosis_evidence"] == diagnosis_evidence
    assert explanation["details"][0]["metadata"]["diagnosis"] == diagnosis


def test_evaluator_writes_four_rules_and_structured_evidence(tmp_path):
    db_path, doc_root = make_fixture(tmp_path)
    before = _extraction_count(db_path)
    apply_migrations(db_path)

    run_id = process_all_documents(db_path, doc_root)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert _extraction_count(db_path) == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        run = conn.execute("SELECT * FROM rule_run WHERE run_id = ?", (run_id,)).fetchone()
        assert run["status"] == "completed"
        rule_names = {
            row["rule_name"]
            for row in conn.execute("SELECT DISTINCT rule_name FROM business_rule_result WHERE run_id = ?", (run_id,))
        }
        assert rule_names == {
            "debit_amounts_equal_subtotal_debits",
            "credit_amounts_equal_subtotal_credits",
            "total_credits_equal_subtotal_credits_plus_due_from_buyer",
            "total_debits_balance_total_credits",
        }
        failed = conn.execute(
            "SELECT result_id FROM business_rule_result WHERE rule_passed = 0 LIMIT 1"
        ).fetchone()
        detail_types = {
            row["detail_type"]
            for row in conn.execute(
                "SELECT detail_type FROM business_rule_eval_detail WHERE result_id = ?",
                (failed["result_id"],),
            )
        }
        assert {"computed_value", "expected_source", "included_row"}.issubset(detail_types)
        assert conn.execute(
            "SELECT COUNT(*) FROM business_rule_log WHERE level = 'warning' AND event_type = 'numeric_parse_failure'"
        ).fetchone()[0] >= 1
        assert conn.execute(
            "SELECT COUNT(*) FROM business_rule_eval_detail WHERE detail_type = 'no_rule_evaluated'"
        ).fetchone()[0] == 1


def test_evaluator_supports_modern_settlement_schema(tmp_path):
    db_path = tmp_path / "modern.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)

    process_all_documents(db_path, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0] == 9
        assert conn.execute("SELECT COUNT(*) FROM rule_run").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM business_rule_result").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM business_rule_eval").fetchone()[0] == 4
        assert conn.execute(
            "SELECT COUNT(*) FROM business_rule_eval_detail WHERE detail_type = 'included_row'"
        ).fetchone()[0] >= 2


def test_evaluator_falls_back_to_totals_for_line_item_rules_when_subtotals_missing(tmp_path):
    db_path = tmp_path / "missing_subtotals.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE extraction
            SET is_missing = 1, field_value = NULL, field_unformatted_value = NULL, validated_field_value = NULL
            WHERE filename = ? AND field_id IN (?, ?)
            """,
            ("modern_doc.pdf", "subtotal-debits-amount", "subtotal-credits-amount"),
        )
        conn.execute(
            """
            UPDATE extraction
            SET field_value = '250.00', field_unformatted_value = '250.00'
            WHERE filename = ? AND field_id = ?
            """,
            ("modern_doc.pdf", "total-credits-amount"),
        )
        conn.commit()

    process_all_documents(db_path, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        debit_rule = conn.execute(
            """
            SELECT * FROM business_rule_result
            WHERE filename = ? AND rule_name = ?
            """,
            ("modern_doc.pdf", "debit_amounts_equal_subtotal_debits"),
        ).fetchone()
        credit_rule = conn.execute(
            """
            SELECT * FROM business_rule_result
            WHERE filename = ? AND rule_name = ?
            """,
            ("modern_doc.pdf", "credit_amounts_equal_subtotal_credits"),
        ).fetchone()
        total_credits_rollup = conn.execute(
            """
            SELECT * FROM business_rule_result
            WHERE filename = ? AND rule_name = ?
            """,
            ("modern_doc.pdf", "total_credits_equal_subtotal_credits_plus_due_from_buyer"),
        ).fetchone()

        assert debit_rule["expected_total"] == 300
        assert debit_rule["actual_total"] == 300
        assert debit_rule["rule_passed"] == 1
        assert credit_rule["expected_total"] == 250
        assert credit_rule["actual_total"] == 250
        assert credit_rule["rule_passed"] == 1
        assert total_credits_rollup is None


def test_evaluator_uses_due_from_buyer_item_row_when_summary_field_missing(tmp_path):
    db_path = tmp_path / "modern_due_item.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM extraction WHERE filename = ? AND field_id = ?",
            ("modern_doc.pdf", "due-from-buyer-amount"),
        )
        conn.executemany(
            """
            INSERT INTO extraction
                (filename, document_id, document_type_id, field_id, field, is_missing,
                 field_value, row_index, column_index, confidence, ocr_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.9, 0.9)
            """,
            [
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "item-description", 0, "DUE FROM BUYER/BORROWER", 3, 0),
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "credit-amount", 0, "50.00", 3, 1),
            ],
        )
        conn.commit()

    process_all_documents(db_path, tmp_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        total_rule = conn.execute(
            """
            SELECT * FROM business_rule_result
            WHERE filename = ? AND rule_name = ?
            """,
            ("modern_doc.pdf", "total_credits_equal_subtotal_credits_plus_due_from_buyer"),
        ).fetchone()
        credit_rule = conn.execute(
            """
            SELECT * FROM business_rule_result
            WHERE filename = ? AND rule_name = ?
            """,
            ("modern_doc.pdf", "credit_amounts_equal_subtotal_credits"),
        ).fetchone()
        due_source = conn.execute(
            """
            SELECT * FROM business_rule_eval_detail
            WHERE result_id = ? AND detail_type = 'actual_source'
              AND source_field_id = 'items' AND source_field = 'credit-amount'
            """,
            (total_rule["result_id"],),
        ).fetchone()

        assert total_rule["rule_passed"] == 1
        assert total_rule["actual_total"] == 300
        assert credit_rule["rule_passed"] == 1
        assert credit_rule["actual_total"] == 250
        assert due_source["row_index"] == 3
        assert due_source["amount"] == 50


def test_api_reads_pass_fail_from_business_rule_eval_without_rule_run(tmp_path, monkeypatch):
    db_path = tmp_path / "eval_only.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN failure_reason TEXT")
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN details TEXT")
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed, failure_reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "modern_doc.pdf",
                "credit_amounts_equal_subtotal_credits",
                250,
                275,
                0,
                "subtotal mismatch",
                '{"absolute_difference": "25.00", "difference": "25.00"}',
            ),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["evaluated_documents"] == 1
    assert dashboard["failed_evaluations"] == 1
    assert dashboard["recent_documents"][0]["filename"] == "modern_doc.pdf"
    docs = client.get("/api/documents", params={"status": "failed"}).json()
    assert docs["total"] == 1
    detail = client.get("/api/documents/modern_doc.pdf").json()
    assert detail["rules"][0]["rule_name"] == "credit_amounts_equal_subtotal_credits"
    assert detail["rules"][0]["rule_passed"] == 0
    explanation = client.get("/api/evaluations/modern_doc.pdf/credit_amounts_equal_subtotal_credits/explanation").json()
    assert explanation["result"]["absolute_difference"] == 25
    assert explanation["details"][0]["detail_type"] == "computed_value"
    detail_types = {detail["detail_type"] for detail in explanation["details"]}
    assert {"expected_source", "included_row"}.issubset(detail_types)
    assert any(detail["source_field_id"] == "subtotal-credits-amount" for detail in explanation["details"])
    assert any(
        detail["source_field_id"] == "items" and detail["source_field"] == "credit-amount" and detail["amount"] == 250
        for detail in explanation["details"]
    )


def test_document_rule_filter_status_applies_to_that_rule(tmp_path, monkeypatch):
    db_path = tmp_path / "rule_status_filter.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("credit_failed.pdf", "credit_amounts_equal_subtotal_credits", 250, 275, 0),
                ("credit_failed.pdf", "debit_amounts_equal_subtotal_debits", 300, 300, 1),
                ("credit_passed_other_failed.pdf", "credit_amounts_equal_subtotal_credits", 250, 250, 1),
                ("credit_passed_other_failed.pdf", "debit_amounts_equal_subtotal_debits", 300, 325, 0),
                ("only_debit_failed.pdf", "debit_amounts_equal_subtotal_debits", 300, 325, 0),
            ],
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    failed_credit = client.get(
        "/api/documents",
        params={"status": "failed", "rule": "credit_amounts_equal_subtotal_credits", "sort": "filename", "direction": "asc"},
    ).json()
    passed_credit = client.get(
        "/api/documents",
        params={"status": "passed", "rule": "credit_amounts_equal_subtotal_credits", "sort": "filename", "direction": "asc"},
    ).json()

    assert [item["filename"] for item in failed_credit["items"]] == ["credit_failed.pdf"]
    assert [item["filename"] for item in passed_credit["items"]] == ["credit_passed_other_failed.pdf"]


def test_documents_can_be_filtered_by_review_status(tmp_path, monkeypatch):
    db_path = tmp_path / "review_status_filter.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("reviewed_doc.pdf", "credit_amounts_equal_subtotal_credits", 250, 275, 0),
                ("ignored_doc.pdf", "credit_amounts_equal_subtotal_credits", 250, 275, 0),
                ("unreviewed_doc.pdf", "credit_amounts_equal_subtotal_credits", 250, 275, 0),
            ],
        )
        conn.executemany(
            """
            INSERT INTO business_rule_review
                (filename, rule_name, status, root_cause, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("reviewed_doc.pdf", "credit_amounts_equal_subtotal_credits", "reviewed", "checked", ""),
                ("ignored_doc.pdf", "credit_amounts_equal_subtotal_credits", "ignored", "not relevant", ""),
            ],
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    reviewed = client.get(
        "/api/documents",
        params={"status": "failed", "review_status": "reviewed", "sort": "filename", "direction": "asc"},
    ).json()
    unreviewed = client.get(
        "/api/documents",
        params={"status": "failed", "review_status": "unreviewed", "sort": "filename", "direction": "asc"},
    ).json()

    assert [item["filename"] for item in reviewed["items"]] == ["reviewed_doc.pdf"]
    assert [item["filename"] for item in unreviewed["items"]] == ["unreviewed_doc.pdf"]


def test_eval_analytics_uses_business_rule_eval_without_rule_run(tmp_path, monkeypatch):
    db_path = tmp_path / "eval_analytics.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    diagnosis = {
        "title": "Amount appears to be assigned to the wrong column",
        "confidence": "high",
        "reason_code": "amount_extracted_in_wrong_column",
        "reason_group": "line_item_column_assignment",
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN failure_reason TEXT")
        conn.execute("ALTER TABLE business_rule_eval ADD COLUMN details TEXT")
        conn.execute(
            """
            INSERT INTO extraction
                (filename, document_id, document_type_id, field_id, field, is_missing,
                 field_value, row_index, column_index, confidence, ocr_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("other_doc.pdf", "doc-other", "settlement_statement", "total-credits-amount", "total-credits-amount", 0, "300.00", 0, 0, 0.75, 0.8),
        )
        conn.executemany(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed, failure_reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "modern_doc.pdf",
                    "credit_amounts_equal_subtotal_credits",
                    250,
                    275,
                    0,
                    "line_item_sum_mismatch",
                    json.dumps({"diagnosis": diagnosis}),
                ),
                (
                    "other_doc.pdf",
                    "credit_amounts_equal_subtotal_credits",
                    300,
                    300,
                    1,
                    None,
                    "{}",
                ),
                (
                    "other_doc.pdf",
                    "debit_amounts_equal_subtotal_debits",
                    300,
                    325,
                    0,
                    "line_item_sum_mismatch",
                    "{}",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO business_rule_review
                (filename, rule_name, status, root_cause, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("modern_doc.pdf", "credit_amounts_equal_subtotal_credits", "reviewed", "wrong column", ""),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    analytics = client.get("/api/analytics").json()

    assert analytics["run_id"] is None
    assert analytics["summary"]["total_evaluations"] == 3
    assert analytics["summary"]["failed_evaluations"] == 2
    assert analytics["summary"]["pass_rate"] == 33.33
    assert analytics["rule_pass_rates"]
    assert analytics["largest_differences"][0]["filename"] in {"modern_doc.pdf", "other_doc.pdf"}
    assert analytics["root_cause_counts"]
    assert analytics["diagnosis_counts"][0]["reason_code"] == "amount_extracted_in_wrong_column"
    assert any(row["status"] == "reviewed" for row in analytics["review_status_counts"])
    assert analytics["confidence"]["available"] is True
    assert analytics["field_confidence"]


def test_api_synthesizes_evidence_when_structured_details_are_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "missing_details.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        run_id = conn.execute(
            """
            INSERT INTO rule_run (evaluator_name, status, document_count, result_count)
            VALUES ('settlement_statement', 'completed', 1, 1)
            """
        ).lastrowid
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("modern_doc.pdf", "credit_amounts_equal_subtotal_credits", 250, 250, 1),
        )
        conn.execute(
            """
            INSERT INTO business_rule_result
                (run_id, filename, rule_name, expected_total, actual_total, difference,
                 absolute_difference, tolerance, rule_passed, root_cause, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "modern_doc.pdf",
                "credit_amounts_equal_subtotal_credits",
                250,
                250,
                0,
                0,
                0.01,
                1,
                "unknown",
                "Rule passed.",
            ),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    explanation = client.get("/api/evaluations/modern_doc.pdf/credit_amounts_equal_subtotal_credits/explanation").json()

    detail_types = {detail["detail_type"] for detail in explanation["details"]}
    assert {"computed_value", "expected_source", "included_row"}.issubset(detail_types)
    assert any(
        detail["source_field_id"] == "items" and detail["source_field"] == "credit-amount" and detail["amount"] == 250
        for detail in explanation["details"]
    )


def test_api_eval_fallback_surfaces_due_from_buyer_item_row(tmp_path, monkeypatch):
    db_path = tmp_path / "eval_due_item.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM extraction WHERE filename = ? AND field_id = ?", ("modern_doc.pdf", "due-from-buyer-amount"))
        conn.executemany(
            """
            INSERT INTO extraction
                (filename, document_id, document_type_id, field_id, field, is_missing,
                 field_value, row_index, column_index, confidence, ocr_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.9, 0.9)
            """,
            [
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "item-description", 0, "DUE FROM BUYER/BORROWER", 3, 0),
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "credit-amount", 0, "50.00", 3, 1),
            ],
        )
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("modern_doc.pdf", "total_credits_equal_subtotal_credits_plus_due_from_buyer", 300, 250, 0),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    explanation = client.get(
        "/api/evaluations/modern_doc.pdf/total_credits_equal_subtotal_credits_plus_due_from_buyer/explanation"
    ).json()

    assert any(
        detail["detail_type"] == "actual_source"
        and detail["source_field_id"] == "items"
        and detail["source_field"] == "credit-amount"
        and detail["amount"] == 50
        for detail in explanation["details"]
    )


def test_api_eval_fallback_surfaces_borrower_regular_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "eval_borrower_fields.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO extraction
                (filename, document_id, document_type_id, field_id, field, is_missing,
                 field_value, row_index, column_index, confidence, ocr_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.9, 0.9)
            """,
            [
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "due-from-borrower", "due-from-borrower", 0, "50.00", 0, 5),
                ("modern_doc.pdf", "doc-modern", "settlement_statement", "due-to-borrower", "due-to-borrower", 0, "25.00", 0, 6),
            ],
        )
        conn.executemany(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("modern_doc.pdf", "total_credits_equal_subtotal_credits_plus_due_from_borrower", 300, 300, 1),
                ("modern_doc.pdf", "total_debits_equal_subtotal_debits_plus_due_to_borrower", 325, 325, 1),
                ("modern_doc.pdf", "borrower_balance_fields_are_mutually_exclusive", 1, 0, 0),
            ],
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    credit_explanation = client.get(
        "/api/evaluations/modern_doc.pdf/total_credits_equal_subtotal_credits_plus_due_from_borrower/explanation"
    ).json()
    debit_explanation = client.get(
        "/api/evaluations/modern_doc.pdf/total_debits_equal_subtotal_debits_plus_due_to_borrower/explanation"
    ).json()
    exclusivity_explanation = client.get(
        "/api/evaluations/modern_doc.pdf/borrower_balance_fields_are_mutually_exclusive/explanation"
    ).json()

    assert any(
        detail["detail_type"] == "actual_source"
        and detail["source_field_id"] == "due-from-borrower"
        and detail["amount"] == 50
        for detail in credit_explanation["details"]
    )
    assert any(
        detail["detail_type"] == "actual_source"
        and detail["source_field_id"] == "due-to-borrower"
        and detail["amount"] == 25
        for detail in debit_explanation["details"]
    )
    exclusivity_fields = {
        detail["source_field_id"]
        for detail in exclusivity_explanation["details"]
        if detail["detail_type"] == "actual_source"
    }
    assert {"due-from-borrower", "due-to-borrower"}.issubset(exclusivity_fields)


def test_total_debits_balance_explanation_includes_debit_item_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "eval_debit_rows.db"
    _create_modern_schema_fixture(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("modern_doc.pdf", "total_debits_balance_total_credits", 300, 250, 0),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    explanation = client.get(
        "/api/evaluations/modern_doc.pdf/total_debits_balance_total_credits/explanation"
    ).json()

    assert any(
        detail["detail_type"] == "included_row"
        and detail["source_field_id"] == "items"
        and detail["source_field"] == "debit-amount"
        and detail["amount"] == 300
        for detail in explanation["details"]
    )


def test_api_allows_local_vite_fallback_ports(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.options(
        "/api/documents/fail_balancing.pdf",
        headers={
            "Origin": "http://127.0.0.1:5175",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5175"


def test_legacy_scorecard_sql_and_api_payloads(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    with sqlite3.connect(db_path) as conn:
        conn.executescript((PARENT / "sql_examples" / "ss-vibe-scores.sql").read_text())

    from backend.app.main import create_app

    client = TestClient(create_app())
    assert client.get("/api/health").json()["status"] == "ok"
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_documents"] == 4
    assert dashboard["failed_evaluations"] > 0
    assert dashboard["warning_count"] > 0
    docs = client.get("/api/documents", params={"status": "failed", "sort": "largest_absolute_difference"}).json()
    assert docs["total"] >= 1
    assert docs["items"][0]["rules_failed"] >= 1
    detail = client.get("/api/documents/fail_balancing.pdf").json()
    failed_rule = next(rule for rule in detail["rules"] if rule["rule_name"] == "credit_amounts_equal_subtotal_credits")
    explanation = client.get(f"/api/evaluations/fail_balancing.pdf/{failed_rule['rule_name']}/explanation").json()
    assert explanation["result"]["expected_total"] is not None
    assert any(row["detail_type"] == "included_row" for row in explanation["details"])
    assert any(row["bbox"] for row in explanation["details"] if row["detail_type"] in {"included_row", "expected_source"})
    review = client.post(
        f"/api/reviews/fail_balancing.pdf/{failed_rule['rule_name']}",
        json={"status": "reviewed", "root_cause": "extraction mismatch", "notes": "checked fixture evidence"},
    ).json()
    assert review["notes"] == "checked fixture evidence"
    reloaded = client.get(f"/api/reviews/fail_balancing.pdf/{failed_rule['rule_name']}").json()
    assert reloaded["status"] == "reviewed"
    analytics = client.get("/api/analytics").json()
    assert analytics["rule_pass_rates"]
    assert analytics["warning_frequency"]
    logs = client.get("/api/logs").json()
    assert logs["total"] > 0
    csv_text = client.get("/api/exports/failed-rules.csv").text
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert rows
    assert {"filename", "rule_name", "expected_total", "actual_total", "difference", "root_cause", "warning_count"}.issubset(rows[0])
    missing = client.get("/api/documents/missing.pdf")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "document_not_found"


def test_document_file_serving_finds_nested_safe_document(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    nested_dir = doc_root / "nested"
    nested_dir.mkdir()
    original = doc_root / "fail_balancing.pdf"
    nested = nested_dir / "fail_balancing.pdf"
    nested.write_bytes(original.read_bytes())
    original.unlink()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.get("/api/documents/fail_balancing.pdf/file")

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def test_document_can_be_copied_to_training_exceptions(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/documents/fail_balancing.pdf/training-exception")

    assert response.status_code == 200
    payload = response.json()
    copied = doc_root / "exceptions" / "fail_balancing.pdf"
    assert copied.exists()
    assert copied.read_bytes().startswith(b"%PDF")
    assert payload["filename"] == "fail_balancing.pdf"
    assert payload["exception_path"] == str(copied)
    assert payload["already_exists"] is False

    second = client.post("/api/documents/fail_balancing.pdf/training-exception")

    assert second.status_code == 200
    assert second.json()["already_exists"] is True


def test_document_can_be_archived_as_bad_training_data(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/documents/fail_balancing.pdf/archive",
        params={"rule_name": "credit_amounts_equal_subtotal_credits"},
    )

    assert response.status_code == 200
    payload = response.json()
    archived = doc_root / "archive" / "fail_balancing.pdf"
    assert payload["filename"] == "fail_balancing.pdf"
    assert payload["rule_name"] == "credit_amounts_equal_subtotal_credits"
    assert payload["archive_path"] == str(archived)
    assert archived.exists()
    assert archived.read_bytes().startswith(b"%PDF")
    assert not (doc_root / "fail_balancing.pdf").exists()

    review = client.get("/api/reviews/fail_balancing.pdf/credit_amounts_equal_subtotal_credits").json()
    assert review["status"] == "archived"
    assert review["root_cause"] == "bad training data"


def _extraction_count(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM extraction").fetchone()[0]


def _create_modern_schema_fixture(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE extraction (
            filename TEXT NOT NULL,
            document_id TEXT NOT NULL,
            document_type_id TEXT NOT NULL,
            field_id TEXT,
            field TEXT,
            is_missing BOOLEAN,
            field_value TEXT,
            field_unformatted_value TEXT,
            validated_field_value TEXT,
            is_correct BOOLEAN,
            confidence REAL,
            ocr_confidence REAL,
            operator_confirmed BOOLEAN,
            row_index INTEGER DEFAULT -1,
            column_index INTEGER DEFAULT -1,
            page_range TEXT,
            page_count INTEGER,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (filename, field_id, field, row_index, column_index)
        )
        """
    )
    rows = [
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "subtotal-debits-amount", "subtotal-debits-amount", 0, "300.00", 0, 0),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "subtotal-credits-amount", "subtotal-credits-amount", 0, "250.00", 0, 1),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "total-debits-amount", "total-debits-amount", 0, "300.00", 0, 2),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "total-credits-amount", "total-credits-amount", 0, "300.00", 0, 3),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "due-from-buyer-amount", "due-from-buyer-amount", 0, "50.00", 0, 4),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "item-description", 0, "Debit one", 1, 0),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "debit-amount", 0, "300.00", 1, 1),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "item-description", 0, "Credit one", 2, 0),
        ("modern_doc.pdf", "doc-modern", "settlement_statement", "items", "credit-amount", 0, "250.00", 2, 1),
    ]
    conn.executemany(
        """
        INSERT INTO extraction
            (filename, document_id, document_type_id, field_id, field, is_missing,
             field_value, row_index, column_index, confidence, ocr_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.9, 0.9)
        """,
        rows,
    )
    conn.commit()
    conn.close()
