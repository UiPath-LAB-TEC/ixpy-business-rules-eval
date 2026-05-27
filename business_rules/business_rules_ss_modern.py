import json
import logging
import os
import re
import sqlite3
from collections import defaultdict
from decimal import Decimal, InvalidOperation


SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "uwm_ss_v14_uwm_eval.db")

SUMMARY_FIELD_IDS = {
    "subtotal-debits-amount",
    "subtotal-credits-amount",
    "total-debits-amount",
    "total-credits-amount",
    "due-from-borrower",
    "due-from-brorrower",
    "due-to-borrower",
    "due-to-brorrower",
    "due-from-buyer-estimated-amount",
    "due-from-buyer-amount",
}
ITEMS_FIELD_ID = "items"

DEBIT_AMOUNT_FIELD = "Debit Amount"
CREDIT_AMOUNT_FIELD = "Credit Amount"
DUE_FROM_BORROWER_FIELD = "Due From Borrower"
DUE_TO_BORROWER_FIELD = "Due To Borrower"
SUBTOTAL_DEBITS_FIELDS = ("Subtotal Debits Amount", "Subtotal Debit Amount")
SUBTOTAL_CREDITS_FIELDS = ("Subtotal Credits Amount", "Subtotal Credit Amount")
TOTAL_DEBITS_FIELDS = ("Total Debits Amount", "Total Debit Amount")
TOTAL_CREDITS_FIELDS = ("Total Credits Amount", "Total Credit Amount")
DUE_FROM_BORROWER_FIELDS = (DUE_FROM_BORROWER_FIELD,)
DUE_TO_BORROWER_FIELDS = (DUE_TO_BORROWER_FIELD,)

