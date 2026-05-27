from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
from io import StringIO
import json
import shutil
import sqlite3
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse

from ..config import get_settings
from ..db import connect, rows_to_dicts, table_columns

DUE_FROM_BORROWER_FIELD_IDS = [
    "due-from-borrower",
    "due-from-brorrower",
    "due-from-buyer-amount",
    "due-from-buyer-estimated-amount",
]
DUE_TO_BORROWER_FIELD_IDS = [
    "due-to-borrower",
    "due-to-brorrower",
]
CANONICAL_EVIDENCE_FIELDS = {
    "due-from-borrower": ("due-from-borrower", "Due From Borrower"),
    "due-from-brorrower": ("due-from-borrower", "Due From Borrower"),
    "due-to-borrower": ("due-to-borrower", "Due To Borrower"),
    "due-to-brorrower": ("due-to-borrower", "Due To Borrower"),
}

EVAL_RULE_SOURCES = {
    "borrower_balance_fields_are_mutually_exclusive": {
        "actual": [*DUE_FROM_BORROWER_FIELD_IDS, *DUE_TO_BORROWER_FIELD_IDS],
    },
    "debit_amounts_equal_subtotal_debits": {
        "expected": ["subtotal-debits-amount"],
        "included_amount_field": "debit-amount",
    },
    "credit_amounts_equal_subtotal_credits": {
        "expected": ["subtotal-credits-amount"],
        "included_amount_field": "credit-amount",
    },
    "total_credits_equal_subtotal_credits_plus_due_from_buyer": {
        "expected": ["total-credits-amount"],
        "actual": ["subtotal-credits-amount", *DUE_FROM_BORROWER_FIELD_IDS],
        "actual_item_amount_field": "credit-amount",
        "actual_item_description_terms": ["due from buyer", "due from borrower"],
    },
    "total_credits_equal_subtotal_credits_plus_due_from_borrower": {
        "expected": ["total-credits-amount"],
        "actual": ["subtotal-credits-amount", *DUE_FROM_BORROWER_FIELD_IDS],
        "actual_item_amount_field": "credit-amount",
        "actual_item_description_terms": ["due from borrower", "due from buyer"],
    },
    "total_debits_equal_subtotal_debits_plus_due_to_borrower": {
        "expected": ["total-debits-amount"],
        "actual": ["subtotal-debits-amount", *DUE_TO_BORROWER_FIELD_IDS],
        "actual_item_amount_field": "debit-amount",
        "actual_item_description_terms": ["due to borrower", "due to buyer"],
    },
    "total_debits_balance_total_credits": {
        "expected": ["total-debits-amount"],
        "expected_item_amount_field": "debit-amount",
        "actual": ["total-credits-amount", *DUE_FROM_BORROWER_FIELD_IDS, *DUE_TO_BORROWER_FIELD_IDS],
    },
}

REVIEW_STATUSES = {
    "unreviewed",
    "in_review",
    "reviewed",
    "ignored",
    "needs_extraction_fix",
    "added_to_training",
    "archived",
}


def health() -> dict[str, Any]:
    settings = get_settings()
    with connect(settings.db_path) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    return {"status": "ok", "db_path": str(settings.db_path), "integrity": integrity}


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT run_id FROM rule_run WHERE status = 'completed' ORDER BY completed_at DESC, run_id DESC LIMIT 1"
    ).fetchone()
    return int(row["run_id"]) if row else None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM rule_run ORDER BY started_at DESC, run_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )


def dashboard() -> dict[str, Any]:
    with connect() as conn:
        run_id = latest_run_id(conn)
        total_documents = conn.execute("SELECT COUNT(DISTINCT filename) AS count FROM extraction").fetchone()["count"]
        if _use_eval_source(conn, run_id):
            return _eval_dashboard(conn, total_documents)
        if run_id is None:
            return _empty_dashboard(total_documents)
        counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total_evaluations,
                COUNT(DISTINCT filename) AS evaluated_documents,
                SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS failed,
                ROUND(AVG(CASE WHEN rule_passed = 0 THEN absolute_difference END), 2) AS avg_failed_difference
            FROM business_rule_result
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        warnings = conn.execute(
            "SELECT COUNT(*) AS count FROM business_rule_log WHERE run_id = ? AND level = 'warning'",
            (run_id,),
        ).fetchone()["count"]
        no_rule = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM extraction e
            WHERE e.field_id = 'Statement Table > Summary Totals and Balance'
            GROUP BY e.filename
            HAVING NOT EXISTS (
                SELECT 1 FROM business_rule_result r WHERE r.run_id = ? AND r.filename = e.filename
            )
            """,
            (run_id,),
        ).fetchall()
        worst_rules = rows_to_dicts(conn.execute("SELECT * FROM v_rule_pass_rate ORDER BY pass_rate_percentage ASC").fetchall())
        recent_documents = _document_rows(conn, run_id, limit=10)
        total_evaluations = counts["total_evaluations"] or 0
        passed = counts["passed"] or 0
        return {
            "run_id": run_id,
            "total_documents": total_documents,
            "evaluated_documents": counts["evaluated_documents"] or 0,
            "no_rule_documents": len(no_rule),
            "total_evaluations": total_evaluations,
            "passed_evaluations": passed,
            "failed_evaluations": counts["failed"] or 0,
            "pass_rate": round(passed * 100.0 / total_evaluations, 2) if total_evaluations else 0,
            "warning_count": warnings,
            "average_failed_absolute_difference": counts["avg_failed_difference"] or 0,
            "worst_rules": worst_rules,
            "recent_documents": recent_documents,
            **_dashboard_review_metrics(conn, use_eval=False, run_id=run_id),
        }


def _empty_dashboard(total_documents: int) -> dict[str, Any]:
    return {
        "run_id": None,
        "total_documents": total_documents,
        "evaluated_documents": 0,
        "no_rule_documents": total_documents,
        "total_evaluations": 0,
        "passed_evaluations": 0,
        "failed_evaluations": 0,
        "pass_rate": 0,
        "warning_count": 0,
        "average_failed_absolute_difference": 0,
        "worst_rules": [],
        "recent_documents": [],
        "unreviewed_failed_documents": 0,
        "reviewed_documents": 0,
        "added_to_training_documents": 0,
        "ignored_documents": 0,
        "top_recurring_root_causes": [],
    }


def _use_eval_source(conn: sqlite3.Connection, run_id: int | None) -> bool:
    eval_count = conn.execute("SELECT COUNT(*) AS count FROM business_rule_eval").fetchone()["count"]
    if not eval_count:
        return False
    if run_id is None:
        return True
    result_count = conn.execute(
        "SELECT COUNT(*) AS count FROM business_rule_result WHERE run_id = ?",
        (run_id,),
    ).fetchone()["count"]
    return result_count == 0


def _eval_dashboard(conn: sqlite3.Connection, total_documents: int) -> dict[str, Any]:
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_evaluations,
            COUNT(DISTINCT filename) AS evaluated_documents,
            SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS passed,
            SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS failed,
            ROUND(AVG(CASE WHEN rule_passed = 0 THEN ABS(COALESCE(actual_total, 0) - COALESCE(expected_total, 0)) END), 2) AS avg_failed_difference
        FROM business_rule_eval
        """
    ).fetchone()
    no_rule = conn.execute(
        """
        SELECT e.filename
        FROM extraction e
        GROUP BY e.filename
        HAVING NOT EXISTS (
            SELECT 1 FROM business_rule_eval r WHERE r.filename = e.filename
        )
        """
    ).fetchall()
    total_evaluations = counts["total_evaluations"] or 0
    passed = counts["passed"] or 0
    return {
        "run_id": None,
        "total_documents": total_documents,
        "evaluated_documents": counts["evaluated_documents"] or 0,
        "no_rule_documents": len(no_rule),
        "total_evaluations": total_evaluations,
        "passed_evaluations": passed,
        "failed_evaluations": counts["failed"] or 0,
        "pass_rate": round(passed * 100.0 / total_evaluations, 2) if total_evaluations else 0,
        "warning_count": 0,
        "average_failed_absolute_difference": counts["avg_failed_difference"] or 0,
        "worst_rules": _eval_rule_pass_rates(conn),
        "recent_documents": _eval_document_rows(conn, sort="failed_rules", limit=10),
        **_dashboard_review_metrics(conn, use_eval=True, run_id=None),
    }


