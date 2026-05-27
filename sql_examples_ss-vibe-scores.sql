-- Compatibility copy of the settlement statement scorecard query.
SELECT
    COUNT(*) AS total_rule_evaluations,
    COUNT(DISTINCT filename) AS evaluated_documents,
    SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS total_passed,
    SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS total_failed,
    ROUND(SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate_percentage
FROM business_rule_eval;

