from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from backend.app.db import apply_migrations, connect, table_columns


SUMMARY_FIELD_ID = "Statement Table > Summary Totals and Balance"
MODERN_SUMMARY_FIELD_IDS = {
    "subtotal-debits-amount",
    "subtotal-credits-amount",
    "total-debits-amount",
    "total-credits-amount",
    "due-from-buyer-estimated-amount",
    "due-from-buyer-amount",
}
TABLE_FIELD_ID = "Statement Table"
MODERN_ITEMS_FIELD_ID = "items"
TABLE_FIELD_ID_PREFIX = "Statement Table > "
EXCLUDED_TABLE_FIELD_IDS = {
    "Statement Table > Column Headers",
    SUMMARY_FIELD_ID,
}

DEBIT_AMOUNT_FIELD = "Debit Amount"
CREDIT_AMOUNT_FIELD = "Credit Amount"
SUBTOTAL_DEBITS_FIELDS = ("Subtotal Debits Amount", "Subtotal Debit Amount")
SUBTOTAL_CREDITS_FIELDS = ("Subtotal Credits Amount", "Subtotal Credit Amount")
TOTAL_DEBITS_FIELDS = ("Total Debits Amount", "Total Debit Amount")
TOTAL_CREDITS_FIELDS = ("Total Credits Amount", "Total Credit Amount")
DUE_FROM_BUYER_FIELDS = (
    "Due from Buyer Estimated Amount",
    "Due From Buyer Estimated Amount",
)
FIELD_ALIASES = {
    "credit-amount": CREDIT_AMOUNT_FIELD,
    "credit amount": CREDIT_AMOUNT_FIELD,
    "debit-amount": DEBIT_AMOUNT_FIELD,
    "debit amount": DEBIT_AMOUNT_FIELD,
    "due-from-buyer-amount": "Due from Buyer Estimated Amount",
    "due-from-buyer-estimated-amount": "Due from Buyer Estimated Amount",
    "item-description": "Item Description",
    "item description": "Item Description",
    "parent-section": "Parent Section",
    "parent section": "Parent Section",
    "row-role": "Row Role",
    "row role": "Row Role",
    "subtotal-credits-amount": "Subtotal Credits Amount",
    "subtotal credits amount": "Subtotal Credits Amount",
    "subtotal-debits-amount": "Subtotal Debits Amount",
    "subtotal debits amount": "Subtotal Debits Amount",
    "total-credits-amount": "Total Credits Amount",
    "total credits amount": "Total Credits Amount",
    "total-debits-amount": "Total Debits Amount",
    "total debits amount": "Total Debits Amount",
}
ROLLUP_ROW_ROLE_TERMS = ("subtotal", "total", "summary")
ROLLUP_ITEM_DESCRIPTIONS = {"subtotal", "subtotals", "total", "totals"}
NON_ROLLUP_ITEM_PREFIXES = ("total consideration",)
DUE_FROM_BUYER_DESCRIPTION_TERMS = ("due from buyer", "due from borrower")
TOLERANCE = Decimal("0.01")

ROOT_CAUSES = {
    "missing field",
    "parse failure",
    "extraction mismatch",
    "OCR issue",
    "row inclusion error",
    "duplicate/rollup issue",
    "rule logic issue",
    "document inconsistency",
    "unknown",
}


@dataclass(frozen=True)
class EvidenceCell:
    filename: str
    field_id: str | None
    field: str | None
    value: str | None
    is_missing: bool
    row_index: int | None
    column_index: int | None
    page_number: int | None
    bbox: dict[str, float] | None
    confidence: float | None
    ocr_confidence: float | None


@dataclass(frozen=True)
class AmountSource:
    amount: Decimal
    cell: EvidenceCell


@dataclass(frozen=True)
class ExpectedAmountSource:
    amount: Decimal
    cell: EvidenceCell
    used_total_fallback: bool = False


@dataclass
class EvalContext:
    conn: sqlite3.Connection
    run_id: int
    filename: str
    warnings: list[dict[str, Any]]