def list_documents(
    search: str | None,
    status: str | None,
    rule: str | None,
    review_status: str | None,
    warning: str | None,
    sort: str,
    direction: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    with connect() as conn:
        run_id = latest_run_id(conn)
        if _use_eval_source(conn, run_id):
            rows = _eval_document_rows(conn, search, status, rule, review_status, warning, sort, direction, limit, offset)
            total = _eval_document_total(conn, search, status, rule, review_status, warning)
            return {"items": rows, "total": total, "limit": limit, "offset": offset}
        if run_id is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        rows = _document_rows(conn, run_id, search, status, rule, review_status, warning, sort, direction, limit, offset)
        total = _document_total(conn, run_id, search, status, rule, review_status, warning)
        return {"items": rows, "total": total, "limit": limit, "offset": offset}


def _eval_rule_pass_rates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT
                rule_name,
                COUNT(*) AS total_evaluated,
                SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS total_passed,
                SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS total_failed,
                ROUND(SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate_percentage,
                ROUND(AVG(CASE WHEN rule_passed = 0 THEN ABS(COALESCE(actual_total, 0) - COALESCE(expected_total, 0)) END), 2) AS avg_absolute_difference
            FROM business_rule_eval
            GROUP BY rule_name
            ORDER BY pass_rate_percentage ASC, rule_name
            """
        ).fetchall()
    )


def _dashboard_review_metrics(conn: sqlite3.Connection, use_eval: bool, run_id: int | None) -> dict[str, Any]:
    if use_eval:
        failed_source = "business_rule_eval"
        failed_where = "rule_passed = 0"
        join_where = "r.filename = v.filename AND r.rule_name = v.rule_name"
        run_params: tuple[Any, ...] = ()
        cause_expr = "COALESCE(v.root_cause, r.failure_reason, 'unknown')" if "failure_reason" in table_columns(conn, "business_rule_eval") else "COALESCE(v.root_cause, 'unknown')"
    else:
        failed_source = "business_rule_result"
        failed_where = "r.run_id = ? AND r.rule_passed = 0"
        join_where = "r.filename = v.filename AND r.rule_name = v.rule_name"
        run_params = (run_id,)
        cause_expr = "COALESCE(v.root_cause, r.root_cause, 'unknown')"

    unreviewed_failed = conn.execute(
        f"""
        SELECT COUNT(DISTINCT r.filename) AS count
        FROM {failed_source} r
        LEFT JOIN business_rule_review v ON {join_where}
        WHERE {failed_where}
          AND COALESCE(v.status, 'unreviewed') = 'unreviewed'
        """,
        run_params,
    ).fetchone()["count"]
    review_counts = {
        row["status"]: row["count"]
        for row in conn.execute(
            """
            SELECT status, COUNT(DISTINCT filename) AS count
            FROM business_rule_review
            WHERE status IN ('reviewed', 'added_to_training', 'ignored')
            GROUP BY status
            """
        ).fetchall()
    }
    top_root_causes = rows_to_dicts(
        conn.execute(
            f"""
            SELECT {cause_expr} AS root_cause, COUNT(*) AS count, COUNT(DISTINCT r.filename) AS document_count, COUNT(*) AS occurrence_count
            FROM {failed_source} r
            LEFT JOIN business_rule_review v ON {join_where}
            WHERE {failed_where}
            GROUP BY {cause_expr}
            HAVING {cause_expr} IS NOT NULL AND {cause_expr} != ''
            ORDER BY occurrence_count DESC, document_count DESC, 1
            LIMIT 5
            """,
            run_params,
        ).fetchall()
    )
    return {
        "unreviewed_failed_documents": unreviewed_failed or 0,
        "reviewed_documents": review_counts.get("reviewed", 0),
        "added_to_training_documents": review_counts.get("added_to_training", 0),
        "ignored_documents": review_counts.get("ignored", 0),
        "top_recurring_root_causes": top_root_causes,
    }


def _eval_document_total(
    conn: sqlite3.Connection,
    search: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    review_status: str | None = None,
    warning: str | None = None,
) -> int:
    query, params = _eval_document_query(table_columns(conn, "business_rule_eval"), search, status, rule, review_status, warning, "filename", None, None, None)
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM ({query})", params).fetchone()["count"])


def _document_order(sort: str, direction: str | None) -> str:
    sql_direction = "ASC" if str(direction or "").lower() == "asc" else "DESC"
    filename_direction = sql_direction if sort == "filename" else "ASC"
    default_order = (
        f"largest_absolute_difference {sql_direction}, recurring_root_cause_count DESC, "
        "missing_evidence_score DESC, rules_failed DESC, avg_confidence ASC, avg_ocr_confidence ASC, "
        f"r.filename {filename_direction}"
    )
    return {
        "default": default_order,
        "highest_value": default_order,
        "failed_rules": f"rules_failed {sql_direction}, largest_absolute_difference DESC, r.filename ASC",
        "largest_absolute_difference": f"largest_absolute_difference {sql_direction}, rules_failed DESC, r.filename ASC",
        "filename": f"r.filename {sql_direction}",
        "pass_rate": f"pass_rate {sql_direction}, r.filename ASC",
        "warning_count": f"warning_count {sql_direction}, r.filename ASC",
        "review_status": f"review_status {sql_direction}, r.filename ASC",
    }.get(sort, default_order)


def _eval_document_rows(
    conn: sqlite3.Connection,
    search: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    review_status: str | None = None,
    warning: str | None = None,
    sort: str = "failed_rules",
    direction: str | None = None,
    limit: int | None = 25,
    offset: int | None = 0,
) -> list[dict[str, Any]]:
    query, params = _eval_document_query(table_columns(conn, "business_rule_eval"), search, status, rule, review_status, warning, sort, direction, limit, offset)
    return rows_to_dicts(conn.execute(query, params).fetchall())


def _eval_document_query(
    eval_columns: set[str],
    search: str | None,
    status: str | None,
    rule: str | None,
    review_status: str | None,
    warning: str | None,
    sort: str,
    direction: str | None,
    limit: int | None,
    offset: int | None,
) -> tuple[str, list[Any]]:
    root_cause_expr = "MAX(r.failure_reason)" if "failure_reason" in eval_columns else "'unknown'"
    where: list[str] = []
    params: list[Any] = []
    having: list[str] = []
    if search:
        where.append("r.filename LIKE ?")
        params.append(f"%{search}%")
    if rule:
        if status == "failed":
            where.append("r.filename IN (SELECT filename FROM business_rule_eval WHERE rule_name = ? AND rule_passed = 0)")
        elif status == "passed":
            where.append("r.filename IN (SELECT filename FROM business_rule_eval WHERE rule_name = ? AND rule_passed = 1)")
        else:
            where.append("r.filename IN (SELECT filename FROM business_rule_eval WHERE rule_name = ?)")
        params.append(rule)
    elif status == "failed":
        where.append("r.filename IN (SELECT filename FROM business_rule_eval WHERE rule_passed = 0)")
    elif status == "passed":
        where.append("r.filename NOT IN (SELECT filename FROM business_rule_eval WHERE rule_passed = 0)")
    if warning:
        where.append("0 = 1")
    recurring_expr = (
        "MAX((SELECT COUNT(*) FROM business_rule_eval rr "
        "WHERE rr.rule_passed = 0 AND COALESCE(rr.failure_reason, 'unknown') = COALESCE(r.failure_reason, 'unknown')))"
        if "failure_reason" in eval_columns
        else "0"
    )
    order = _document_order(sort, direction)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    if review_status:
        having.append("COALESCE(MAX(v.status), 'unreviewed') = ?")
    sql = f"""
        SELECT
            r.filename,
            MAX(e.document_type_id) AS document_type_id,
            COUNT(*) AS rules_evaluated,
            SUM(CASE WHEN r.rule_passed = 1 THEN 1 ELSE 0 END) AS rules_passed,
            SUM(CASE WHEN r.rule_passed = 0 THEN 1 ELSE 0 END) AS rules_failed,
            ROUND(SUM(CASE WHEN r.rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate,
            MAX(ABS(COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0))) AS largest_absolute_difference,
            {recurring_expr} AS recurring_root_cause_count,
            MAX(CASE WHEN r.rule_passed = 0 AND (r.expected_total IS NULL OR r.actual_total IS NULL) THEN 1 ELSE 0 END) AS missing_evidence_score,
            0 AS warning_count,
            AVG(e.confidence) AS avg_confidence,
            AVG(e.ocr_confidence) AS avg_ocr_confidence,
            COALESCE(MAX(v.status), 'unreviewed') AS review_status,
            COALESCE(MAX(v.root_cause), {root_cause_expr}, 'unknown') AS root_cause
        FROM business_rule_eval r
        LEFT JOIN (
            SELECT
                filename,
                MAX(document_type_id) AS document_type_id,
                AVG(confidence) AS confidence,
                AVG(ocr_confidence) AS ocr_confidence
            FROM extraction
            GROUP BY filename
        ) e ON e.filename = r.filename
        LEFT JOIN business_rule_review v ON v.filename = r.filename
        {where_sql}
        GROUP BY r.filename
        {"HAVING " + " AND ".join(having) if having else ""}
        ORDER BY {order}
    """
    if review_status:
        params.append(review_status)
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        sql += " OFFSET ?"
        params.append(offset)
    return sql, params


def _document_total(
    conn: sqlite3.Connection,
    run_id: int,
    search: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    review_status: str | None = None,
    warning: str | None = None,
) -> int:
    query, params = _document_query(run_id, search, status, rule, review_status, warning, "filename", None, None, None)
    count_sql = f"SELECT COUNT(*) AS count FROM ({query})"
    return int(conn.execute(count_sql, params).fetchone()["count"])


def _document_rows(
    conn: sqlite3.Connection,
    run_id: int,
    search: str | None = None,
    status: str | None = None,
    rule: str | None = None,
    review_status: str | None = None,
    warning: str | None = None,
    sort: str = "failed_rules",
    direction: str | None = None,
    limit: int | None = 25,
    offset: int | None = 0,
) -> list[dict[str, Any]]:
    query, params = _document_query(run_id, search, status, rule, review_status, warning, sort, direction, limit, offset)
    return rows_to_dicts(conn.execute(query, params).fetchall())


def _document_query(
    run_id: int,
    search: str | None,
    status: str | None,
    rule: str | None,
    review_status: str | None,
    warning: str | None,
    sort: str,
    direction: str | None,
    limit: int | None,
    offset: int | None,
) -> tuple[str, list[Any]]:
    where = ["r.run_id = ?"]
    params: list[Any] = [run_id]
    having: list[str] = []
    if search:
        where.append("r.filename LIKE ?")
        params.append(f"%{search}%")
    if rule:
        if status == "failed":
            where.append("r.filename IN (SELECT filename FROM business_rule_result WHERE run_id = ? AND rule_name = ? AND rule_passed = 0)")
        elif status == "passed":
            where.append("r.filename IN (SELECT filename FROM business_rule_result WHERE run_id = ? AND rule_name = ? AND rule_passed = 1)")
        else:
            where.append("r.filename IN (SELECT filename FROM business_rule_result WHERE run_id = ? AND rule_name = ?)")
        params.extend([run_id, rule])
    elif status == "failed":
        where.append("r.filename IN (SELECT filename FROM business_rule_result WHERE run_id = ? AND rule_passed = 0)")
        params.append(run_id)
    elif status == "passed":
        where.append("r.filename NOT IN (SELECT filename FROM business_rule_result WHERE run_id = ? AND rule_passed = 0)")
        params.append(run_id)
    if warning:
        where.append("r.filename IN (SELECT filename FROM business_rule_log WHERE run_id = ? AND level = 'warning' AND event_type = ?)")
        params.extend([run_id, warning])
    if review_status:
        having.append("COALESCE(MAX(v.status), 'unreviewed') = ?")
    order = _document_order(sort, direction)
    sql = f"""
        SELECT
            r.filename,
            MAX(d.document_type_id) AS document_type_id,
            COUNT(r.result_id) AS rules_evaluated,
            SUM(CASE WHEN r.rule_passed = 1 THEN 1 ELSE 0 END) AS rules_passed,
            SUM(CASE WHEN r.rule_passed = 0 THEN 1 ELSE 0 END) AS rules_failed,
            ROUND(SUM(CASE WHEN r.rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate,
            MAX(r.absolute_difference) AS largest_absolute_difference,
            (
                SELECT COUNT(*)
                FROM business_rule_log l
                WHERE l.run_id = ? AND l.filename = r.filename AND l.level = 'warning'
            ) AS warning_count,
            MAX((
                SELECT COUNT(*)
                FROM business_rule_result rr
                WHERE rr.run_id = ? AND rr.rule_passed = 0 AND COALESCE(rr.root_cause, 'unknown') = COALESCE(r.root_cause, 'unknown')
            )) AS recurring_root_cause_count,
            MAX(CASE WHEN r.rule_passed = 0 AND (r.expected_total IS NULL OR r.actual_total IS NULL) THEN 1 ELSE 0 END) AS missing_evidence_score,
            (SELECT AVG(e.confidence) FROM extraction e WHERE e.filename = r.filename) AS avg_confidence,
            (SELECT AVG(e.ocr_confidence) FROM extraction e WHERE e.filename = r.filename) AS avg_ocr_confidence,
            COALESCE(MAX(v.status), 'unreviewed') AS review_status,
            COALESCE(MAX(v.root_cause), MAX(r.root_cause)) AS root_cause
        FROM business_rule_result r
        LEFT JOIN document_registry d ON d.filename = r.filename
        LEFT JOIN business_rule_review v ON v.filename = r.filename
        WHERE {" AND ".join(where)}
        GROUP BY r.filename
        {"HAVING " + " AND ".join(having) if having else ""}
        ORDER BY {order}
    """
    params = [run_id, run_id, *params]
    if review_status:
        params.append(review_status)
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        sql += " OFFSET ?"
        params.append(offset)
    return sql, params


def document_detail(filename: str) -> dict[str, Any]:
    with connect() as conn:
        if _use_eval_source(conn, latest_run_id(conn)):
            return _eval_document_detail(conn, filename)
        row = conn.execute("SELECT * FROM document_registry WHERE filename = ?", (filename,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"code": "document_not_found", "message": "Document not found"})
        rules = rows_to_dicts(
            conn.execute(
                """
                SELECT r.*, COALESCE(v.status, 'unreviewed') AS review_status, v.notes AS review_notes,
                       COALESCE(v.root_cause, r.root_cause) AS review_root_cause
                FROM business_rule_result r
                LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
                WHERE r.filename = ? AND r.run_id = ?
                ORDER BY r.rule_passed ASC, r.absolute_difference DESC, r.rule_name
                """,
                (filename, row["latest_run_id"]),
            ).fetchall()
        )
        return {"document": dict(row), "rules": rules}


def _eval_document_detail(conn: sqlite3.Connection, filename: str) -> dict[str, Any]:
    exists = conn.execute("SELECT 1 FROM business_rule_eval WHERE filename = ? LIMIT 1", (filename,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail={"code": "document_not_found", "message": "Document not found"})
    extraction = conn.execute(
        """
        SELECT MAX(document_type_id) AS document_type_id, MAX(page_count) AS page_count
        FROM extraction
        WHERE filename = ?
        """,
        (filename,),
    ).fetchone()
    settings = get_settings()
    document = {
        "filename": filename,
        "document_type_id": extraction["document_type_id"] if extraction else None,
        "document_path": str(settings.document_root / filename),
        "page_count": extraction["page_count"] if extraction else None,
        "has_coordinates": 0,
        "latest_run_id": None,
    }
    rules = _eval_rules(conn, filename)
    return {"document": document, "rules": rules}


def _eval_rules(conn: sqlite3.Connection, filename: str) -> list[dict[str, Any]]:
    eval_columns = table_columns(conn, "business_rule_eval")
    failure_expr = "r.failure_reason" if "failure_reason" in eval_columns else "NULL"
    rows = rows_to_dicts(
        conn.execute(
            f"""
            SELECT
                0 AS result_id,
                NULL AS run_id,
                r.filename,
                r.rule_name,
                r.expected_total,
                r.actual_total,
                COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0) AS difference,
                ABS(COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0)) AS absolute_difference,
                COALESCE(d.tolerance, 0.01) AS tolerance,
                r.rule_passed,
                COALESCE({failure_expr}, 'unknown') AS root_cause,
                CASE
                    WHEN r.rule_passed = 1 THEN 'Rule passed.'
                    ELSE 'Rule failed.'
                END AS summary,
                COALESCE(v.status, 'unreviewed') AS review_status,
                v.notes AS review_notes,
                COALESCE(v.root_cause, {failure_expr}, 'unknown') AS review_root_cause
            FROM business_rule_eval r
            LEFT JOIN rule_definition d ON d.rule_name = r.rule_name
            LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
            WHERE r.filename = ?
            ORDER BY r.rule_passed ASC, absolute_difference DESC, r.rule_name
            """,
            (filename,),
        ).fetchall()
    )
    return rows


def document_file(filename: str):
    settings = get_settings()
    root = settings.document_root.resolve()
    path = _resolve_document_file(root, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "document_file_missing", "message": "Document file is not present under document root"})
    return FileResponse(path, media_type="application/pdf" if path.suffix.lower() == ".pdf" else None)


def copy_document_to_training_exception(filename: str, rule_name: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    root = settings.document_root.resolve()
    copied = _copy_exception_file(root, filename)
    queued = False
    with connect() as conn:
        failed_rule = _rule_totals(conn, filename, rule_name) if rule_name else _first_failed_rule_for_document(conn, filename)
        if failed_rule:
            _upsert_training_exception_queue(
                conn,
                filename,
                rule_name or failed_rule["rule_name"],
                failed_rule.get("root_cause"),
                "",
                copied["exception_path"],
                copied["already_exists"],
                "added_to_training",
                failed_rule.get("expected_total"),
                failed_rule.get("actual_total"),
            )
            conn.commit()
            queued = True
    return {
        "filename": filename,
        "source_path": copied["source_path"],
        "exception_path": copied["exception_path"],
        "already_exists": copied["already_exists"],
        "rule_name": rule_name or (failed_rule["rule_name"] if failed_rule else None),
        "queued": queued,
    }


def archive_document(filename: str, rule_name: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    root = settings.document_root.resolve()
    source = _resolve_document_file(root, filename)
    if not source.exists():
        raise HTTPException(status_code=404, detail={"code": "document_file_missing", "message": "Document file is not present under document root"})
    archive_dir = (root / "archive").resolve()
    _ensure_under_document_root(root, archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = _archive_destination(archive_dir, source.name)
    _ensure_under_document_root(root, destination)
    shutil.move(str(source), str(destination))

    archived_rule = rule_name
    with connect() as conn:
        if archived_rule is None:
            failed_rule = _first_failed_rule_for_document(conn, filename)
            archived_rule = failed_rule["rule_name"] if failed_rule else None
        conn.execute("DELETE FROM training_exception_queue WHERE filename = ?", (filename,))
        conn.commit()
    if archived_rule:
        save_review(filename, archived_rule, {"status": "archived", "root_cause": "bad training data", "notes": ""})

    return {
        "filename": filename,
        "rule_name": archived_rule,
        "source_path": str(source),
        "archive_path": str(destination),
    }


def _archive_destination(archive_dir: Path, filename: str) -> Path:
    destination = archive_dir / filename
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    candidate = archive_dir / f"{stem}-{timestamp}{suffix}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = archive_dir / f"{stem}-{timestamp}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _copy_exception_file(root: Path, filename: str) -> dict[str, Any]:
    source = _resolve_document_file(root, filename)
    if not source.exists():
        raise HTTPException(status_code=404, detail={"code": "document_file_missing", "message": "Document file is not present under document root"})
    exceptions_dir = (root / "exceptions").resolve()
    _ensure_under_document_root(root, exceptions_dir)
    exceptions_dir.mkdir(parents=True, exist_ok=True)
    destination = (exceptions_dir / source.name).resolve()
    _ensure_under_document_root(root, destination)
    already_exists = destination.exists()
    if source != destination:
        shutil.copy2(source, destination)
    return {"source_path": str(source), "exception_path": str(destination), "already_exists": already_exists}


def _resolve_document_file(root: Path, filename: str) -> Path:
    path = (root / filename).resolve()
    _ensure_under_document_root(root, path)
    if path.exists() and path.is_file():
        return path

    basename = Path(filename).name
    for match in root.rglob(basename):
        resolved = match.resolve()
        try:
            _ensure_under_document_root(root, resolved)
        except HTTPException:
            continue
        if resolved.is_file():
            return resolved
    return path


def _ensure_under_document_root(root: Path, path: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "unsafe_path", "message": "Requested path is outside document root"})


def evaluations(filename: str) -> list[dict[str, Any]]:
    return document_detail(filename)["rules"]


def explanation(filename: str, rule_name: str) -> dict[str, Any]:
    with connect() as conn:
        if _use_eval_source(conn, latest_run_id(conn)):
            return _eval_explanation(conn, filename, rule_name)
        result = conn.execute(
            """
            SELECT r.*, d.label, d.formula, COALESCE(v.status, 'unreviewed') AS review_status,
                   v.notes AS review_notes, COALESCE(v.root_cause, r.root_cause) AS review_root_cause
            FROM business_rule_result r
            LEFT JOIN rule_definition d ON d.rule_name = r.rule_name
            LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
            WHERE r.filename = ? AND r.rule_name = ?
            ORDER BY r.run_id DESC
            LIMIT 1
            """,
            (filename, rule_name),
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail={"code": "rule_not_found", "message": "Rule result not found"})
        details = rows_to_dicts(
            conn.execute(
                """
                SELECT * FROM business_rule_eval_detail
                WHERE result_id = ?
                ORDER BY
                    CASE detail_type
                        WHEN 'computed_value' THEN 1
                        WHEN 'expected_source' THEN 2
                        WHEN 'included_row' THEN 3
                        WHEN 'actual_source' THEN 4
                        WHEN 'excluded_row' THEN 5
                        ELSE 6
                    END,
                    row_index,
                    column_index
                """,
                (result["result_id"],),
            ).fetchall()
        )
        for detail in details:
            detail["bbox"] = json.loads(detail["bbox_json"]) if detail.get("bbox_json") else None
            detail["metadata"] = json.loads(detail["metadata_json"]) if detail.get("metadata_json") else None
        details = _with_synthesized_missing_details(conn, dict(result), details)
        logs = rows_to_dicts(
            conn.execute(
                "SELECT * FROM business_rule_log WHERE run_id = ? AND filename = ? ORDER BY log_id",
                (result["run_id"], filename),
            ).fetchall()
        )
        return {
            "result": dict(result),
            "details": details,
            "logs": logs,
            "root_cause_suggestions": _root_cause_suggestions(dict(result), details, logs),
            "suggested_root_causes": _root_cause_suggestion_labels(dict(result), details, logs),
        }


def _eval_explanation(conn: sqlite3.Connection, filename: str, rule_name: str) -> dict[str, Any]:
    eval_columns = table_columns(conn, "business_rule_eval")
    failure_expr = "r.failure_reason" if "failure_reason" in eval_columns else "NULL"
    details_expr = "r.details" if "details" in eval_columns else "NULL"
    result = conn.execute(
        f"""
        SELECT
            0 AS result_id,
            NULL AS run_id,
            r.filename,
            r.rule_name,
            r.expected_total,
            r.actual_total,
            COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0) AS difference,
            ABS(COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0)) AS absolute_difference,
            COALESCE(d.tolerance, 0.01) AS tolerance,
            r.rule_passed,
            COALESCE({failure_expr}, 'unknown') AS root_cause,
            CASE
                WHEN r.rule_passed = 1 THEN 'Rule passed.'
                ELSE 'Rule failed.'
            END AS summary,
            d.label,
            d.formula,
            COALESCE(v.status, 'unreviewed') AS review_status,
            v.notes AS review_notes,
            COALESCE(v.root_cause, {failure_expr}, 'unknown') AS review_root_cause,
            {details_expr} AS eval_details_json
        FROM business_rule_eval r
        LEFT JOIN rule_definition d ON d.rule_name = r.rule_name
        LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
        WHERE r.filename = ? AND r.rule_name = ?
        LIMIT 1
        """,
        (filename, rule_name),
    ).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail={"code": "rule_not_found", "message": "Rule result not found"})
    result_dict = dict(result)
    eval_details = _parse_eval_details(result_dict.pop("eval_details_json", None))
    details = [
        *_eval_computed_details(result_dict, eval_details),
        *_eval_extraction_details(conn, result_dict, eval_details),
    ]
    return {
        "result": result_dict,
        "details": details,
        "logs": [],
        **_eval_diagnosis(eval_details),
        "root_cause_suggestions": _root_cause_suggestions(result_dict, details, []),
        "suggested_root_causes": _root_cause_suggestion_labels(result_dict, details, []),
    }


def _with_synthesized_missing_details(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_config = EVAL_RULE_SOURCES.get(str(result.get("rule_name")))
    if not source_config:
        return details
    expected_types = {"computed_value", "expected_source"}
    if source_config.get("actual"):
        expected_types.add("actual_source")
    if source_config.get("included_amount_field"):
        expected_types.add("included_row")
    present_types = {str(detail.get("detail_type")) for detail in details}
    missing_types = expected_types - present_types
    if not missing_types:
        return details

    eval_details = _eval_scorecard_details(conn, str(result["filename"]), str(result["rule_name"]))
    synthesized = [
        detail
        for detail in (
            _eval_computed_details(result, eval_details)
            + _eval_extraction_details(conn, result, eval_details)
        )
        if detail.get("detail_type") in missing_types
    ]
    return [*details, *synthesized]


def _root_cause_suggestions(
    result: dict[str, Any],
    details: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    def add(code: str, label: str, confidence: str, reason: str) -> None:
        if code not in {item["code"] for item in suggestions}:
            suggestions.append({"code": code, "label": label, "confidence": confidence, "reason": reason})

    rule_name = str(result.get("rule_name") or "")
    root_cause = str(result.get("root_cause") or result.get("review_root_cause") or "").lower()
    absolute_difference = float(result.get("absolute_difference") or 0)
    actual_sources = [detail for detail in details if detail.get("detail_type") == "actual_source"]
    included_rows = [detail for detail in details if detail.get("detail_type") == "included_row"]
    excluded_rows = [detail for detail in details if detail.get("detail_type") == "excluded_row"]

    if ("due_from_borrower" in rule_name or "due_from_buyer" in rule_name) and not any(
        detail.get("source_field_id") in DUE_FROM_BORROWER_FIELD_IDS
        and detail.get("amount") not in (None, 0)
        for detail in actual_sources
    ):
        if "due_from_buyer" in rule_name:
            add("missing_due_from_buyer", "Missing due-from-buyer row", "high", "The rule needs due-from-buyer evidence, but no non-zero source amount was found.")
        else:
            add("missing_due_from_borrower", "Missing due-from-borrower field", "high", "The rule needs due-from-borrower evidence, but no non-zero source amount was found.")

    if excluded_rows or any(
        isinstance(detail.get("metadata"), dict) and detail["metadata"].get("skipped_summary_or_rollup_rows")
        for detail in details
    ):
        add("rollup_row_excluded", "Rollup row excluded", "medium", "One or more subtotal or rollup-like rows were excluded from the computed evidence.")

    if any(_looks_like_rollup_detail(detail) for detail in included_rows):
        add("rollup_row_included", "Rollup row included", "medium", "Included evidence contains subtotal/total language that may double count a rollup row.")

    if absolute_difference > 0 and ("subtotal" in root_cause or any("subtotal" in str(detail.get("reason") or "").lower() for detail in details)):
        add("subtotal_mismatch", "Subtotal mismatch", "high", "The expected and actual totals differ and the failure reason points at subtotal evidence.")
    elif absolute_difference > 0 and any(detail.get("evidence_role") == "expected_total" for detail in details):
        add("subtotal_mismatch", "Subtotal mismatch", "medium", "The rule has a non-zero difference against a subtotal or expected-total source.")

    if any(log.get("event_type") == "numeric_parse_failure" for log in logs) or any(
        detail.get("amount") is None and detail.get("raw_value") not in (None, "") for detail in details
    ):
        add("parse_failure", "Parse failure", "high", "Evidence contains an unparsed numeric value or a numeric parse warning.")

    if not included_rows and any(name in rule_name for name in ("debit_amounts", "credit_amounts")):
        add("missing_table_rows", "Missing table rows", "high", "The rule depends on line-item rows, but no included item evidence was found.")

    return suggestions


def _root_cause_suggestion_labels(
    result: dict[str, Any],
    details: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> list[str]:
    return [suggestion["label"] for suggestion in _root_cause_suggestions(result, details, logs)]


def _looks_like_rollup_detail(detail: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "").lower()
        for value in (
            detail.get("source_field"),
            detail.get("source_field_id"),
            detail.get("raw_value"),
            detail.get("reason"),
        )
    )
    return any(term in text for term in ("subtotal", "sub total", "total", "summary", "rollup"))


def _eval_scorecard_details(conn: sqlite3.Connection, filename: str, rule_name: str) -> dict[str, Any]:
    eval_columns = table_columns(conn, "business_rule_eval")
    if "details" not in eval_columns:
        return {}
    row = conn.execute(
        "SELECT details FROM business_rule_eval WHERE filename = ? AND rule_name = ? LIMIT 1",
        (filename, rule_name),
    ).fetchone()
    return _parse_eval_details(row["details"] if row else None)


def _parse_eval_details(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_details": raw}
    return parsed if isinstance(parsed, dict) else {"details": parsed}


def _eval_diagnosis(eval_details: dict[str, Any]) -> dict[str, Any]:
    diagnosis = eval_details.get("diagnosis")
    diagnosis_evidence = eval_details.get("diagnosis_evidence")
    return {
        "diagnosis": diagnosis if isinstance(diagnosis, dict) else None,
        "diagnosis_evidence": diagnosis_evidence if isinstance(diagnosis_evidence, dict) else None,
    }


def _eval_computed_details(result: dict[str, Any], eval_details: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    values = {
        "expected_total": result.get("expected_total"),
        "actual_total": result.get("actual_total"),
        "difference": result.get("difference"),
        "absolute_difference": result.get("absolute_difference"),
    }
    for index, (role, value) in enumerate(values.items(), start=1):
        rows.append(
            {
                "detail_id": index,
                "result_id": result.get("result_id"),
                "run_id": result.get("run_id"),
                "filename": result.get("filename"),
                "rule_name": result.get("rule_name"),
                "detail_type": "computed_value",
                "evidence_role": role,
                "source_field_id": None,
                "source_field": None,
                "row_index": None,
                "column_index": None,
                "raw_value": None,
                "normalized_value": None if value is None else str(value),
                "amount": value,
                "page_number": None,
                "bbox": None,
                "reason": None,
                "severity": "info",
                "metadata": eval_details or None,
            }
        )
    return rows


def _eval_extraction_details(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    eval_details: dict[str, Any],
) -> list[dict[str, Any]]:
    source_config = EVAL_RULE_SOURCES.get(str(result.get("rule_name")))
    if not source_config:
        return []
    detail_id = 100
    rows: list[dict[str, Any]] = []
    for field_id in source_config.get("expected", []):
        for extraction in _eval_field_rows(conn, str(result["filename"]), field_id):
            detail_id += 1
            rows.append(_eval_detail_row(detail_id, result, "expected_source", "expected_total", extraction, _money_value(extraction)))
    for field_id in source_config.get("actual", []):
        for extraction in _eval_field_rows(conn, str(result["filename"]), field_id):
            detail_id += 1
            rows.append(_eval_detail_row(detail_id, result, "actual_source", "actual_total", extraction, _money_value(extraction)))
    expected_item_amount_field = source_config.get("expected_item_amount_field")
    if expected_item_amount_field:
        skipped = _skipped_eval_rows(eval_details)
        for extraction in _eval_item_amount_rows(conn, str(result["filename"]), str(expected_item_amount_field), skipped):
            detail_id += 1
            rows.append(_eval_detail_row(detail_id, result, "included_row", "expected_total", extraction, _money_value(extraction)))
    item_amount_field = source_config.get("actual_item_amount_field")
    item_description_terms = source_config.get("actual_item_description_terms", [])
    if item_amount_field:
        for extraction in _eval_item_amount_rows_by_description(
            conn,
            str(result["filename"]),
            str(item_amount_field),
            [str(term) for term in item_description_terms],
        ):
            detail_id += 1
            rows.append(_eval_detail_row(detail_id, result, "actual_source", "actual_total", extraction, _money_value(extraction)))
    amount_field = source_config.get("included_amount_field")
    if amount_field:
        skipped = _skipped_eval_rows(eval_details)
        for extraction in _eval_item_amount_rows(conn, str(result["filename"]), amount_field, skipped):
            detail_id += 1
            rows.append(_eval_detail_row(detail_id, result, "included_row", "actual_total", extraction, _money_value(extraction)))
        for skipped_row in eval_details.get("skipped_summary_or_rollup_rows", []) or []:
            if not isinstance(skipped_row, dict):
                continue
            extraction = _eval_item_row_description(conn, str(result["filename"]), skipped_row)
            detail_id += 1
            rows.append(
                _eval_detail_row(
                    detail_id,
                    result,
                    "excluded_row",
                    "excluded",
                    extraction,
                    _parse_money(skipped_row.get("amount")),
                    reason="rollup row excluded",
                )
            )
    return rows


def _eval_field_rows(conn: sqlite3.Connection, filename: str, field_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT *
            FROM extraction
            WHERE filename = ? AND field_id = ?
            ORDER BY row_index, column_index
            """,
            (filename, field_id),
        ).fetchall()
    )


