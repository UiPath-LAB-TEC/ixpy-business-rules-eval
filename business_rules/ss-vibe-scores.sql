-- Settlement Statement business rule scorecard
-- Run with:
-- sqlite3 -header -column cache/uwm_ss_gemini_caller.db < business_rules/ss-vibe-scores.sql

-- Overall score
SELECT
    COUNT(*) AS total_rule_evaluations,
    COUNT(DISTINCT filename) AS evaluated_documents,
    SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS total_passed,
    SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS total_failed,
    ROUND(
        SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) AS pass_rate_percentage
FROM business_rule_eval;

-- Score by rule
SELECT
    rule_name,
    COUNT(*) AS total_evaluated,
    COUNT(DISTINCT filename) AS unique_documents,
    SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS total_passed,
    SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS total_failed,
    ROUND(
        SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) AS pass_rate_percentage,
    ROUND(AVG(ABS(expected_total - actual_total)), 2) AS avg_absolute_difference
FROM business_rule_eval
GROUP BY rule_name
ORDER BY
    CASE rule_name
        WHEN 'debit_amounts_equal_subtotal_debits' THEN 1
        WHEN 'credit_amounts_equal_subtotal_credits' THEN 2
        WHEN 'total_credits_equal_subtotal_credits_plus_due_from_buyer' THEN 3
        WHEN 'total_debits_balance_total_credits' THEN 4
        ELSE 99
    END,
    rule_name;

-- Score by document
SELECT
    filename,
    COUNT(*) AS rules_evaluated,
    SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS rules_passed,
    SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS rules_failed,
    ROUND(
        SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) AS document_pass_rate_percentage,
    CASE
        WHEN SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) = 0 THEN 1
        ELSE 0
    END AS all_rules_passed
FROM business_rule_eval
GROUP BY filename
ORDER BY rules_failed DESC, document_pass_rate_percentage ASC, filename;

-- Failed rule details
SELECT
    filename,
    rule_name,
    expected_total,
    actual_total,
    ROUND(actual_total - expected_total, 2) AS difference,
    ROUND(ABS(actual_total - expected_total), 2) AS absolute_difference
FROM business_rule_eval
WHERE rule_passed = 0
ORDER BY absolute_difference DESC, filename, rule_name;

-- Documents with one or more failed business rules
SELECT
    filename,
    COUNT(*) AS failed_rules
FROM business_rule_eval
WHERE rule_passed = 0
GROUP BY filename
ORDER BY failed_rules DESC, filename;

-- Documents with all evaluated business rules passing
SELECT
    filename
FROM business_rule_eval
GROUP BY filename
HAVING SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) = 0
ORDER BY filename;

-- Extraction documents that had a Summary Totals and Balance group but no rule output
SELECT
    e.filename
FROM extraction e
WHERE e.field_id = 'Statement Table > Summary Totals and Balance'
GROUP BY e.filename
HAVING NOT EXISTS (
    SELECT 1
    FROM business_rule_eval bre
    WHERE bre.filename = e.filename
)
ORDER BY e.filename;
