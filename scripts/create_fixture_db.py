from __future__ import annotations

from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "tests" / "fixtures" / "settlement_fixture.db"
DOC_ROOT = ROOT / "tests" / "fixtures" / "docs"


def main() -> None:
    create_fixture(DB_PATH, DOC_ROOT)
    print(DB_PATH)


def create_fixture(db_path: Path, doc_root: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    doc_root.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
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
                page_number INTEGER,
                x REAL,
                y REAL,
                width REAL,
                height REAL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (filename, field_id, field, row_index, column_index)
            )
            """
        )
        _insert_document(conn, "pass_balanced.pdf", "doc-pass", "settlement_statement", subtotal_debits="300.00", subtotal_credits="250.00", total_debits="300.00", total_credits="300.00", due_from_buyer="50.00", debit_rows=["100.00", "200.00"], credit_rows=["250.00"])
        _insert_document(conn, "fail_balancing.pdf", "doc-fail", "settlement_statement", subtotal_debits="300.00", subtotal_credits="250.00", total_debits="300.00", total_credits="260.00", due_from_buyer="", debit_rows=["100.00", "200.00"], credit_rows=["125.00", "150.00"])
        _insert_document(conn, "warning_parse.pdf", "doc-warning", "settlement_statement", subtotal_debits="500.00", subtotal_credits="400.00", total_debits="500.00", total_credits="400.00", due_from_buyer="", debit_rows=["to", "500.00"], credit_rows=["USD", "400.00"])
        _insert_document(conn, "no_rule.pdf", "doc-no-rule", "settlement_statement", subtotal_debits="", subtotal_credits="", total_debits="", total_credits="", due_from_buyer="", debit_rows=[], credit_rows=[])
        conn.commit()
    finally:
        conn.close()
    for name in ("pass_balanced.pdf", "fail_balancing.pdf", "warning_parse.pdf", "no_rule.pdf"):
        _write_fixture_pdf(doc_root / name, name)


def _insert_document(
    conn: sqlite3.Connection,
    filename: str,
    document_id: str,
    document_type_id: str,
    subtotal_debits: str,
    subtotal_credits: str,
    total_debits: str,
    total_credits: str,
    due_from_buyer: str,
    debit_rows: list[str],
    credit_rows: list[str],
) -> None:
    summary_values = [
        ("Subtotal Debits Amount", subtotal_debits),
        ("Subtotal Credits Amount", subtotal_credits),
        ("Total Debits Amount", total_debits),
        ("Total Credits Amount", total_credits),
        ("Due from Buyer Estimated Amount", due_from_buyer),
    ]
    for column_index, (field, value) in enumerate(summary_values):
        _row(conn, filename, document_id, document_type_id, "Statement Table > Summary Totals and Balance", field, value == "", value, 0, column_index, 0.90, 0.92)
    row_index = 1
    for amount in debit_rows:
        _row(conn, filename, document_id, document_type_id, "Statement Table", "Item Description", False, f"Debit item {row_index}", row_index, 0, 0.88, 0.90)
        _row(conn, filename, document_id, document_type_id, "Statement Table", "Debit Amount", amount == "", amount, row_index, 1, 0.84, 0.86)
        row_index += 1
    if debit_rows:
        _row(conn, filename, document_id, document_type_id, "Statement Table", "Item Description", False, "Subtotal", row_index, 0, 0.95, 0.95)
        _row(conn, filename, document_id, document_type_id, "Statement Table", "Debit Amount", False, subtotal_debits, row_index, 1, 0.95, 0.95)
        _row(conn, filename, document_id, document_type_id, "Statement Table", "Row Role", False, "subtotal", row_index, 2, 0.95, 0.95)
        row_index += 1
    for amount in credit_rows:
        _row(conn, filename, document_id, document_type_id, "Statement Table > Credits", "Item Description", False, f"Credit item {row_index}", row_index, 0, 0.87, 0.89)
        _row(conn, filename, document_id, document_type_id, "Statement Table > Credits", "Credit Amount", amount == "", amount, row_index, 1, 0.83, 0.85)
        row_index += 1
    if credit_rows:
        _row(conn, filename, document_id, document_type_id, "Statement Table > Credits", "Item Description", False, "Total credits", row_index, 0, 0.95, 0.95)
        _row(conn, filename, document_id, document_type_id, "Statement Table > Credits", "Credit Amount", False, subtotal_credits, row_index, 1, 0.95, 0.95)


def _row(
    conn: sqlite3.Connection,
    filename: str,
    document_id: str,
    document_type_id: str,
    field_id: str,
    field: str,
    is_missing: bool,
    value: str,
    row_index: int,
    column_index: int,
    confidence: float,
    ocr_confidence: float,
) -> None:
    conn.execute(
        """
        INSERT INTO extraction
            (filename, document_id, document_type_id, field_id, field, is_missing,
             field_value, field_unformatted_value, validated_field_value, is_correct,
             confidence, ocr_confidence, operator_confirmed, row_index, column_index,
             page_range, page_count, page_number, x, y, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            document_id,
            document_type_id,
            field_id,
            field,
            1 if is_missing else 0,
            value,
            value,
            None,
            0 if value in {"to", "USD"} else 1,
            confidence,
            ocr_confidence,
            0,
            row_index,
            column_index,
            "1",
            1,
            1,
            min(0.1 + column_index * 0.18, 0.8),
            min(0.12 + row_index * 0.06, 0.82),
            0.14,
            0.04,
        ),
    )


def _write_fixture_pdf(path: Path, title: str) -> None:
    text = f"Business rule fixture: {title}".replace("(", "[").replace(")", "]")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(f'BT /F1 18 Tf 72 720 Td ({text}) Tj ET')} >>\nstream\nBT /F1 18 Tf 72 720 Td ({text}) Tj ET\nendstream".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode())
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    path.write_bytes(bytes(content))


if __name__ == "__main__":
    main()