def _eval_item_amount_rows(
    conn: sqlite3.Connection,
    filename: str,
    amount_field: str,
    skipped_row_indexes: set[int],
) -> list[dict[str, Any]]:
    rows = rows_to_dicts(
        conn.execute(
            """
            SELECT *
            FROM extraction
            WHERE filename = ?
              AND field_id = 'items'
              AND field = ?
              AND COALESCE(field_value, field_unformatted_value, validated_field_value, '') != ''
            ORDER BY row_index, column_index
            """,
            (filename, amount_field),
        ).fetchall()
    )
    return [row for row in rows if row.get("row_index") not in skipped_row_indexes]


def _eval_item_amount_rows_by_description(
    conn: sqlite3.Connection,
    filename: str,
    amount_field: str,
    description_terms: list[str],
) -> list[dict[str, Any]]:
    if not description_terms:
        return []
    where = " OR ".join("LOWER(COALESCE(description.validated_field_value, description.field_value, description.field_unformatted_value, '')) LIKE ?" for _ in description_terms)
    params = [
        filename,
        amount_field,
        *(f"%{term.lower()}%" for term in description_terms),
    ]
    return rows_to_dicts(
        conn.execute(
            f"""
            SELECT amount.*
            FROM extraction amount
            JOIN extraction description
              ON description.filename = amount.filename
             AND description.field_id = amount.field_id
             AND description.row_index = amount.row_index
            WHERE amount.filename = ?
              AND amount.field_id = 'items'
              AND amount.field = ?
              AND LOWER(description.field) IN ('item-description', 'item description')
              AND COALESCE(amount.field_value, amount.field_unformatted_value, amount.validated_field_value, '') != ''
              AND ({where})
            ORDER BY amount.row_index, amount.column_index
            """,
            params,
        ).fetchall()
    )


