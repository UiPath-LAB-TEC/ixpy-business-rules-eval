from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from backend.app.db import apply_migrations


def test_eval_fallback_surfaces_missing_and_alias_borrower_regular_fields(tmp_path, monkeypatch):
    db_path = tmp_path / "borrower_regular_fields.db"
    _create_extraction_schema(db_path)
    apply_migrations(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO extraction (
                filename, document_id, document_type_id, field_id, field, is_missing,
                field_value, field_unformatted_value, validated_field_value, is_correct,
                confidence, ocr_confidence, operator_confirmed, row_index, column_index,
                page_range, page_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "3169265740.pdf",
                    "doc-modern",
                    "settlement_statement",
                    "due-from-borrower",
                    "Due From Borrower",
                    1,
                    None,
                    None,
                    None,
                    1,
                    None,
                    None,
                    None,
                    -1,
                    -1,
                    "1",
                    1,
                ),
                (
                    "3169265740.pdf",
                    "doc-modern",
                    "settlement_statement",
                    "due-to-brorrower",
                    "Due To Brorrower",
                    0,
                    "498393.85",
                    "498,393.85",
                    None,
                    1,
                    0.962,
                    1.0,
                    0,
                    -1,
                    -1,
                    "1",
                    1,
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO business_rule_eval
                (filename, rule_name, expected_total, actual_total, rule_passed)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("3169265740.pdf", "borrower_balance_fields_are_mutually_exclusive", 1, 1, 1),
        )
        conn.commit()
    monkeypatch.setenv("BUSINESS_RULE_DB", str(db_path))
    monkeypatch.setenv("BUSINESS_RULE_DOCUMENT_ROOT", str(tmp_path))

    from backend.app.main import create_app

    client = TestClient(create_app())
    payload = client.get(
        "/api/evaluations/3169265740.pdf/borrower_balance_fields_are_mutually_exclusive/explanation"
    ).json()

    regular_fields = [
        detail
        for detail in payload["details"]
        if detail["detail_type"] == "actual_source"
    ]
    due_from = next(detail for detail in regular_fields if detail["source_field_id"] == "due-from-borrower")
    due_to = next(detail for detail in regular_fields if detail["source_field_id"] == "due-to-borrower")

    assert due_from["source_field"] == "Due From Borrower"
    assert due_from["amount"] is None
    assert due_from["reason"] == "missing extraction"
    assert due_from["metadata"]["is_missing"] is True
    assert due_to["source_field"] == "Due To Borrower"
    assert due_to["amount"] == 498393.85
    assert due_to["metadata"]["original_source_field_id"] == "due-to-brorrower"


def _create_extraction_schema(db_path):
    with sqlite3.connect(db_path) as conn:
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
        conn.commit()
