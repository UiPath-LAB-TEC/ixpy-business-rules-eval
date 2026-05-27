CREATE TABLE IF NOT EXISTS business_rule_eval (
    filename TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    expected_total REAL,
    actual_total REAL,
    rule_passed BOOLEAN NOT NULL,
    PRIMARY KEY (filename, rule_name)
);

CREATE TABLE IF NOT EXISTS rule_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluator_name TEXT NOT NULL,
    db_path TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    document_count INTEGER NOT NULL DEFAULT 0,
    result_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS document_registry (
    filename TEXT PRIMARY KEY,
    document_type_id TEXT,
    document_path TEXT,
    page_count INTEGER,
    has_coordinates BOOLEAN NOT NULL DEFAULT 0,
    latest_run_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (latest_run_id) REFERENCES rule_run(run_id)
);

CREATE TABLE IF NOT EXISTS rule_definition (
    rule_name TEXT PRIMARY KEY,
    document_family TEXT NOT NULL,
    label TEXT NOT NULL,
    formula TEXT NOT NULL,
    tolerance REAL NOT NULL DEFAULT 0.01,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS business_rule_result (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    expected_total REAL,
    actual_total REAL,
    difference REAL,
    absolute_difference REAL,
    tolerance REAL NOT NULL DEFAULT 0.01,
    rule_passed BOOLEAN NOT NULL,
    root_cause TEXT NOT NULL DEFAULT 'unknown',
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES rule_run(run_id),
    FOREIGN KEY (rule_name) REFERENCES rule_definition(rule_name),
    UNIQUE (run_id, filename, rule_name)
);

CREATE TABLE IF NOT EXISTS business_rule_eval_detail (
    detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER,
    run_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    rule_name TEXT,
    detail_type TEXT NOT NULL,
    evidence_role TEXT,
    source_field_id TEXT,
    source_field TEXT,
    row_index INTEGER,
    column_index INTEGER,
    raw_value TEXT,
    normalized_value TEXT,
    amount REAL,
    page_number INTEGER,
    bbox_json TEXT,
    reason TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (result_id) REFERENCES business_rule_result(result_id),
    FOREIGN KEY (run_id) REFERENCES rule_run(run_id)
);

CREATE TABLE IF NOT EXISTS business_rule_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    filename TEXT,
    level TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    context_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES rule_run(run_id)
);

CREATE TABLE IF NOT EXISTS business_rule_review (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    run_id INTEGER,
    status TEXT NOT NULL DEFAULT 'unreviewed',
    root_cause TEXT,
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (filename, rule_name),
    FOREIGN KEY (run_id) REFERENCES rule_run(run_id)
);

CREATE TABLE IF NOT EXISTS business_rule_annotation (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    detail_id INTEGER,
    evidence_role TEXT,
    detail_type TEXT,
    source_field TEXT,
    source_field_id TEXT,
    row_index INTEGER,
    column_index INTEGER,
    corrected_amount REAL,
    include_in_rule BOOLEAN,
    root_cause TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_exception_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    root_cause TEXT,
    notes TEXT NOT NULL DEFAULT '',
    expected_total REAL,
    actual_total REAL,
    reviewer_status TEXT NOT NULL DEFAULT 'added_to_training',
    copied_path TEXT,
    already_present BOOLEAN NOT NULL DEFAULT 0,
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (filename, rule_name)
);

CREATE INDEX IF NOT EXISTS idx_rule_run_status ON rule_run(status, started_at);
CREATE INDEX IF NOT EXISTS idx_result_filename ON business_rule_result(filename, run_id);
CREATE INDEX IF NOT EXISTS idx_result_rule ON business_rule_result(rule_name, rule_passed);
CREATE INDEX IF NOT EXISTS idx_result_diff ON business_rule_result(absolute_difference DESC);
CREATE INDEX IF NOT EXISTS idx_detail_filename_rule ON business_rule_eval_detail(filename, rule_name, detail_type);
CREATE INDEX IF NOT EXISTS idx_log_filename ON business_rule_log(filename, event_type, level);
CREATE INDEX IF NOT EXISTS idx_review_filename ON business_rule_review(filename, rule_name);
CREATE INDEX IF NOT EXISTS idx_annotation_filename_rule ON business_rule_annotation(filename, rule_name);
CREATE INDEX IF NOT EXISTS idx_training_exception_filename_rule ON training_exception_queue(filename, rule_name);