def _eval_item_row_description(conn: sqlite3.Connection, filename: str, skipped_row: dict[str, Any]) -> dict[str, Any]:
    row_index = skipped_row.get("row_index")
    row = conn.execute(
        """
        SELECT *
        FROM extraction
        WHERE filename = ?
          AND field_id = 'items'
          AND row_index = ?
          AND field IN ('item-description', 'Item Description')
        ORDER BY column_index
        LIMIT 1
        """,
        (filename, row_index),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "filename": filename,
        "field_id": skipped_row.get("field_id", "items"),
        "field": skipped_row.get("amount_field"),
        "field_value": skipped_row.get("description"),
        "field_unformatted_value": skipped_row.get("description"),
        "validated_field_value": None,
        "row_index": row_index,
        "column_index": None,
        "page_range": None,
        "confidence": None,
        "ocr_confidence": None,
    }


def _skipped_eval_rows(eval_details: dict[str, Any]) -> set[int]:
    rows: set[int] = set()
    for row in eval_details.get("skipped_summary_or_rollup_rows", []) or []:
        if isinstance(row, dict) and row.get("row_index") is not None:
            rows.add(int(row["row_index"]))
    return rows


def _eval_detail_row(
    detail_id: int,
    result: dict[str, Any],
    detail_type: str,
    evidence_role: str,
    extraction: dict[str, Any],
    amount: float | None,
    reason: str | None = None,
) -> dict[str, Any]:
    raw_value = _first_present(
        extraction.get("validated_field_value"),
        extraction.get("field_value"),
        extraction.get("field_unformatted_value"),
    )
    source_field_id, source_field = _evidence_field_display(extraction)
    missing = _is_missing_extraction(extraction)
    row_reason = reason or ("missing extraction" if missing and raw_value is None else None)
    metadata = {
        "confidence": extraction.get("confidence"),
        "ocr_confidence": extraction.get("ocr_confidence"),
        "is_missing": missing,
    }
    if source_field_id != extraction.get("field_id"):
        metadata["original_source_field_id"] = extraction.get("field_id")
    if source_field != extraction.get("field"):
        metadata["original_source_field"] = extraction.get("field")
    return {
        "detail_id": detail_id,
        "result_id": result.get("result_id"),
        "run_id": result.get("run_id"),
        "filename": result.get("filename"),
        "rule_name": result.get("rule_name"),
        "detail_type": detail_type,
        "evidence_role": evidence_role,
        "source_field_id": source_field_id,
        "source_field": source_field,
        "row_index": extraction.get("row_index"),
        "column_index": extraction.get("column_index"),
        "raw_value": raw_value,
        "normalized_value": None if amount is None else str(amount),
        "amount": amount,
        "page_number": _page_from_extraction(extraction),
        "bbox": None,
        "reason": row_reason,
        "severity": "info",
        "metadata": metadata,
    }