def process_all_documents(db_path: str | Path, document_root: str | Path | None = None) -> int:
    path = Path(db_path)
    apply_migrations(path)
    conn = connect(path)
    try:
        run_id = _create_run(conn, path)
        summary_placeholders = ",".join("?" for _ in MODERN_SUMMARY_FIELD_IDS)
        filenames = [
            row["filename"]
            for row in conn.execute(
                f"""
                SELECT DISTINCT filename
                FROM extraction
                WHERE field_id = ?
                   OR field_id IN ({summary_placeholders})
                   OR field_id = ?
                ORDER BY filename
                """,
                (SUMMARY_FIELD_ID, *MODERN_SUMMARY_FIELD_IDS, MODERN_ITEMS_FIELD_ID),
            )
        ]
        result_count = 0
        warning_count = 0
        try:
            for filename in filenames:
                _register_document(conn, filename, run_id, document_root)
                result_count += _process_document(conn, run_id, filename)
            warning_count = conn.execute(
                "SELECT COUNT(*) AS count FROM business_rule_log WHERE run_id = ? AND level = 'warning'",
                (run_id,),
            ).fetchone()["count"]
            _complete_run(conn, run_id, "completed", len(filenames), result_count, warning_count)
        except Exception as exc:
            _complete_run(conn, run_id, "failed", len(filenames), result_count, warning_count, str(exc))
            raise
        conn.commit()
        return run_id
    finally:
        conn.close()


def _create_run(conn: sqlite3.Connection, db_path: Path) -> int:
    cursor = conn.execute(
        "INSERT INTO rule_run (evaluator_name, db_path) VALUES (?, ?)",
        ("settlement_statement", str(db_path)),
    )
    return int(cursor.lastrowid)


def _complete_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    document_count: int,
    result_count: int,
    warning_count: int,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE rule_run
        SET completed_at = ?, status = ?, document_count = ?, result_count = ?,
            warning_count = ?, error_message = ?
        WHERE run_id = ?
        """,
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            status,
            document_count,
            result_count,
            warning_count,
            error_message,
            run_id,
        ),
    )


def _register_document(
    conn: sqlite3.Connection,
    filename: str,
    run_id: int,
    document_root: str | Path | None,
) -> None:
    columns = table_columns(conn, "extraction")
    page_expr = "MAX(page_count)" if "page_count" in columns else "NULL"
    type_expr = "MAX(document_type_id)" if "document_type_id" in columns else "NULL"
    row = conn.execute(
        f"SELECT {type_expr} AS document_type_id, {page_expr} AS page_count FROM extraction WHERE filename = ?",
        (filename,),
    ).fetchone()
    has_coordinates = _has_coordinate_columns(columns)
    document_path = str(Path(document_root or "").joinpath(filename)) if document_root else filename
    conn.execute(
        """
        INSERT INTO document_registry
            (filename, document_type_id, document_path, page_count, has_coordinates, latest_run_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(filename) DO UPDATE SET
            document_type_id = excluded.document_type_id,
            document_path = excluded.document_path,
            page_count = excluded.page_count,
            has_coordinates = excluded.has_coordinates,
            latest_run_id = excluded.latest_run_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            filename,
            row["document_type_id"] if row else None,
            document_path,
            row["page_count"] if row else None,
            1 if has_coordinates else 0,
            run_id,
        ),
    )


def _has_coordinate_columns(columns: set[str]) -> bool:
    aliases = [
        {"page_number", "x", "y", "width", "height"},
        {"page", "left", "top", "right", "bottom"},
        {"page_index", "bbox_x", "bbox_y", "bbox_width", "bbox_height"},
    ]
    return any(group.issubset(columns) for group in aliases)


