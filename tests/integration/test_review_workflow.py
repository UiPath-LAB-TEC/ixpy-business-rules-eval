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
    assert docs["items"][0]["largest_absolute_difference"] >= docs["items"][-1]["largest_absolute_difference"]
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