def _evidence_field_display(extraction: dict[str, Any]) -> tuple[Any, Any]:
    field_id = extraction.get("field_id")
    if isinstance(field_id, str) and field_id in CANONICAL_EVIDENCE_FIELDS:
        return CANONICAL_EVIDENCE_FIELDS[field_id]
    return field_id, extraction.get("field")


def _is_missing_extraction(extraction: dict[str, Any]) -> bool:
    value = extraction.get("is_missing")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _money_value(extraction: dict[str, Any]) -> float | None:
    return _parse_money(
        _first_present(
            extraction.get("validated_field_value"),
            extraction.get("field_value"),
            extraction.get("field_unformatted_value"),
        )
    )


def _parse_money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")") or "-" in text
    cleaned = "".join(char for char in text if char.isdigit() or char == ".")
    if not cleaned:
        return None
    parsed = float(cleaned)
    return -parsed if negative else parsed


def _page_from_extraction(extraction: dict[str, Any]) -> int | None:
    page_range = extraction.get("page_range")
    if not page_range:
        return None
    digits = ""
    for char in str(page_range):
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return None


def logs(level: str | None, limit: int, offset: int) -> dict[str, Any]:
    with connect() as conn:
        where = []
        params: list[Any] = []
        if level:
            where.append("level = ?")
            params.append(level)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        items = rows_to_dicts(
            conn.execute(
                f"SELECT * FROM business_rule_log {where_sql} ORDER BY created_at DESC, log_id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        )
        total = conn.execute(f"SELECT COUNT(*) AS count FROM business_rule_log {where_sql}", params).fetchone()["count"]
        return {"items": items, "total": total, "limit": limit, "offset": offset}


def analytics() -> dict[str, Any]:
    with connect() as conn:
        run_id = latest_run_id(conn)
        if _use_eval_source(conn, run_id):
            return _eval_analytics(conn)
        if run_id is None:
            return _empty_analytics(None)
        summary = _legacy_analytics_summary(conn, run_id)
        rule_pass_rates = rows_to_dicts(conn.execute("SELECT * FROM v_rule_pass_rate ORDER BY rule_name").fetchall())
        failed_documents = _document_rows(conn, run_id, status="failed", sort="failed_rules", limit=20)
        largest = rows_to_dicts(
            conn.execute(
                """
                SELECT filename, rule_name, expected_total, actual_total, difference, absolute_difference, root_cause
                FROM business_rule_result
                WHERE run_id = ? AND rule_passed = 0
                ORDER BY absolute_difference DESC
                LIMIT 20
                """,
                (run_id,),
            ).fetchall()
        )
        warning_frequency = rows_to_dicts(
            conn.execute(
                """
                SELECT event_type, raw_value, COUNT(*) AS count
                FROM business_rule_log
                WHERE run_id = ? AND level = 'warning'
                GROUP BY event_type, raw_value
                ORDER BY count DESC
                """,
                (run_id,),
            ).fetchall()
        )
        no_rule_documents = rows_to_dicts(
            conn.execute(
                """
                SELECT DISTINCT e.filename
                FROM extraction e
                WHERE e.field_id = 'Statement Table > Summary Totals and Balance'
                  AND NOT EXISTS (
                    SELECT 1 FROM business_rule_result r WHERE r.run_id = ? AND r.filename = e.filename
                  )
                ORDER BY e.filename
                """,
                (run_id,),
            ).fetchall()
        )
        confidence = _confidence_metrics(conn)
        root_causes = rows_to_dicts(
            conn.execute(
                """
                SELECT COALESCE(v.root_cause, r.root_cause) AS root_cause, COUNT(*) AS count
                FROM business_rule_result r
                LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
                WHERE r.run_id = ?
                GROUP BY COALESCE(v.root_cause, r.root_cause)
                ORDER BY count DESC
                """,
                (run_id,),
            ).fetchall()
        )
        return {
            "run_id": run_id,
            "summary": summary,
            "rule_pass_rates": rule_pass_rates,
            "failed_documents": failed_documents,
            "largest_differences": largest,
            "warning_frequency": warning_frequency,
            "no_rule_documents": no_rule_documents,
            "confidence": confidence,
            "root_cause_counts": root_causes,
            "diagnosis_counts": [],
            "review_status_counts": _legacy_review_status_counts(conn, run_id),
            "field_confidence": _field_confidence_metrics(conn),
        }


def _empty_analytics(run_id: int | None) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "summary": {
            "total_documents": 0,
            "evaluated_documents": 0,
            "no_rule_documents": 0,
            "total_evaluations": 0,
            "passed_evaluations": 0,
            "failed_evaluations": 0,
            "pass_rate": 0,
            "average_failed_absolute_difference": 0,
        },
        "rule_pass_rates": [],
        "failed_documents": [],
        "largest_differences": [],
        "warning_frequency": [],
        "no_rule_documents": [],
        "confidence": {},
        "root_cause_counts": [],
        "diagnosis_counts": [],
        "review_status_counts": [],
        "field_confidence": [],
    }


def _eval_analytics(conn: sqlite3.Connection) -> dict[str, Any]:
    eval_columns = table_columns(conn, "business_rule_eval")
    failure_expr = "COALESCE(v.root_cause, r.failure_reason, 'unknown')" if "failure_reason" in eval_columns else "COALESCE(v.root_cause, 'unknown')"
    summary = _eval_analytics_summary(conn)
    largest = rows_to_dicts(
        conn.execute(
            f"""
            SELECT
                0 AS result_id,
                NULL AS run_id,
                r.filename,
                r.rule_name,
                r.expected_total,
                r.actual_total,
                COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0) AS difference,
                ABS(COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0)) AS absolute_difference,
                COALESCE(d.tolerance, 0.01) AS tolerance,
                r.rule_passed,
                {failure_expr} AS root_cause,
                CASE WHEN r.rule_passed = 1 THEN 'Rule passed.' ELSE 'Rule failed.' END AS summary,
                d.label,
                d.formula,
                COALESCE(v.status, 'unreviewed') AS review_status,
                v.notes AS review_notes,
                {failure_expr} AS review_root_cause
            FROM business_rule_eval r
            LEFT JOIN rule_definition d ON d.rule_name = r.rule_name
            LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
            WHERE r.rule_passed = 0
            ORDER BY ABS(COALESCE(r.actual_total, 0) - COALESCE(r.expected_total, 0)) DESC, r.filename, r.rule_name
            LIMIT 20
            """
        ).fetchall()
    )
    warning_frequency = rows_to_dicts(
        conn.execute(
            """
            SELECT event_type, raw_value, COUNT(*) AS count
            FROM business_rule_log
            WHERE level = 'warning'
            GROUP BY event_type, raw_value
            ORDER BY count DESC, event_type
            LIMIT 20
            """
        ).fetchall()
    )
    no_rule_documents = rows_to_dicts(
        conn.execute(
            """
            SELECT DISTINCT e.filename
            FROM extraction e
            WHERE NOT EXISTS (
                SELECT 1 FROM business_rule_eval r WHERE r.filename = e.filename
            )
            ORDER BY e.filename
            LIMIT 50
            """
        ).fetchall()
    )
    root_causes = rows_to_dicts(
        conn.execute(
            f"""
            SELECT {failure_expr} AS root_cause, COUNT(*) AS count
            FROM business_rule_eval r
            LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
            WHERE r.rule_passed = 0
            GROUP BY {failure_expr}
            ORDER BY count DESC, root_cause
            LIMIT 20
            """
        ).fetchall()
    )
    return {
        "run_id": None,
        "summary": summary,
        "rule_pass_rates": _eval_rule_pass_rates(conn),
        "failed_documents": _eval_document_rows(conn, status="failed", sort="failed_rules", limit=20),
        "largest_differences": largest,
        "warning_frequency": warning_frequency,
        "no_rule_documents": no_rule_documents,
        "confidence": _confidence_metrics(conn),
        "root_cause_counts": root_causes,
        "diagnosis_counts": _eval_diagnosis_counts(conn),
        "review_status_counts": _eval_review_status_counts(conn),
        "field_confidence": _field_confidence_metrics(conn),
    }


def _eval_analytics_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    total_documents = conn.execute("SELECT COUNT(DISTINCT filename) AS count FROM extraction").fetchone()["count"] or 0
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_evaluations,
            COUNT(DISTINCT filename) AS evaluated_documents,
            SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS passed_evaluations,
            SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS failed_evaluations,
            ROUND(AVG(CASE WHEN rule_passed = 0 THEN ABS(COALESCE(actual_total, 0) - COALESCE(expected_total, 0)) END), 2) AS average_failed_absolute_difference
        FROM business_rule_eval
        """
    ).fetchone()
    total_evaluations = counts["total_evaluations"] or 0
    passed = counts["passed_evaluations"] or 0
    no_rule_documents = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT filename
            FROM extraction e
            GROUP BY filename
            HAVING NOT EXISTS (
                SELECT 1 FROM business_rule_eval r WHERE r.filename = e.filename
            )
        )
        """
    ).fetchone()["count"] or 0
    return {
        "total_documents": total_documents,
        "evaluated_documents": counts["evaluated_documents"] or 0,
        "no_rule_documents": no_rule_documents,
        "total_evaluations": total_evaluations,
        "passed_evaluations": passed,
        "failed_evaluations": counts["failed_evaluations"] or 0,
        "pass_rate": round(passed * 100.0 / total_evaluations, 2) if total_evaluations else 0,
        "average_failed_absolute_difference": counts["average_failed_absolute_difference"] or 0,
    }