def _process_document(conn: sqlite3.Connection, run_id: int, filename: str) -> int:
    ctx = EvalContext(conn=conn, run_id=run_id, filename=filename, warnings=[])
    _log(ctx, "info", "document_started", f"Processing filename: {filename}")
    summary_totals = fetch_summary_totals(conn, filename)
    line_items = fetch_statement_table_data(conn, filename)
    results = evaluate_settlement_statement_rules(ctx, summary_totals, line_items)
    conn.execute("DELETE FROM business_rule_eval WHERE filename = ?", (filename,))
    if not results:
        _log(
            ctx,
            "warning",
            "no_rule_evaluated",
            f"No settlement-statement math rules evaluated for {filename}",
        )
        conn.execute(
            """
            INSERT INTO business_rule_eval_detail
                (run_id, filename, detail_type, evidence_role, reason, severity)
            VALUES (?, ?, 'no_rule_evaluated', 'diagnostic', ?, 'warning')
            """,
            (run_id, filename, "Required settlement-statement summary fields were missing or unrecognized."),
        )
        return 0

    for result in results:
        _write_result(ctx, result)
    return len(results)


def fetch_summary_totals(conn: sqlite3.Connection, filename: str) -> dict[int, dict[str, EvidenceCell]]:
    summary_placeholders = ",".join("?" for _ in MODERN_SUMMARY_FIELD_IDS)
    rows = _fetch_extraction_rows(
        conn,
        f"""
        SELECT * FROM extraction
        WHERE filename = ?
          AND (field_id = ? OR field_id IN ({summary_placeholders}))
          AND field != ?
        ORDER BY row_index, column_index
        """,
        (filename, SUMMARY_FIELD_ID, *MODERN_SUMMARY_FIELD_IDS, SUMMARY_FIELD_ID),
    )
    return _organize_data(rows)


def fetch_statement_table_data(
    conn: sqlite3.Connection,
    filename: str,
) -> dict[str, dict[int, dict[str, EvidenceCell]]]:
    excluded_placeholders = ",".join("?" for _ in EXCLUDED_TABLE_FIELD_IDS)
    rows = _fetch_extraction_rows(
        conn,
        f"""
        SELECT * FROM extraction
        WHERE filename = ?
          AND (field_id = ? OR field_id LIKE ? OR field_id = ?)
          AND field_id NOT IN ({excluded_placeholders})
          AND COALESCE(row_index, -1) >= 0
          AND field != field_id
        ORDER BY field_id, row_index, column_index
        """,
        (filename, TABLE_FIELD_ID, f"{TABLE_FIELD_ID_PREFIX}%", MODERN_ITEMS_FIELD_ID, *EXCLUDED_TABLE_FIELD_IDS),
    )

    grouped: dict[str, list[EvidenceCell]] = {}
    for cell in rows:
        grouped.setdefault(cell.field_id or "", []).append(cell)
    return {field_id: _organize_data(cells) for field_id, cells in grouped.items()}


def _fetch_extraction_rows(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...],
) -> list[EvidenceCell]:
    columns = table_columns(conn, "extraction")
    cells: list[EvidenceCell] = []
    for row in conn.execute(query, params):
        cells.append(
            EvidenceCell(
                filename=row["filename"],
                field_id=row["field_id"] if "field_id" in columns else None,
                field=row["field"] if "field" in columns else None,
                value=_first_nonblank(
                    row["validated_field_value"] if "validated_field_value" in columns else None,
                    row["field_value"] if "field_value" in columns else None,
                    row["field_unformatted_value"] if "field_unformatted_value" in columns else None,
                ),
                is_missing=bool(row["is_missing"]) if "is_missing" in columns else False,
                row_index=row["row_index"] if "row_index" in columns else None,
                column_index=row["column_index"] if "column_index" in columns else None,
                page_number=_page_number(row, columns),
                bbox=_bbox(row, columns),
                confidence=row["confidence"] if "confidence" in columns else None,
                ocr_confidence=row["ocr_confidence"] if "ocr_confidence" in columns else None,
            )
        )
    return cells


def _page_number(row: sqlite3.Row, columns: set[str]) -> int | None:
    for name in ("page_number", "page", "page_index"):
        if name in columns and row[name] is not None:
            return int(row[name])
    page_range = row["page_range"] if "page_range" in columns else None
    if page_range:
        match = re.search(r"\d+", str(page_range))
        if match:
            return int(match.group(0))
    return None


