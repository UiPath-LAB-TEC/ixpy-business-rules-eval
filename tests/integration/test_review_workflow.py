from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.db import apply_migrations
from business_rules.settlement_statement import process_all_documents
from tests.conftest import make_fixture


def test_dashboard_to_failed_rule_to_evidence_to_persisted_note(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    from backend.app.main import create_app

    client = TestClient(create_app())
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["failed_evaluations"] > 0
    docs = client.get("/api/documents", params={"status": "failed"}).json()
    filename = docs["items"][0]["filename"]
    detail = client.get(f"/api/documents/{filename}").json()
    failed_rule = next(rule for rule in detail["rules"] if rule["rule_passed"] == 0)
    explanation = client.get(f"/api/evaluations/{filename}/{failed_rule['rule_name']}/explanation").json()
    evidence = [row for row in explanation["details"] if row["detail_type"] in {"included_row", "expected_source", "actual_source"}]
    assert evidence
    assert evidence[0]["filename"] == filename
    saved = client.post(
        f"/api/reviews/{filename}/{failed_rule['rule_name']}",
        json={"status": "in_review", "root_cause": "duplicate/rollup issue", "notes": "integration note"},
    ).json()
    assert saved["notes"] == "integration note"
    reloaded = client.get(f"/api/reviews/{filename}/{failed_rule['rule_name']}").json()
    assert reloaded["notes"] == "integration note"


def test_dashboard_sorting_and_training_exception_batch_workflow(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    from backend.app.main import create_app

    client = TestClient(create_app())
    docs = client.get("/api/documents", params={"status": "failed", "sort": "highest_value"}).json()
    assert docs["total"] >= 1
    assert docs["items"][0]["validation_value_score"] >= docs["items"][-1]["validation_value_score"]
    assert docs["items"][0]["largest_absolute_difference"] is not None
    assert "recurring_root_cause_count" in docs["items"][0]
    assert "missing_evidence_score" in docs["items"][0]

    filename = docs["items"][0]["filename"]
    detail = client.get(f"/api/documents/{filename}").json()
    failed_rule = next(rule for rule in detail["rules"] if rule["rule_passed"] == 0)
    saved = client.post(
        f"/api/reviews/{filename}/{failed_rule['rule_name']}",
        json={"status": "added_to_training", "root_cause": "parse failure", "notes": "queue for dataset"},
    ).json()
    assert saved["status"] == "added_to_training"

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["unreviewed_failed_documents"] >= 0
    assert dashboard["added_to_training_documents"] >= 1
    assert dashboard["ignored_documents"] >= 0
    assert dashboard["reviewed_documents"] >= 0
    assert dashboard["top_recurring_root_causes"]

    queued = client.get("/api/documents/training-exceptions").json()
    assert queued["total"] >= 1
    queue_item = next(item for item in queued["items"] if item["filename"] == filename)
    assert queue_item["rule_name"] == failed_rule["rule_name"]
    assert queue_item["root_cause"] == "parse failure"

    frontend_queue = client.get("/api/training-exceptions").json()
    assert any(item["filename"] == filename and item["review_status"] == "added_to_training" for item in frontend_queue["items"])

    exported = client.post("/api/training-exceptions/export").json()
    assert exported["total"] >= 1
    assert exported["exported_count"] >= 1
    copied = doc_root / "exceptions" / filename
    manifest = doc_root / "exceptions" / "training_exceptions_manifest.csv"
    assert copied.exists()
    assert manifest.exists()
    assert {"filename", "rule", "root_cause", "notes", "expected_total", "actual_total", "reviewer_status", "copied_path", "already_present"}.issubset(
        set(exported["manifest"][0])
    )

    removed = client.delete(f"/api/training-exceptions/{filename}", params={"rule_name": failed_rule["rule_name"]}).json()
    assert removed["removed"] == 1


def test_highest_value_sort_combines_recurring_missing_and_confidence_signals(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    with _connect(db_path) as conn:
        run_id = conn.execute("SELECT run_id FROM rule_run ORDER BY run_id DESC LIMIT 1").fetchone()[0]
        _insert_triage_document(conn, run_id, "triage_high_difference.pdf", 0, 50, "one-off mismatch", 0.99)
        _insert_triage_document(conn, run_id, "triage_recurring_a.pdf", 0, 10, "recurring pattern", 0.99)
        _insert_triage_document(conn, run_id, "triage_recurring_b.pdf", 0, 8, "recurring pattern", 0.99)
        _insert_triage_document(conn, run_id, "triage_missing_evidence.pdf", None, 5, "missing source", 0.99)
        _insert_triage_document(conn, run_id, "triage_low_confidence.pdf", 0, 15, "low confidence source", 0.40)

    from backend.app.main import create_app

    client = TestClient(create_app())
    docs = client.get("/api/documents", params={"status": "failed", "search": "triage"}).json()

    assert [item["filename"] for item in docs["items"]] == [
        "triage_recurring_a.pdf",
        "triage_recurring_b.pdf",
        "triage_missing_evidence.pdf",
        "triage_low_confidence.pdf",
        "triage_high_difference.pdf",
    ]
    assert docs["items"][0]["validation_value_score"] > docs["items"][4]["validation_value_score"]
    assert docs["items"][2]["missing_evidence_score"] == 1
    assert docs["items"][3]["avg_confidence"] == 0.40


def test_existing_training_exception_post_refreshes_queue_metadata(tmp_path, monkeypatch):
    db_path, doc_root = make_fixture(tmp_path)
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(doc_root))
    apply_migrations(db_path)
    process_all_documents(db_path, doc_root)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/documents/fail_balancing.pdf/training-exception",
        params={"rule_name": "total_debits_balance_total_credits"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "fail_balancing.pdf"
    assert payload["rule_name"] == "total_debits_balance_total_credits"
    assert payload["queued"] is True
    queued = client.get("/api/documents/training-exceptions").json()
    assert any(
        item["filename"] == "fail_balancing.pdf" and item["rule_name"] == "total_debits_balance_total_credits"
        for item in queued["items"]
    )


def _connect(db_path):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_triage_document(conn, run_id, filename, expected_total, actual_total, root_cause, confidence):
    difference = None if expected_total is None or actual_total is None else actual_total - expected_total
    absolute_difference = abs(difference) if difference is not None else abs(actual_total or 0)
    conn.execute(
        """
        INSERT INTO document_registry (filename, document_type_id, document_path, page_count, has_coordinates, latest_run_id)
        VALUES (?, 'settlement_statement', ?, 1, 0, ?)
        """,
        (filename, filename, run_id),
    )
    conn.execute(
        """
        INSERT INTO business_rule_result (
            run_id, filename, rule_name, expected_total, actual_total, difference,
            absolute_difference, rule_passed, root_cause, summary
        )
        VALUES (?, ?, 'total_debits_balance_total_credits', ?, ?, ?, ?, 0, ?, 'failed')
        """,
        (run_id, filename, expected_total, actual_total, difference, absolute_difference, root_cause),
    )
    conn.execute(
        """
        INSERT INTO extraction (
            filename, document_id, document_type_id, field_id, field, is_missing,
            field_value, field_unformatted_value, validated_field_value, is_correct,
            confidence, ocr_confidence, operator_confirmed, row_index, column_index,
            page_range, page_count, page_number, x, y, width, height
        )
        VALUES (?, ?, 'settlement_statement', 'triage-field', 'Triage Field', 0,
                '1.00', '1.00', NULL, 1, ?, ?, 0, 0, 0, '1', 1, 1, NULL, NULL, NULL, NULL)
        """,
        (filename, filename, confidence, confidence),
    )
    conn.commit()