def _legacy_analytics_summary(conn: sqlite3.Connection, run_id: int) -> dict[str, Any]:
    total_documents = conn.execute("SELECT COUNT(DISTINCT filename) AS count FROM extraction").fetchone()["count"] or 0
    counts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_evaluations,
            COUNT(DISTINCT filename) AS evaluated_documents,
            SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS passed_evaluations,
            SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS failed_evaluations,
            ROUND(AVG(CASE WHEN rule_passed = 0 THEN absolute_difference END), 2) AS average_failed_absolute_difference
        FROM business_rule_result
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    no_rule_documents = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT filename
            FROM extraction e
            GROUP BY filename
            HAVING NOT EXISTS (
                SELECT 1 FROM business_rule_result r WHERE r.run_id = ? AND r.filename = e.filename
            )
        )
        """,
        (run_id,),
    ).fetchone()["count"] or 0
    total_evaluations = counts["total_evaluations"] or 0
    passed = counts["passed_evaluations"] or 0
    return {
        "total_documents": total_documents,
        "evaluated_documents": counts["evaluated_documents"] or 0,
        "no_rule_documents": no_rule_documents,
        "total_evaluations": total_evaluations,
        "passed_evaluations": passed,
        "failed_evaluations": counts["failed_evaluations"] or 0,
        "pass_rate": round(passed * 100.0 / total_evaluations, 2) if total_evaluations else 0,
        "average_failed_absolute_difference": counts["average_failed_absolute_difference"] or 0,
    }


def _eval_diagnosis_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if "details" not in table_columns(conn, "business_rule_eval"):
        return []
    counts: dict[tuple[str, str, str, str], int] = {}
    rows = conn.execute(
        """
        SELECT details
        FROM business_rule_eval
        WHERE rule_passed = 0 AND details IS NOT NULL AND details != ''
        """
    ).fetchall()
    for row in rows:
        diagnosis = _parse_eval_details(row["details"]).get("diagnosis")
        if not isinstance(diagnosis, dict):
            continue
        key = (
            str(diagnosis.get("reason_code") or "unknown"),
            str(diagnosis.get("title") or diagnosis.get("reason_code") or "Unknown diagnosis"),
            str(diagnosis.get("reason_group") or "unknown"),
            str(diagnosis.get("confidence") or "unknown"),
        )
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "reason_code": reason_code,
            "title": title,
            "reason_group": reason_group,
            "confidence": confidence,
            "count": count,
        }
        for (reason_code, title, reason_group, confidence), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][1]),
        )
    ]


def _eval_review_status_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT review_status AS status, COUNT(*) AS count
            FROM (
                SELECT r.filename, COALESCE(MAX(v.status), 'unreviewed') AS review_status
                FROM business_rule_eval r
                LEFT JOIN business_rule_review v ON v.filename = r.filename
                GROUP BY r.filename
            )
            GROUP BY review_status
            ORDER BY count DESC, review_status
            """
        ).fetchall()
    )