def _bbox(row: sqlite3.Row, columns: set[str]) -> dict[str, float] | None:
    if {"x", "y", "width", "height"}.issubset(columns):
        values = [row["x"], row["y"], row["width"], row["height"]]
        if all(value is not None for value in values):
            return {"x": float(values[0]), "y": float(values[1]), "width": float(values[2]), "height": float(values[3])}
    if {"bbox_x", "bbox_y", "bbox_width", "bbox_height"}.issubset(columns):
        values = [row["bbox_x"], row["bbox_y"], row["bbox_width"], row["bbox_height"]]
        if all(value is not None for value in values):
            return {"x": float(values[0]), "y": float(values[1]), "width": float(values[2]), "height": float(values[3])}
    if {"left", "top", "right", "bottom"}.issubset(columns):
        values = [row["left"], row["top"], row["right"], row["bottom"]]
        if all(value is not None for value in values):
            return {
                "x": float(values[0]),
                "y": float(values[1]),
                "width": float(values[2]) - float(values[0]),
                "height": float(values[3]) - float(values[1]),
            }
    return None


def _organize_data(rows: list[EvidenceCell]) -> dict[int, dict[str, EvidenceCell]]:
    data: dict[int, dict[str, EvidenceCell]] = {}
    for cell in rows:
        row_index = cell.row_index if cell.row_index is not None else -1
        field = _normalize_field(cell.field, cell.column_index)
        data.setdefault(row_index, {})[field] = cell
    return data


def _normalize_field(field: str | None, column_index: int | None) -> str:
    if not field:
        return f"Unknown Field {column_index}"
    stripped = field.strip()
    return FIELD_ALIASES.get(stripped.lower(), stripped)


