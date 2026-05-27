CREATE VIEW IF NOT EXISTS v_latest_run AS
SELECT run_id
FROM rule_run
WHERE status = 'completed'
ORDER BY completed_at DESC, run_id DESC
LIMIT 1;

CREATE VIEW IF NOT EXISTS v_document_rule_summary AS
SELECT
    r.filename,
    COUNT(*) AS rules_evaluated,
    SUM(CASE WHEN r.rule_passed = 1 THEN 1 ELSE 0 END) AS rules_passed,
    SUM(CASE WHEN r.rule_passed = 0 THEN 1 ELSE 0 END) AS rules_failed,
    MAX(r.absolute_difference) AS largest_absolute_difference,
    AVG(e.confidence) AS avg_confidence,
    AVG(e.ocr_confidence) AS avg_ocr_confidence
FROM business_rule_result r
LEFT JOIN extraction e ON e.filename = r.filename
WHERE r.run_id = (SELECT run_id FROM v_latest_run)
GROUP BY r.filename;

CREATE VIEW IF NOT EXISTS v_rule_pass_rate AS
SELECT
    rule_name,
    COUNT(*) AS total_evaluated,
    SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) AS total_passed,
    SUM(CASE WHEN rule_passed = 0 THEN 1 ELSE 0 END) AS total_failed,
    ROUND(SUM(CASE WHEN rule_passed = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate_percentage,
    ROUND(AVG(absolute_difference), 2) AS avg_absolute_difference
FROM business_rule_result
WHERE run_id = (SELECT run_id FROM v_latest_run)
GROUP BY rule_name;