def _legacy_review_status_counts(conn: sqlite3.Connection, run_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT review_status AS status, COUNT(*) AS count
            FROM (
                SELECT r.filename, COALESCE(MAX(v.status), 'unreviewed') AS review_status
                FROM business_rule_result r
                LEFT JOIN business_rule_review v ON v.filename = r.filename
                WHERE r.run_id = ?
                GROUP BY r.filename
            )
            GROUP BY review_status
            ORDER BY count DESC, review_status
            """,
            (run_id,),
        ).fetchall()
    )


def _confidence_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    columns = table_columns(conn, "extraction")
    if "confidence" not in columns and "ocr_confidence" not in columns:
        return {"available": False}
    labels_available = "is_correct" in columns
    confidence_expr = "AVG(confidence)" if "confidence" in columns else "NULL"
    ocr_confidence_expr = "AVG(ocr_confidence)" if "ocr_confidence" in columns else "NULL"
    metrics = conn.execute(
        f"""
        SELECT {confidence_expr} AS avg_confidence, {ocr_confidence_expr} AS avg_ocr_confidence
        FROM extraction
        """
    ).fetchone()
    result = {"available": True, "avg_confidence": metrics["avg_confidence"], "avg_ocr_confidence": metrics["avg_ocr_confidence"]}
    if labels_available:
        accuracy = conn.execute(
            """
            SELECT
                (
                    SELECT ROUND(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
                    FROM extraction
                    WHERE is_correct IS NOT NULL
                ) AS field_accuracy,
                ROUND(AVG(stp) * 100.0, 2) AS stp_rate
            FROM (
                SELECT filename,
                       CASE WHEN SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) = COUNT(*) THEN 1 ELSE 0 END AS stp
                FROM extraction
                WHERE is_correct IS NOT NULL
                GROUP BY filename
            ) labeled_documents
            """
        ).fetchone()
        result["field_accuracy"] = accuracy["field_accuracy"]
        result["stp_rate"] = accuracy["stp_rate"]
    return result


def _field_confidence_metrics(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    columns = table_columns(conn, "extraction")
    if "confidence" not in columns and "ocr_confidence" not in columns:
        return []
    confidence_expr = "AVG(confidence)" if "confidence" in columns else "NULL"
    ocr_confidence_expr = "AVG(ocr_confidence)" if "ocr_confidence" in columns else "NULL"
    missing_expr = "SUM(CASE WHEN is_missing = 1 THEN 1 ELSE 0 END)" if "is_missing" in columns else "0"
    return rows_to_dicts(
        conn.execute(
            f"""
            SELECT
                field_id,
                field,
                COUNT(*) AS extraction_count,
                ROUND({confidence_expr}, 4) AS avg_confidence,
                ROUND({ocr_confidence_expr}, 4) AS avg_ocr_confidence,
                {missing_expr} AS missing_count
            FROM extraction
            GROUP BY field_id, field
            HAVING extraction_count > 0
            ORDER BY
                COALESCE(avg_confidence, avg_ocr_confidence, 1) ASC,
                extraction_count DESC,
                field_id,
                field
            LIMIT 20
            """
        ).fetchall()
    )


def get_review(filename: str, rule_name: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM business_rule_review WHERE filename = ? AND rule_name = ?",
            (filename, rule_name),
        ).fetchone()
        if not row:
            return {"filename": filename, "rule_name": rule_name, "status": "unreviewed", "root_cause": None, "notes": ""}
        return dict(row)


def save_review(filename: str, rule_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = payload.get("status", "unreviewed")
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail={"code": "invalid_review_status", "message": f"Unsupported review status: {status}"})
    root_cause = payload.get("root_cause")
    notes = payload.get("notes", "")
    with connect() as conn:
        run = conn.execute(
            "SELECT run_id FROM business_rule_result WHERE filename = ? AND rule_name = ? ORDER BY run_id DESC LIMIT 1",
            (filename, rule_name),
        ).fetchone()
        run_id = run["run_id"] if run else None
        if not run:
            exists = conn.execute(
                "SELECT 1 FROM business_rule_eval WHERE filename = ? AND rule_name = ? LIMIT 1",
                (filename, rule_name),
            ).fetchone()
        if not run and not exists:
            raise HTTPException(status_code=404, detail={"code": "rule_not_found", "message": "Rule result not found"})
        conn.execute(
            """
            INSERT INTO business_rule_review (filename, rule_name, run_id, status, root_cause, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(filename, rule_name) DO UPDATE SET
                run_id = excluded.run_id,
                status = excluded.status,
                root_cause = excluded.root_cause,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
            """,
            (filename, rule_name, run_id, status, root_cause, notes),
        )
        if status == "added_to_training":
            _upsert_training_exception_queue(conn, filename, rule_name, root_cause, notes, None, False, status)
        conn.commit()
    return get_review(filename, rule_name)


def list_annotations(filename: str, rule_name: str) -> dict[str, Any]:
    with connect() as conn:
        rows = [
            _annotation_row(row)
            for row in rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM business_rule_annotation
                WHERE filename = ? AND rule_name = ?
                ORDER BY updated_at DESC, annotation_id DESC
                """,
                (filename, rule_name),
            ).fetchall()
        )
        ]
    return {"items": rows, "total": len(rows)}