def _first_nonblank(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return values[-1] if values else None


def clean_numeric_value(ctx: EvalContext, cell: EvidenceCell | str | int | float | Decimal | None) -> Decimal:
    raw_value = cell.value if isinstance(cell, EvidenceCell) else cell
    if raw_value is None:
        return Decimal("0")
    if isinstance(raw_value, Decimal):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return Decimal(str(raw_value))
    text = str(raw_value).strip()
    if not text:
        return Decimal("0")
    is_parenthetical_negative = text.startswith("(") and text.endswith(")")
    cleaned_value = re.sub(r"[^\d.-]", "", text)
    is_negative = is_parenthetical_negative or "-" in cleaned_value
    cleaned_value = cleaned_value.replace("-", "")
    if cleaned_value in {"", "."}:
        _numeric_warning(ctx, cell, raw_value, None)
        return Decimal("0")
    try:
        number = Decimal(cleaned_value)
    except InvalidOperation:
        _numeric_warning(ctx, cell, raw_value, cleaned_value)
        return Decimal("0")
    return -number if is_negative else number


def _numeric_warning(
    ctx: EvalContext,
    cell: EvidenceCell | str | int | float | Decimal | None,
    raw_value: Any,
    normalized_value: str | None,
) -> None:
    message = f"Could not parse numeric value from: {raw_value}"
    _log(
        ctx,
        "warning",
        "numeric_parse_failure",
        message,
        raw_value=str(raw_value),
        normalized_value=normalized_value,
        cell=cell if isinstance(cell, EvidenceCell) else None,
    )
    ctx.warnings.append(
        {
            "raw_value": str(raw_value),
            "normalized_value": normalized_value,
            "cell": cell if isinstance(cell, EvidenceCell) else None,
        }
    )


def evaluate_settlement_statement_rules(
    ctx: EvalContext,
    summary_totals: dict[int, dict[str, EvidenceCell]],
    line_items_by_field_id: dict[str, dict[int, dict[str, EvidenceCell]]],
) -> list[dict[str, Any]]:
    subtotal_debits = first_present_amount(ctx, summary_totals, SUBTOTAL_DEBITS_FIELDS)
    subtotal_credits = first_present_amount(ctx, summary_totals, SUBTOTAL_CREDITS_FIELDS)
    total_debits = first_present_amount(ctx, summary_totals, TOTAL_DEBITS_FIELDS)
    total_credits = first_present_amount(ctx, summary_totals, TOTAL_CREDITS_FIELDS)
    debit_line_expected = subtotal_debits or total_field_fallback(total_debits)
    credit_line_expected = subtotal_credits or total_field_fallback(total_credits)
    due_from_buyer = first_present_amount(ctx, summary_totals, DUE_FROM_BUYER_FIELDS) or due_from_buyer_line_item(
        ctx,
        line_items_by_field_id,
    )
    rollup_amounts = {
        amount.amount
        for amount in collect_present_amounts(
            ctx,
            summary_totals,
            SUBTOTAL_DEBITS_FIELDS + SUBTOTAL_CREDITS_FIELDS + TOTAL_DEBITS_FIELDS + TOTAL_CREDITS_FIELDS,
        )
    }

    line_item_debits = sum_line_item_amounts(ctx, line_items_by_field_id, DEBIT_AMOUNT_FIELD, rollup_amounts)
    line_item_credits = sum_line_item_amounts(ctx, line_items_by_field_id, CREDIT_AMOUNT_FIELD, rollup_amounts)

    results: list[dict[str, Any]] = []
    if debit_line_expected is not None:
        results.append(
            build_rule_result(
                "debit_amounts_equal_subtotal_debits",
                debit_line_expected.amount,
                line_item_debits["total"],
                [debit_line_expected],
                line_item_debits["included"],
                line_item_debits["excluded"],
            )
        )
    if credit_line_expected is not None:
        results.append(
            build_rule_result(
                "credit_amounts_equal_subtotal_credits",
                credit_line_expected.amount,
                line_item_credits["total"],
                [credit_line_expected],
                line_item_credits["included"],
                line_item_credits["excluded"],
            )
        )
    if subtotal_credits is not None and total_credits is not None:
        actual_sources = [subtotal_credits]
        actual_total = subtotal_credits.amount
        if due_from_buyer is not None:
            actual_sources.append(due_from_buyer)
            actual_total += due_from_buyer.amount
        results.append(
            build_rule_result(
                "total_credits_equal_subtotal_credits_plus_due_from_buyer",
                total_credits.amount,
                actual_total,
                [total_credits],
                actual_sources,
                [],
            )
        )
    if total_debits is not None and total_credits is not None:
        adjusted = adjusted_total_credits(total_debits.amount, total_credits.amount, due_from_buyer.amount if due_from_buyer else None)
        actual_sources = [total_credits]
        if due_from_buyer is not None:
            actual_sources.append(due_from_buyer)
        results.append(
            build_rule_result(
                "total_debits_balance_total_credits",
                total_debits.amount,
                adjusted,
                [total_debits],
                actual_sources,
                [],
            )
        )
    return results


def adjusted_total_credits(
    total_debits: Decimal,
    total_credits: Decimal,
    due_from_buyer: Decimal | None,
) -> Decimal:
    if due_from_buyer is None:
        return total_credits
    difference = total_debits - total_credits
    if abs(abs(difference) - abs(due_from_buyer)) > TOLERANCE:
        return total_credits
    if difference > 0:
        return total_credits + abs(due_from_buyer)
    if difference < 0:
        return total_credits - abs(due_from_buyer)
    return total_credits


def total_field_fallback(total_source: AmountSource | None) -> ExpectedAmountSource | None:
    if total_source is None:
        return None
    return ExpectedAmountSource(total_source.amount, total_source.cell, used_total_fallback=True)


def sum_line_item_amounts(
    ctx: EvalContext,
    line_items_by_field_id: dict[str, dict[int, dict[str, EvidenceCell]]],
    amount_field: str,
    subtotal_amounts: set[Decimal] | None = None,
) -> dict[str, Any]:
    total = Decimal("0")
    included: list[AmountSource] = []
    excluded: list[dict[str, Any]] = []
    subtotal_amounts = subtotal_amounts or set()
    for field_id, line_items in line_items_by_field_id.items():
        if field_id == TABLE_FIELD_ID:
            section = sum_first_statement_table_section(ctx, line_items, amount_field, subtotal_amounts)
        else:
            section = sum_all_non_rollup_rows(ctx, line_items, amount_field, subtotal_amounts)
        total += section["total"]
        included.extend(section["included"])
        excluded.extend(section["excluded"])
    return {"total": total, "included": included, "excluded": excluded}


def sum_first_statement_table_section(
    ctx: EvalContext,
    line_items: dict[int, dict[str, EvidenceCell]],
    amount_field: str,
    subtotal_amounts: set[Decimal],
) -> dict[str, Any]:
    total = Decimal("0")
    included: list[AmountSource] = []
    excluded: list[dict[str, Any]] = []
    section_started = False
    for row_index, fields in sorted(line_items.items()):
        if is_rollup_row(ctx, fields, subtotal_amounts):
            excluded.append({"fields": fields, "reason": "rollup row excluded"})
            if section_started:
                break
            continue
        if row_has_line_item_data(fields):
            section_started = True
        amount_info = fields.get(amount_field)
        if not is_present(amount_info):
            continue
        amount = clean_numeric_value(ctx, amount_info)
        total += amount
        included.append(AmountSource(amount=amount, cell=amount_info))
    return {"total": total, "included": included, "excluded": excluded}


def sum_all_non_rollup_rows(
    ctx: EvalContext,
    line_items: dict[int, dict[str, EvidenceCell]],
    amount_field: str,
    subtotal_amounts: set[Decimal],
) -> dict[str, Any]:
    total = Decimal("0")
    included: list[AmountSource] = []
    excluded: list[dict[str, Any]] = []
    for fields in line_items.values():
        if is_rollup_row(ctx, fields, subtotal_amounts):
            excluded.append({"fields": fields, "reason": "rollup row excluded"})
            continue
        amount_info = fields.get(amount_field)
        if not is_present(amount_info):
            continue
        amount = clean_numeric_value(ctx, amount_info)
        total += amount
        included.append(AmountSource(amount=amount, cell=amount_info))
    return {"total": total, "included": included, "excluded": excluded}


def row_has_line_item_data(fields: dict[str, EvidenceCell]) -> bool:
    return any(is_present(fields.get(name)) for name in ("Item Description", DEBIT_AMOUNT_FIELD, CREDIT_AMOUNT_FIELD))


def is_rollup_row(
    ctx: EvalContext,
    fields: dict[str, EvidenceCell],
    subtotal_amounts: set[Decimal],
) -> bool:
    row_role = normalized_field_value(fields, "Row Role")
    item_description = normalized_field_value(fields, "Item Description")
    if is_due_from_buyer_row(fields):
        return True
    if any(term in row_role for term in ROLLUP_ROW_ROLE_TERMS):
        return True
    if item_description in ROLLUP_ITEM_DESCRIPTIONS:
        return True
    if "subtotal" in item_description or "sub-total" in item_description:
        return True
    return row_has_subtotal_amount(ctx, fields, subtotal_amounts) and has_rollup_total_label(item_description)


def has_rollup_total_label(item_description: str) -> bool:
    if not item_description:
        return False
    if item_description.startswith(NON_ROLLUP_ITEM_PREFIXES):
        return False
    return "total" in item_description


def row_has_subtotal_amount(
    ctx: EvalContext,
    fields: dict[str, EvidenceCell],
    subtotal_amounts: set[Decimal],
) -> bool:
    if not subtotal_amounts:
        return False
    for amount_field in (DEBIT_AMOUNT_FIELD, CREDIT_AMOUNT_FIELD):
        amount_info = fields.get(amount_field)
        if not is_present(amount_info):
            continue
        if clean_numeric_value(ctx, amount_info) in subtotal_amounts:
            return True
    return False


def normalized_field_value(fields: dict[str, EvidenceCell], field_name: str) -> str:
    field_info = fields.get(field_name)
    if not is_present(field_info):
        return ""
    return re.sub(r"\s+", " ", str(field_info.value).strip().lower())


def due_from_buyer_line_item(
    ctx: EvalContext,
    line_items_by_field_id: dict[str, dict[int, dict[str, EvidenceCell]]],
) -> AmountSource | None:
    for line_items in line_items_by_field_id.values():
        for fields in line_items.values():
            if not is_due_from_buyer_row(fields):
                continue
            for amount_field in (CREDIT_AMOUNT_FIELD, DEBIT_AMOUNT_FIELD):
                amount_info = fields.get(amount_field)
                if is_present(amount_info):
                    return AmountSource(clean_numeric_value(ctx, amount_info), amount_info)
    return None


def is_due_from_buyer_row(fields: dict[str, EvidenceCell]) -> bool:
    item_description = normalized_field_value(fields, "Item Description")
    return any(term in item_description for term in DUE_FROM_BUYER_DESCRIPTION_TERMS)


def collect_present_amounts(
    ctx: EvalContext,
    rows: dict[int, dict[str, EvidenceCell]],
    field_names: tuple[str, ...],
) -> list[AmountSource]:
    amounts: list[AmountSource] = []
    for fields in rows.values():
        for field_name in field_names:
            field_info = fields.get(field_name)
            if is_present(field_info):
                amounts.append(AmountSource(clean_numeric_value(ctx, field_info), field_info))
    return amounts


def first_present_amount(
    ctx: EvalContext,
    rows: dict[int, dict[str, EvidenceCell]],
    field_names: tuple[str, ...],
) -> AmountSource | None:
    for fields in rows.values():
        for field_name in field_names:
            field_info = fields.get(field_name)
            if is_present(field_info):
                return AmountSource(clean_numeric_value(ctx, field_info), field_info)
    return None


def is_present(field_info: EvidenceCell | None) -> bool:
    if not field_info or field_info.is_missing:
        return False
    return field_info.value is not None and str(field_info.value).strip() != ""


def build_rule_result(
    rule_name: str,
    expected_total: Decimal,
    actual_total: Decimal,
    expected_sources: list[AmountSource],
    actual_sources: list[AmountSource],
    excluded_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    difference = actual_total - expected_total
    passed = abs(difference) <= TOLERANCE
    return {
        "rule_name": rule_name,
        "expected_total": expected_total,
        "actual_total": actual_total,
        "difference": difference,
        "absolute_difference": abs(difference),
        "rule_passed": passed,
        "expected_sources": expected_sources,
        "actual_sources": actual_sources,
        "excluded_rows": excluded_rows,
    }


def _write_result(ctx: EvalContext, result: dict[str, Any]) -> None:
    root_cause = _infer_root_cause(ctx, result)
    summary = _summary(result, root_cause)
    _log(
        ctx,
        "info" if result["rule_passed"] else "error",
        "rule_result",
        "Rule '%s' %s: Expected = %s, Actual = %s"
        % (
            result["rule_name"],
            "PASSED" if result["rule_passed"] else "FAILED",
            result["expected_total"],
            result["actual_total"],
        ),
    )
    conn = ctx.conn
    conn.execute(
        """
        INSERT INTO business_rule_eval
            (filename, rule_name, expected_total, actual_total, rule_passed)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(filename, rule_name) DO UPDATE SET
            expected_total = excluded.expected_total,
            actual_total = excluded.actual_total,
            rule_passed = excluded.rule_passed
        """,
        (
            ctx.filename,
            result["rule_name"],
            float(result["expected_total"]),
            float(result["actual_total"]),
            1 if result["rule_passed"] else 0,
        ),
    )
    cursor = conn.execute(
        """
        INSERT INTO business_rule_result
            (run_id, filename, rule_name, expected_total, actual_total, difference,
             absolute_difference, tolerance, rule_passed, root_cause, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx.run_id,
            ctx.filename,
            result["rule_name"],
            float(result["expected_total"]),
            float(result["actual_total"]),
            float(result["difference"]),
            float(result["absolute_difference"]),
            float(TOLERANCE),
            1 if result["rule_passed"] else 0,
            root_cause,
            summary,
        ),
    )
    result_id = int(cursor.lastrowid)
    _write_computed_detail(ctx, result_id, result)
    for source in result["expected_sources"]:
        reason = (
            "subtotal missing; total field used as expected line-item total"
            if getattr(source, "used_total_fallback", False)
            else None
        )
        _write_cell_detail(ctx, result_id, result["rule_name"], "expected_source", "expected_total", source.cell, source.amount, reason)
    for source in result["actual_sources"]:
        role = "included_row" if result["rule_name"] in {"debit_amounts_equal_subtotal_debits", "credit_amounts_equal_subtotal_credits"} else "actual_source"
        _write_cell_detail(ctx, result_id, result["rule_name"], role, "actual_total", source.cell, source.amount)
    for excluded in result["excluded_rows"]:
        cells = list(excluded["fields"].values())
        cell = cells[0] if cells else None
        if cell:
            _write_cell_detail(ctx, result_id, result["rule_name"], "excluded_row", "excluded", cell, None, excluded["reason"])


def _summary(result: dict[str, Any], root_cause: str) -> str:
    verb = "passed" if result["rule_passed"] else "failed"
    return (
        f"Rule {verb} because actual {float(result['actual_total']):.2f} "
        f"and expected {float(result['expected_total']):.2f} differ by "
        f"{float(result['difference']):.2f}. Likely root cause: {root_cause}."
    )


def _infer_root_cause(ctx: EvalContext, result: dict[str, Any]) -> str:
    if result["rule_passed"]:
        return "unknown"
    if ctx.warnings:
        return "parse failure"
    if result["excluded_rows"] and result["absolute_difference"] > TOLERANCE:
        return "duplicate/rollup issue"
    if not result["expected_sources"] or not result["actual_sources"]:
        return "missing field"
    return "extraction mismatch"


def _write_computed_detail(ctx: EvalContext, result_id: int, result: dict[str, Any]) -> None:
    for role, value in (
        ("expected_total", result["expected_total"]),
        ("actual_total", result["actual_total"]),
        ("difference", result["difference"]),
        ("absolute_difference", result["absolute_difference"]),
        ("tolerance", TOLERANCE),
    ):
        ctx.conn.execute(
            """
            INSERT INTO business_rule_eval_detail
                (result_id, run_id, filename, rule_name, detail_type, evidence_role,
                 normalized_value, amount)
            VALUES (?, ?, ?, ?, 'computed_value', ?, ?, ?)
            """,
            (result_id, ctx.run_id, ctx.filename, result["rule_name"], role, str(value), float(value)),
        )


def _write_cell_detail(
    ctx: EvalContext,
    result_id: int,
    rule_name: str,
    detail_type: str,
    evidence_role: str,
    cell: EvidenceCell,
    amount: Decimal | None,
    reason: str | None = None,
) -> None:
    ctx.conn.execute(
        """
        INSERT INTO business_rule_eval_detail
            (result_id, run_id, filename, rule_name, detail_type, evidence_role,
             source_field_id, source_field, row_index, column_index, raw_value,
             normalized_value, amount, page_number, bbox_json, reason, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_id,
            ctx.run_id,
            ctx.filename,
            rule_name,
            detail_type,
            evidence_role,
            cell.field_id,
            cell.field,
            cell.row_index,
            cell.column_index,
            cell.value,
            str(amount) if amount is not None else None,
            float(amount) if amount is not None else None,
            cell.page_number,
            json.dumps(cell.bbox) if cell.bbox else None,
            reason,
            json.dumps({"confidence": cell.confidence, "ocr_confidence": cell.ocr_confidence}),
        ),
    )


def _log(
    ctx: EvalContext,
    level: str,
    event_type: str,
    message: str,
    raw_value: str | None = None,
    normalized_value: str | None = None,
    cell: EvidenceCell | None = None,
) -> None:
    context = None
    if cell:
        context = {
            "field_id": cell.field_id,
            "field": cell.field,
            "row_index": cell.row_index,
            "column_index": cell.column_index,
            "page_number": cell.page_number,
            "bbox": cell.bbox,
        }
    ctx.conn.execute(
        """
        INSERT INTO business_rule_log
            (run_id, filename, level, event_type, message, raw_value, normalized_value, context_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ctx.run_id, ctx.filename, level, event_type, message, raw_value, normalized_value, json.dumps(context) if context else None),
    )