FIELD_ALIASES = {
    "credit-amount": CREDIT_AMOUNT_FIELD,
    "credit amount": CREDIT_AMOUNT_FIELD,
    "debit-amount": DEBIT_AMOUNT_FIELD,
    "debit amount": DEBIT_AMOUNT_FIELD,
    "due-from-borrower": DUE_FROM_BORROWER_FIELD,
    "due from borrower": DUE_FROM_BORROWER_FIELD,
    "due-from-brorrower": DUE_FROM_BORROWER_FIELD,
    "due from brorrower": DUE_FROM_BORROWER_FIELD,
    "due-from-buyer-amount": DUE_FROM_BORROWER_FIELD,
    "due-from-buyer-estimated-amount": DUE_FROM_BORROWER_FIELD,
    "due from buyer estimated amount": DUE_FROM_BORROWER_FIELD,
    "due-to-borrower": DUE_TO_BORROWER_FIELD,
    "due to borrower": DUE_TO_BORROWER_FIELD,
    "due-to-brorrower": DUE_TO_BORROWER_FIELD,
    "due to brorrower": DUE_TO_BORROWER_FIELD,
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
BALANCE_ROW_TERMS = (
    "cash from borrower",
    "cash from buyer",
    "cash from seller",
    "cash to borrower",
    "cash to buyer",
    "cash to seller",
    "due from borrower",
    "due from buyer",
    "due from seller",
    "due to borrower",
    "due to buyer",
    "due to seller",
)
TOLERANCE = Decimal("0.01")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def create_business_rule_eval_table(db_path=SQLITE_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS business_rule_eval (
                filename TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                expected_total REAL,
                actual_total REAL,
                rule_passed BOOLEAN NOT NULL,
                failure_reason TEXT,
                details TEXT,
                PRIMARY KEY (filename, rule_name)
            )
            """
        )
        ensure_business_rule_eval_columns(cursor)
        conn.commit()
    finally:
        conn.close()


def ensure_business_rule_eval_columns(cursor):
    cursor.execute("PRAGMA table_info(business_rule_eval)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if "failure_reason" not in existing_columns:
        cursor.execute("ALTER TABLE business_rule_eval ADD COLUMN failure_reason TEXT")
    if "details" not in existing_columns:
        cursor.execute("ALTER TABLE business_rule_eval ADD COLUMN details TEXT")


def insert_rule_eval(filename, results, db_path=SQLITE_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        ensure_business_rule_eval_columns(cursor)
        for rule_name, result in results.items():
            cursor.execute(
                """
                INSERT INTO business_rule_eval
                    (
                        filename,
                        rule_name,
                        expected_total,
                        actual_total,
                        rule_passed,
                        failure_reason,
                        details
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filename, rule_name) DO UPDATE SET
                    expected_total=excluded.expected_total,
                    actual_total=excluded.actual_total,
                    rule_passed=excluded.rule_passed,
                    failure_reason=excluded.failure_reason,
                    details=excluded.details
                """,
                (
                    filename,
                    rule_name,
                    float(result["expected_total"]),
                    float(result["actual_total"]),
                    bool(result["match"]),
                    result.get("failure_reason"),
                    json.dumps(result.get("details", {}), sort_keys=True),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def delete_rule_eval(filename, db_path=SQLITE_DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM business_rule_eval WHERE filename=?",
            (filename,),
        )
        conn.commit()
    finally:
        conn.close()


def process_all_documents(db_path=SQLITE_DB_PATH):
    create_business_rule_eval_table(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        placeholders = ",".join("?" for _ in SUMMARY_FIELD_IDS)
        cursor.execute(
            f"""
            SELECT DISTINCT filename
            FROM extraction
            WHERE (
                field_id IN ({placeholders})
                OR field_id = ?
            )
              AND (
                is_missing = 0
                OR COALESCE(field_value, '') != ''
                OR COALESCE(field_unformatted_value, '') != ''
                OR COALESCE(validated_field_value, '') != ''
                OR row_index >= 0
              )
            """,
            (*SUMMARY_FIELD_IDS, ITEMS_FIELD_ID),
        )
        filenames = [row[0] for row in cursor.fetchall()]

        for filename in filenames:
            logger.info("Processing filename: %s", filename)
            summary_totals = fetch_summary_totals(filename, db_path)
            line_items = fetch_statement_table_data(filename, db_path)
            results = evaluate_settlement_statement_rules(
                summary_totals,
                line_items,
            )
            delete_rule_eval(filename, db_path)
            if not results:
                logger.warning("No settlement-statement math rules evaluated for %s", filename)
                continue
            insert_rule_eval(filename, results, db_path)
    finally:
        conn.close()


def fetch_data(query, params, db_path=SQLITE_DB_PATH):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def fetch_summary_totals(filename, db_path=SQLITE_DB_PATH):
    placeholders = ",".join("?" for _ in SUMMARY_FIELD_IDS)
    query = f"""
        SELECT
            field,
            field_value,
            field_unformatted_value,
            validated_field_value,
            is_missing,
            row_index,
            column_index
        FROM extraction
        WHERE filename=?
          AND field_id IN ({placeholders})
    """
    rows = fetch_data(query, (filename, *SUMMARY_FIELD_IDS), db_path)
    return _organize_data(rows)


def fetch_statement_table_data(filename, db_path=SQLITE_DB_PATH):
    query = """
        SELECT
            field,
            field_value,
            field_unformatted_value,
            validated_field_value,
            is_missing,
            row_index,
            column_index
        FROM extraction
        WHERE filename=?
          AND field_id=?
          AND row_index >= 0
    """
    rows = fetch_data(query, (filename, ITEMS_FIELD_ID), db_path)
    return {ITEMS_FIELD_ID: _organize_data(rows)} if rows else {}


def _normalize_field(field, column_index):
    if not field:
        return f"Unknown Field {column_index}"

    stripped_field = field.strip()
    return FIELD_ALIASES.get(stripped_field.lower(), stripped_field)


def _organize_data(rows):
    data = defaultdict(lambda: defaultdict(dict))
    for (
        field,
        field_value,
        field_unformatted_value,
        validated_field_value,
        is_missing,
        row_index,
        column_index,
    ) in rows:
        normalized_field = _normalize_field(field, column_index)
        data[row_index][normalized_field] = {
            "value": first_nonblank(
                validated_field_value,
                field_value,
                field_unformatted_value,
            ),
            "is_missing": bool(is_missing),
            "column_index": column_index,
        }
    return data


def first_nonblank(*values):
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return values[-1] if values else None


def clean_numeric_value(value):
    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = str(value).strip()
    if not text:
        return Decimal("0")

    is_parenthetical_negative = text.startswith("(") and text.endswith(")")
    cleaned_value = re.sub(r"[^\d.-]", "", text)
    is_negative = is_parenthetical_negative or "-" in cleaned_value
    cleaned_value = cleaned_value.replace("-", "")

    if cleaned_value in {"", "."}:
        logger.warning("Could not parse numeric value from: %s", value)
        return Decimal("0")

    try:
        number = Decimal(cleaned_value)
    except InvalidOperation:
        logger.warning("Could not parse numeric value from: %s", value)
        return Decimal("0")

    return -number if is_negative else number


def evaluate_settlement_statement_rules(summary_totals, line_items_by_field_id):
    subtotal_debits = first_present_amount(summary_totals, SUBTOTAL_DEBITS_FIELDS)
    subtotal_credits = first_present_amount(summary_totals, SUBTOTAL_CREDITS_FIELDS)
    total_debits = first_present_amount(summary_totals, TOTAL_DEBITS_FIELDS)
    total_credits = first_present_amount(summary_totals, TOTAL_CREDITS_FIELDS)
    due_from_borrower_entries = present_amount_entries(
        summary_totals,
        DUE_FROM_BORROWER_FIELDS,
    )
    due_to_borrower_entries = present_amount_entries(
        summary_totals,
        DUE_TO_BORROWER_FIELDS,
    )
    due_from_borrower = first_entry_amount(due_from_borrower_entries)
    due_to_borrower = first_entry_amount(due_to_borrower_entries)
    rollup_amounts = collect_present_amounts(
        summary_totals,
        (
            SUBTOTAL_DEBITS_FIELDS
            + SUBTOTAL_CREDITS_FIELDS
            + TOTAL_DEBITS_FIELDS
            + TOTAL_CREDITS_FIELDS
        ),
    )

    debit_stats = line_item_amount_stats(
        line_items_by_field_id,
        DEBIT_AMOUNT_FIELD,
        rollup_amounts,
    )
    credit_stats = line_item_amount_stats(
        line_items_by_field_id,
        CREDIT_AMOUNT_FIELD,
        rollup_amounts,
    )
    line_item_debits = debit_stats["total"]
    line_item_credits = credit_stats["total"]
    (
        debit_line_expected,
        debit_line_expected_source,
        debit_fallback_adjustment,
    ) = subtotal_or_total_fallback(
        subtotal_debits,
        total_debits,
        line_item_debits,
        balance_amount=due_to_borrower,
        subtotal_source_name="subtotal_debits",
        total_source_name="total_debits_fallback",
        adjusted_total_source_name="total_debits_minus_due_to_borrower_fallback",
    )
    (
        credit_line_expected,
        credit_line_expected_source,
        credit_fallback_adjustment,
    ) = subtotal_or_total_fallback(
        subtotal_credits,
        total_credits,
        line_item_credits,
        balance_amount=due_from_borrower,
        subtotal_source_name="subtotal_credits",
        total_source_name="total_credits_fallback",
        adjusted_total_source_name="total_credits_minus_due_from_borrower_fallback",
    )
    due_from_borrower_source = None
    due_to_borrower_source = None
    if (
        due_from_borrower is None
        and subtotal_credits is not None
        and total_credits is not None
    ):
        due_from_borrower = inferred_between_subtotal_and_total_amount(
            line_items_by_field_id,
            CREDIT_AMOUNT_FIELD,
            total_credits - subtotal_credits,
        )
        if due_from_borrower is not None:
            due_from_borrower_source = "between_subtotals_and_totals"

    if (
        due_to_borrower is None
        and subtotal_debits is not None
        and total_debits is not None
    ):
        due_to_borrower = inferred_between_subtotal_and_total_amount(
            line_items_by_field_id,
            DEBIT_AMOUNT_FIELD,
            total_debits - subtotal_debits,
        )
        if due_to_borrower is not None:
            due_to_borrower_source = "between_subtotals_and_totals"

    results = {}
    results["borrower_balance_fields_are_mutually_exclusive"] = (
        borrower_balance_exclusivity_result(
            due_from_borrower_entries,
            due_to_borrower_entries,
        )
    )

    if debit_line_expected is not None:
        results["debit_amounts_equal_subtotal_debits"] = build_rule_result(
            debit_line_expected,
            line_item_debits,
            failure_reason=subtotal_rule_failure_reason(debit_stats),
            details=line_item_rule_details(
                debit_line_expected,
                line_item_debits,
                debit_stats,
                expected_total_source=debit_line_expected_source,
                expected_total_fallback=subtotal_debits is None,
                fallback_adjustment_amount=debit_fallback_adjustment,
            ),
        )

    if credit_line_expected is not None:
        results["credit_amounts_equal_subtotal_credits"] = build_rule_result(
            credit_line_expected,
            line_item_credits,
            failure_reason=subtotal_rule_failure_reason(credit_stats),
            details=line_item_rule_details(
                credit_line_expected,
                line_item_credits,
                credit_stats,
                expected_total_source=credit_line_expected_source,
                expected_total_fallback=subtotal_credits is None,
                fallback_adjustment_amount=credit_fallback_adjustment,
            ),
        )

    if subtotal_debits is not None and total_debits is not None:
        actual_total_debits = subtotal_debits + (due_to_borrower or Decimal("0"))
        results["total_debits_equal_subtotal_debits_plus_due_to_borrower"] = (
            build_rule_result(
                total_debits,
                actual_total_debits,
                failure_reason="subtotal_plus_due_to_borrower_mismatch",
                details=amount_rule_details(
                    total_debits,
                    actual_total_debits,
                    due_to_borrower=due_to_borrower,
                    due_to_borrower_source=due_to_borrower_source,
                ),
            )
        )

    if subtotal_credits is not None and total_credits is not None:
        actual_total_credits = subtotal_credits + (due_from_borrower or Decimal("0"))
        results["total_credits_equal_subtotal_credits_plus_due_from_borrower"] = (
            build_rule_result(
                total_credits,
                actual_total_credits,
                failure_reason="subtotal_plus_due_from_borrower_mismatch",
                details=amount_rule_details(
                    total_credits,
                    actual_total_credits,
                    due_from_borrower=due_from_borrower,
                    due_from_borrower_source=due_from_borrower_source,
                ),
            )
        )

    if total_debits is not None and total_credits is not None:
        adjusted_credits = adjusted_total_credits(
            total_debits,
            total_credits,
            due_from_borrower,
            due_to_borrower,
        )
        results["total_debits_balance_total_credits"] = build_rule_result(
            total_debits,
            adjusted_credits,
            failure_reason="total_debits_total_credits_mismatch",
            details=amount_rule_details(
                total_debits,
                adjusted_credits,
                total_credits=total_credits,
                due_from_borrower=due_from_borrower,
                due_from_borrower_source=due_from_borrower_source,
                due_to_borrower=due_to_borrower,
                due_to_borrower_source=due_to_borrower_source,
            ),
        )

    for rule_name, result in results.items():
        log_rule_result(rule_name, result)

    return results


def adjusted_total_credits(
    total_debits,
    total_credits,
    due_from_borrower,
    due_to_borrower,
):
    if due_from_borrower is None and due_to_borrower is None:
        return total_credits

    difference = total_debits - total_credits
    if (
        difference > 0
        and due_from_borrower is not None
        and amounts_match(abs(difference), abs(due_from_borrower))
    ):
        return total_credits + abs(due_from_borrower)
    if (
        difference < 0
        and due_to_borrower is not None
        and amounts_match(abs(difference), abs(due_to_borrower))
    ):
        return total_credits - abs(due_to_borrower)
    return total_credits


def total_field_fallback(total_source):
    if total_source is None:
        return None
    return total_source


def subtotal_or_total_fallback(
    subtotal_amount,
    total_amount,
    actual_line_total,
    balance_amount=None,
    subtotal_source_name=None,
    total_source_name=None,
    adjusted_total_source_name=None,
):
    if subtotal_amount is not None:
        return subtotal_amount, subtotal_source_name, None
    if total_amount is None:
        return None, None, None
    if balance_amount is not None:
        adjustment = abs(balance_amount)
        adjusted_total = total_amount - adjustment
        if amounts_match(actual_line_total, adjusted_total):
            return adjusted_total, adjusted_total_source_name, adjustment
    if amounts_match(actual_line_total, total_amount):
        return total_field_fallback(total_amount), total_source_name, None
    return None, None, None


def sum_line_item_amounts(
    line_items_by_field_id,
    amount_field,
    subtotal_amounts=None,
):
    return line_item_amount_stats(
        line_items_by_field_id,
        amount_field,
        subtotal_amounts,
    )["total"]


def line_item_amount_stats(
    line_items_by_field_id,
    amount_field,
    subtotal_amounts=None,
):
    total = Decimal("0")
    subtotal_amounts = subtotal_amounts or set()
    included_rows = []
    skipped_rows = []
    row_count = 0

    for field_id, line_items in line_items_by_field_id.items():
        for row_index, fields in sorted(line_items.items()):
            if not row_has_line_item_data(fields):
                continue

            row_count += 1
            amount_info = fields.get(amount_field)
            amount = (
                clean_numeric_value(amount_info.get("value"))
                if is_present(amount_info)
                else None
            )
            row = line_item_row_summary(field_id, row_index, fields, amount_field, amount)

            if should_skip_line_item_row(
                row_index,
                fields,
                line_items,
                subtotal_amounts,
            ):
                if amount is not None:
                    skipped_rows.append(row)
                continue

            if amount is None:
                continue

            total += amount
            included_rows.append(row)

    return {
        "amount_field": amount_field,
        "total": total,
        "row_count": row_count,
        "included_count": len(included_rows),
        "skipped_count": len(skipped_rows),
        "included_rows": included_rows,
        "skipped_rows": skipped_rows,
    }


def line_item_row_summary(field_id, row_index, fields, amount_field, amount):
    return {
        "field_id": field_id,
        "row_index": row_index,
        "description": normalized_field_value(fields, "Item Description"),
        "amount_field": amount_field,
        "amount": decimal_to_string(amount) if amount is not None else None,
    }


def sum_all_non_rollup_rows(line_items, amount_field, subtotal_amounts):
    total = Decimal("0")
    for row_index, fields in line_items.items():
        if should_skip_line_item_row(row_index, fields, line_items, subtotal_amounts):
            continue
        amount_info = fields.get(amount_field)
        if not is_present(amount_info):
            continue
        total += clean_numeric_value(amount_info.get("value"))
    return total


def should_skip_line_item_row(row_index, fields, line_items, subtotal_amounts):
    if is_rollup_row(fields, subtotal_amounts):
        return True

    if is_between_subtotal_and_total(row_index, line_items):
        return True

    detail_rows = [
        row_fields
        for row_fields in line_items.values()
        if row_has_line_item_data(row_fields)
    ]
    return (
        len(detail_rows) == 1
        and fields is detail_rows[0]
        and row_has_subtotal_amount(fields, subtotal_amounts)
    )


def inferred_between_subtotal_and_total_amount(
    line_items_by_field_id,
    amount_field,
    target_amount,
):
    if target_amount == Decimal("0"):
        return None

    for line_items in line_items_by_field_id.values():
        for row_index, fields in sorted(line_items.items()):
            if not is_between_subtotal_and_total(row_index, line_items):
                continue
            amount_info = fields.get(amount_field)
            if not is_present(amount_info):
                continue
            amount = clean_numeric_value(amount_info.get("value"))
            if abs(amount - target_amount) <= TOLERANCE:
                return amount
    return None


def is_between_subtotal_and_total(row_index, line_items):
    saw_subtotal = False
    for candidate_index, fields in sorted(line_items.items()):
        if candidate_index == row_index:
            return saw_subtotal and has_later_total_row(row_index, line_items)
        if is_subtotal_marker_row(fields):
            saw_subtotal = True
        if is_total_marker_row(fields):
            saw_subtotal = False
    return False


def has_later_total_row(row_index, line_items):
    return any(
        candidate_index > row_index and is_total_marker_row(fields)
        for candidate_index, fields in line_items.items()
    )


def is_subtotal_marker_row(fields):
    row_role = normalized_field_value(fields, "Row Role")
    item_description = normalized_field_value(fields, "Item Description")
    return row_role == "subtotals" or item_description == "subtotals"


def is_total_marker_row(fields):
    row_role = normalized_field_value(fields, "Row Role")
    item_description = normalized_field_value(fields, "Item Description")
    return (
        "total" in row_role
        or item_description in {"total", "totals"}
        or (
            "subtotal" not in item_description
            and "sub-total" not in item_description
            and has_rollup_total_label(item_description)
        )
    )


def row_has_line_item_data(fields):
    for field_name in ("Item Description", DEBIT_AMOUNT_FIELD, CREDIT_AMOUNT_FIELD):
        if is_present(fields.get(field_name)):
            return True
    return False


def is_rollup_row(fields, subtotal_amounts):
    row_role = normalized_field_value(fields, "Row Role")
    item_description = normalized_field_value(fields, "Item Description")

    if any(term in row_role for term in ROLLUP_ROW_ROLE_TERMS):
        return True

    if item_description in ROLLUP_ITEM_DESCRIPTIONS:
        return True

    if "subtotal" in item_description or "sub-total" in item_description:
        return True

    if has_balance_label(item_description):
        return True

    if has_unlabeled_duplicate_summary_amount(fields, subtotal_amounts):
        return True

    return (
        row_has_subtotal_amount(fields, subtotal_amounts)
        and has_rollup_total_label(item_description)
    )


def has_unlabeled_duplicate_summary_amount(fields, subtotal_amounts):
    if normalized_field_value(fields, "Item Description"):
        return False

    debit_info = fields.get(DEBIT_AMOUNT_FIELD)
    credit_info = fields.get(CREDIT_AMOUNT_FIELD)
    if not is_present(debit_info) or not is_present(credit_info):
        return False

    debit_amount = clean_numeric_value(debit_info.get("value"))
    credit_amount = clean_numeric_value(credit_info.get("value"))
    return debit_amount == credit_amount and debit_amount in subtotal_amounts


def has_balance_label(item_description):
    if not item_description:
        return False
    return any(term in item_description for term in BALANCE_ROW_TERMS)


def has_rollup_total_label(item_description):
    if not item_description:
        return False
    if item_description.startswith(NON_ROLLUP_ITEM_PREFIXES):
        return False
    return "total" in item_description


def row_has_subtotal_amount(fields, subtotal_amounts):
    if not subtotal_amounts:
        return False

    for amount_field in (DEBIT_AMOUNT_FIELD, CREDIT_AMOUNT_FIELD):
        amount_info = fields.get(amount_field)
        if not is_present(amount_info):
            continue
        if clean_numeric_value(amount_info.get("value")) in subtotal_amounts:
            return True

    return False


def normalized_field_value(fields, field_name):
    field_info = fields.get(field_name)
    if not is_present(field_info):
        return ""
    return re.sub(r"\s+", " ", str(field_info.get("value")).strip().lower())


def collect_present_amounts(rows, field_names):
    amounts = set()
    for fields in rows.values():
        for field_name in field_names:
            field_info = fields.get(field_name)
            if is_present(field_info):
                amounts.add(clean_numeric_value(field_info.get("value")))
    return amounts


def present_amount_entries(rows, field_names):
    entries = []
    for row_index, fields in rows.items():
        for field_name in field_names:
            field_info = fields.get(field_name)
            if is_present(field_info):
                entries.append(
                    {
                        "field": field_name,
                        "row_index": row_index,
                        "amount": clean_numeric_value(field_info.get("value")),
                    }
                )
    return entries


def first_entry_amount(entries):
    if not entries:
        return None
    return entries[0]["amount"]


def first_present_amount(rows, field_names):
    for fields in rows.values():
        for field_name in field_names:
            field_info = fields.get(field_name)
            if is_present(field_info):
                return clean_numeric_value(field_info.get("value"))
    return None


def is_present(field_info):
    if not field_info or field_info.get("is_missing", True):
        return False
    value = field_info.get("value")
    return value is not None and str(value).strip() != ""


def build_rule_result(
    expected_total,
    actual_total,
    failure_reason=None,
    details=None,
):
    match = abs(expected_total - actual_total) <= TOLERANCE
    return {
        "expected_total": expected_total,
        "actual_total": actual_total,
        "match": match,
        "failure_reason": None if match else failure_reason or "amount_mismatch",
        "details": details or amount_rule_details(expected_total, actual_total),
    }


def build_boolean_rule_result(match, failure_reason=None, details=None):
    return {
        "expected_total": Decimal("1"),
        "actual_total": Decimal("1") if match else Decimal("0"),
        "match": match,
        "failure_reason": None if match else failure_reason or "rule_failed",
        "details": details or {},
    }


def borrower_balance_exclusivity_result(
    due_from_borrower_entries,
    due_to_borrower_entries,
):
    match = not (due_from_borrower_entries and due_to_borrower_entries)
    return build_boolean_rule_result(
        match,
        failure_reason="multiple_borrower_balance_fields_present",
        details={
            "due_from_borrower": amount_entries_details(due_from_borrower_entries),
            "due_to_borrower": amount_entries_details(due_to_borrower_entries),
        },
    )


def amount_entries_details(entries):
    return [
        {
            "field": entry["field"],
            "row_index": entry["row_index"],
            "amount": decimal_to_string(entry["amount"]),
        }
        for entry in entries
    ]


def amounts_match(left, right):
    return abs(left - right) <= TOLERANCE


def subtotal_rule_failure_reason(stats):
    if stats["row_count"] == 0:
        return "no_item_rows_extracted"
    if stats["included_count"] == 0:
        return "no_non_rollup_item_amounts"
    return "line_item_sum_mismatch"


def line_item_rule_details(expected_total, actual_total, stats, **extra):
    difference = expected_total - actual_total
    abs_difference = abs(difference)
    return {
        **amount_rule_details(expected_total, actual_total),
        **detail_values(extra),
        "amount_field": stats["amount_field"],
        "item_row_count": stats["row_count"],
        "included_amount_row_count": stats["included_count"],
        "skipped_amount_row_count": stats["skipped_count"],
        "possible_offset_rows": rows_matching_amount(
            stats["included_rows"],
            abs_difference,
        ),
        "skipped_summary_or_rollup_rows": stats["skipped_rows"][:5],
    }


def amount_rule_details(expected_total, actual_total, **extra):
    details = {
        "difference": decimal_to_string(expected_total - actual_total),
        "absolute_difference": decimal_to_string(abs(expected_total - actual_total)),
    }
    details.update(detail_values(extra))
    return details


def detail_values(values):
    return {
        key: decimal_to_string(value) if isinstance(value, Decimal) else value
        for key, value in values.items()
        if value is not None
    }


def rows_matching_amount(rows, amount):
    return [
        row
        for row in rows
        if row.get("amount") is not None
        and clean_numeric_value(row["amount"]) == amount
    ][:5]


def decimal_to_string(value):
    return format(value, "f")


def log_rule_result(rule_name, result):
    log_method = logger.info if result["match"] else logger.error
    log_method(
        "Rule '%s' %s: Expected = %s, Actual = %s",
        rule_name,
        "PASSED" if result["match"] else "FAILED",
        result["expected_total"],
        result["actual_total"],
    )


if __name__ == "__main__":
    create_business_rule_eval_table()
    process_all_documents()