def save_annotation(filename: str, rule_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_annotation_payload(payload)
    with connect() as conn:
        _ensure_rule_exists(conn, filename, rule_name)
        cursor = conn.execute(
            """
            INSERT INTO business_rule_annotation (
                filename, rule_name, detail_id, evidence_role, detail_type, source_field,
                source_field_id, row_index, column_index, corrected_amount, include_in_rule,
                root_cause, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                filename,
                rule_name,
                payload.get("detail_id"),
                payload.get("evidence_role"),
                payload.get("detail_type"),
                payload.get("source_field"),
                payload.get("source_field_id"),
                payload.get("row_index"),
                payload.get("column_index"),
                payload.get("corrected_amount"),
                _bool_to_db(payload.get("include_in_rule")),
                payload.get("root_cause"),
                payload.get("notes", ""),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM business_rule_annotation WHERE annotation_id = ?", (cursor.lastrowid,)).fetchone()
    return _annotation_row(dict(row))


def save_annotations(filename: str, rule_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    annotations = [_normalize_annotation_payload(row) for row in payload.get("annotations", [])]
    with connect() as conn:
        _ensure_rule_exists(conn, filename, rule_name)
        conn.execute("DELETE FROM business_rule_annotation WHERE filename = ? AND rule_name = ?", (filename, rule_name))
        for annotation in annotations:
            conn.execute(
                """
                INSERT INTO business_rule_annotation (
                    filename, rule_name, detail_id, evidence_role, detail_type, source_field,
                    source_field_id, row_index, column_index, corrected_amount, include_in_rule,
                    root_cause, notes, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    filename,
                    rule_name,
                    annotation.get("detail_id"),
                    annotation.get("evidence_role"),
                    annotation.get("detail_type"),
                    annotation.get("source_field"),
                    annotation.get("source_field_id"),
                    annotation.get("row_index"),
                    annotation.get("column_index"),
                    annotation.get("corrected_amount"),
                    _bool_to_db(annotation.get("include_in_rule")),
                    annotation.get("root_cause"),
                    annotation.get("notes", ""),
                ),
            )
        conn.commit()
    saved = list_annotations(filename, rule_name)
    return {**saved, "annotations": saved["items"]}


def recompute_with_annotations(filename: str, rule_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    explanation_payload = explanation(filename, rule_name)
    result = explanation_payload["result"]
    details = explanation_payload["details"]
    annotations = (
        [_normalize_annotation_payload(row) for row in payload.get("annotations", [])]
        if payload and "annotations" in payload
        else list_annotations(filename, rule_name)["items"]
    )
    corrected = _corrected_totals_from_annotations(result, details, annotations)
    return {
        "filename": filename,
        "rule_name": rule_name,
        "original_result": result,
        "corrected_result": corrected,
        "original": result,
        "corrected": corrected,
        "annotations": annotations,
    }


def _normalize_annotation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if "include_in_rule" not in normalized and "include_row" in normalized:
        normalized["include_in_rule"] = normalized.get("include_row")
    return normalized


def _ensure_rule_exists(conn: sqlite3.Connection, filename: str, rule_name: str) -> None:
    if conn.execute(
        "SELECT 1 FROM business_rule_result WHERE filename = ? AND rule_name = ? LIMIT 1",
        (filename, rule_name),
    ).fetchone():
        return
    if conn.execute(
        "SELECT 1 FROM business_rule_eval WHERE filename = ? AND rule_name = ? LIMIT 1",
        (filename, rule_name),
    ).fetchone():
        return
    raise HTTPException(status_code=404, detail={"code": "rule_not_found", "message": "Rule result not found"})


def _annotation_row(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("include_in_rule") is not None:
        row["include_in_rule"] = bool(row["include_in_rule"])
    return row


def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _corrected_totals_from_annotations(
    result: dict[str, Any],
    details: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    detail_annotations: dict[int, dict[str, Any]] = {
        int(annotation["detail_id"]): annotation
        for annotation in annotations
        if annotation.get("detail_id") is not None
    }
    expected_total = float(result.get("expected_total") or 0)
    actual_total = float(result.get("actual_total") or 0)
    expected_parts: list[float] = []
    actual_parts: list[float] = []
    has_expected_annotation = False
    has_actual_annotation = False

    for detail in details:
        detail_type = detail.get("detail_type")
        if detail_type == "computed_value":
            continue
        annotation = detail_annotations.get(int(detail["detail_id"])) if detail.get("detail_id") is not None else _matching_annotation(detail, annotations)
        include = annotation.get("include_in_rule") if annotation else None
        if include is False:
            continue
        amount = annotation.get("corrected_amount") if annotation and annotation.get("corrected_amount") is not None else detail.get("amount")
        if amount is None:
            continue
        evidence_role = (annotation.get("evidence_role") if annotation else detail.get("evidence_role")) or detail.get("evidence_role")
        if evidence_role == "expected_total" or detail_type == "expected_source":
            expected_parts.append(float(amount))
            has_expected_annotation = has_expected_annotation or annotation is not None
        elif evidence_role == "actual_total" or detail_type in {"included_row", "actual_source"}:
            actual_parts.append(float(amount))
            has_actual_annotation = has_actual_annotation or annotation is not None

    if has_expected_annotation and expected_parts:
        expected_total = sum(expected_parts)
    if has_actual_annotation and actual_parts:
        actual_total = sum(actual_parts)

    difference = actual_total - expected_total
    absolute_difference = abs(difference)
    tolerance = float(result.get("tolerance") or 0.01)
    return {
        "expected_total": expected_total,
        "actual_total": actual_total,
        "difference": difference,
        "absolute_difference": absolute_difference,
        "tolerance": tolerance,
        "rule_passed": absolute_difference <= tolerance,
    }


def _matching_annotation(detail: dict[str, Any], annotations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for annotation in annotations:
        if annotation.get("detail_id") is not None:
            continue
        if annotation.get("source_field_id") != detail.get("source_field_id"):
            continue
        if annotation.get("source_field") != detail.get("source_field"):
            continue
        if annotation.get("row_index") != detail.get("row_index"):
            continue
        if annotation.get("column_index") != detail.get("column_index"):
            continue
        return annotation
    return None


def list_training_exceptions() -> dict[str, Any]:
    with connect() as conn:
        rows = [
            _training_exception_row(row)
            for row in rows_to_dicts(
            conn.execute(
                """
                SELECT *
                FROM training_exception_queue
                ORDER BY updated_at DESC, queue_id DESC
                """
            ).fetchall()
        )
        ]
    return {"items": rows, "total": len(rows)}


def remove_training_exception(filename: str, rule_name: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        if rule_name:
            cursor = conn.execute(
                "DELETE FROM training_exception_queue WHERE filename = ? AND rule_name = ?",
                (filename, rule_name),
            )
        else:
            cursor = conn.execute("DELETE FROM training_exception_queue WHERE filename = ?", (filename,))
        conn.commit()
    return {"filename": filename, "rule_name": rule_name, "removed": cursor.rowcount}


def export_training_exceptions() -> dict[str, Any]:
    settings = get_settings()
    root = settings.document_root.resolve()
    exceptions_dir = (root / "exceptions").resolve()
    _ensure_under_document_root(root, exceptions_dir)
    exceptions_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        rows = rows_to_dicts(conn.execute("SELECT * FROM training_exception_queue ORDER BY filename, rule_name").fetchall())
        manifest: list[dict[str, Any]] = []
        for row in rows:
            copied = _copy_exception_file(root, str(row["filename"]))
            conn.execute(
                """
                UPDATE training_exception_queue
                SET copied_path = ?, already_present = ?, updated_at = CURRENT_TIMESTAMP
                WHERE queue_id = ?
                """,
                (copied["exception_path"], 1 if copied["already_exists"] else 0, row["queue_id"]),
            )
            manifest.append(
                {
                    "filename": row["filename"],
                    "rule": row["rule_name"],
                    "root_cause": row.get("root_cause") or "",
                    "notes": row.get("notes") or "",
                    "expected_total": row.get("expected_total"),
                    "actual_total": row.get("actual_total"),
                    "reviewer_status": row.get("reviewer_status") or "",
                    "copied_path": copied["exception_path"],
                    "already_present": copied["already_exists"],
                }
            )
        manifest_path = exceptions_dir / "training_exceptions_manifest.csv"
        with manifest_path.open("w", newline="") as csv_file:
            fieldnames = ["filename", "rule", "root_cause", "notes", "expected_total", "actual_total", "reviewer_status", "copied_path", "already_present"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest)
        conn.commit()
    return {
        "total": len(manifest),
        "exported_count": len(manifest),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "items": [_training_exception_row(row) for row in rows],
    }


def _training_exception_row(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    next_row["source_path"] = next_row.get("source_path") or ""
    next_row["exception_path"] = next_row.get("copied_path") or ""
    next_row["already_exists"] = bool(next_row.get("already_present"))
    next_row["review_status"] = next_row.get("reviewer_status")
    return next_row


def _upsert_training_exception_queue(
    conn: sqlite3.Connection,
    filename: str,
    rule_name: str,
    root_cause: str | None,
    notes: str,
    copied_path: str | None,
    already_present: bool | None,
    reviewer_status: str | None = None,
    expected_total: float | None = None,
    actual_total: float | None = None,
) -> None:
    metadata = _rule_totals(conn, filename, rule_name)
    conn.execute(
        """
        INSERT INTO training_exception_queue (
            filename, rule_name, root_cause, notes, expected_total, actual_total,
            reviewer_status, copied_path, already_present, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(filename, rule_name) DO UPDATE SET
            root_cause = COALESCE(excluded.root_cause, training_exception_queue.root_cause),
            notes = excluded.notes,
            expected_total = COALESCE(excluded.expected_total, training_exception_queue.expected_total),
            actual_total = COALESCE(excluded.actual_total, training_exception_queue.actual_total),
            reviewer_status = excluded.reviewer_status,
            copied_path = COALESCE(excluded.copied_path, training_exception_queue.copied_path),
            already_present = excluded.already_present,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            filename,
            rule_name,
            root_cause if root_cause is not None else metadata.get("root_cause"),
            notes,
            expected_total if expected_total is not None else metadata.get("expected_total"),
            actual_total if actual_total is not None else metadata.get("actual_total"),
            reviewer_status or "added_to_training",
            copied_path,
            1 if already_present else 0,
        ),
    )


def _rule_totals(conn: sqlite3.Connection, filename: str, rule_name: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT expected_total, actual_total, root_cause
        FROM business_rule_result
        WHERE filename = ? AND rule_name = ?
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (filename, rule_name),
    ).fetchone()
    if row:
        return dict(row)
    eval_columns = table_columns(conn, "business_rule_eval")
    failure_expr = "failure_reason" if "failure_reason" in eval_columns else "NULL"
    row = conn.execute(
        f"""
        SELECT expected_total, actual_total, {failure_expr} AS root_cause
        FROM business_rule_eval
        WHERE filename = ? AND rule_name = ?
        LIMIT 1
        """,
        (filename, rule_name),
    ).fetchone()
    return dict(row) if row else {}


def _first_failed_rule_for_document(conn: sqlite3.Connection, filename: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT rule_name, expected_total, actual_total, root_cause
        FROM business_rule_result
        WHERE filename = ? AND rule_passed = 0
        ORDER BY absolute_difference DESC, rule_name
        LIMIT 1
        """,
        (filename,),
    ).fetchone()
    if row:
        return dict(row)
    eval_columns = table_columns(conn, "business_rule_eval")
    failure_expr = "failure_reason" if "failure_reason" in eval_columns else "NULL"
    row = conn.execute(
        f"""
        SELECT rule_name, expected_total, actual_total, {failure_expr} AS root_cause
        FROM business_rule_eval
        WHERE filename = ? AND rule_passed = 0
        ORDER BY ABS(COALESCE(actual_total, 0) - COALESCE(expected_total, 0)) DESC, rule_name
        LIMIT 1
        """,
        (filename,),
    ).fetchone()
    return dict(row) if row else None


def failed_rules_csv() -> str:
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT r.filename, r.rule_name, r.expected_total, r.actual_total, r.difference,
                       COALESCE(v.root_cause, r.root_cause) AS root_cause,
                       COUNT(l.log_id) AS warning_count,
                       COALESCE(v.status, 'unreviewed') AS review_status
                FROM business_rule_result r
                LEFT JOIN business_rule_review v ON v.filename = r.filename AND v.rule_name = r.rule_name
                LEFT JOIN business_rule_log l ON l.run_id = r.run_id AND l.filename = r.filename AND l.level = 'warning'
                WHERE r.rule_passed = 0
                GROUP BY r.result_id
                ORDER BY r.absolute_difference DESC
                """
            ).fetchall()
        )
    output = StringIO()
    fieldnames = ["filename", "rule_name", "expected_total", "actual_total", "difference", "root_cause", "warning_count", "review_status"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
