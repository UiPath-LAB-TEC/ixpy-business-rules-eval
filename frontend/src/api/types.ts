export type Dashboard = {
  run_id: number | null;
  total_documents: number;
  evaluated_documents: number;
  no_rule_documents: number;
  total_evaluations: number;
  passed_evaluations: number;
  failed_evaluations: number;
  pass_rate: number;
  warning_count: number;
  average_failed_absolute_difference: number;
  unreviewed_failed_documents?: number;
  reviewed_documents?: number;
  added_to_training_documents?: number;
  ignored_documents?: number;
  top_recurring_root_causes?: Array<{ root_cause: string; count: number }>;
  worst_rules: RulePassRate[];
  recent_documents: DocumentSummary[];
};

export type DocumentSummary = {
  filename: string;
  document_type_id: string | null;
  rules_evaluated: number;
  rules_passed: number;
  rules_failed: number;
  pass_rate: number;
  largest_absolute_difference: number | null;
  warning_count: number;
  avg_confidence: number | null;
  avg_ocr_confidence: number | null;
  review_status: string;
  root_cause: string | null;
};

export type RuleResult = {
  result_id: number;
  run_id: number;
  filename: string;
  rule_name: string;
  expected_total: number | null;
  actual_total: number | null;
  difference: number | null;
  absolute_difference: number | null;
  tolerance: number;
  rule_passed: number | boolean;
  root_cause: string;
  summary: string | null;
  label?: string;
  formula?: string;
  review_status?: string;
  review_notes?: string | null;
  review_root_cause?: string | null;
};

export type DocumentDetail = {
  document: {
    filename: string;
    document_type_id: string | null;
    document_path: string | null;
    page_count: number | null;
    has_coordinates: number | boolean;
    latest_run_id: number | null;
  };
  rules: RuleResult[];
};

export type TrainingExceptionResult = {
  filename: string;
  source_path: string;
  exception_path: string;
  already_exists: boolean;
  rule_name?: string | null;
  root_cause?: string | null;
  notes?: string | null;
  review_status?: string | null;
  expected_total?: number | null;
  actual_total?: number | null;
};

export type ArchiveDocumentResult = {
  filename: string;
  rule_name: string | null;
  source_path: string;
  archive_path: string;
};

export type TrainingExceptionQueueItem = TrainingExceptionResult;

export type TrainingExceptionExport = {
  manifest_path?: string;
  exported_count?: number;
  items?: TrainingExceptionQueueItem[];
};

export type EvidenceDetail = {
  detail_id: number;
  filename: string;
  rule_name: string | null;
  detail_type: string;
  evidence_role: string | null;
  source_field_id: string | null;
  source_field: string | null;
  row_index: number | null;
  column_index: number | null;
  raw_value: string | null;
  normalized_value: string | null;
  amount: number | null;
  page_number: number | null;
  bbox: { x: number; y: number; width: number; height: number } | null;
  reason: string | null;
  severity: string;
  metadata?: {
    confidence?: number | null;
    ocr_confidence?: number | null;
    is_missing?: boolean | null;
    original_source_field_id?: string | null;
    original_source_field?: string | null;
  } | null;
};

export type Explanation = {
  result: RuleResult;
  details: EvidenceDetail[];
  logs: LogEntry[];
  diagnosis?: RuleDiagnosis | null;
  diagnosis_evidence?: RuleDiagnosisEvidence | null;
  suggested_root_causes?: string[];
};

export type RuleDiagnosis = {
  title?: string | null;
  message?: string | null;
  confidence?: string | null;
  reason_code?: string | null;
  reason_group?: string | null;
  recommended_action?: string | null;
};

export type RuleDiagnosisEvidence = Record<string, unknown>;

export type EvidenceAnnotation = {
  detail_id: number;
  corrected_amount: number | null;
  include_row: boolean;
  root_cause?: string | null;
  notes: string;
};

export type RecomputeResult = {
  original: {
    expected_total: number | null;
    actual_total: number | null;
    difference: number | null;
    rule_passed: boolean | number;
  };
  corrected: {
    expected_total: number | null;
    actual_total: number | null;
    difference: number | null;
    rule_passed: boolean | number;
  };
};

export type LogEntry = {
  log_id: number;
  run_id: number | null;
  filename: string | null;
  level: string;
  event_type: string;
  message: string;
  raw_value: string | null;
  normalized_value: string | null;
  created_at: string;
};

export type RulePassRate = {
  rule_name: string;
  total_evaluated: number;
  total_passed: number;
  total_failed: number;
  pass_rate_percentage: number;
  avg_absolute_difference: number | null;
};

export type Analytics = {
  run_id: number | null;
  summary?: {
    total_documents: number;
    evaluated_documents: number;
    no_rule_documents: number;
    total_evaluations: number;
    passed_evaluations: number;
    failed_evaluations: number;
    pass_rate: number;
    average_failed_absolute_difference: number;
  };
  rule_pass_rates: RulePassRate[];
  failed_documents: DocumentSummary[];
  largest_differences: RuleResult[];
  warning_frequency: Array<{ event_type: string; raw_value: string | null; count: number }>;
  no_rule_documents: Array<{ filename: string }>;
  confidence: Record<string, unknown>;
  root_cause_counts: Array<{ root_cause: string; count: number }>;
  diagnosis_counts?: Array<{ reason_code: string; title: string; reason_group: string; confidence: string; count: number }>;
  review_status_counts?: Array<{ status: string; count: number }>;
  field_confidence?: Array<{
    field_id: string | null;
    field: string | null;
    extraction_count: number;
    avg_confidence: number | null;
    avg_ocr_confidence: number | null;
    missing_count: number;
  }>;
};

export type Run = {
  run_id: number;
  evaluator_name: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  document_count: number;
  result_count: number;
  warning_count: number;
  error_message: string | null;
};

export type ReviewPayload = {
  status: string;
  root_cause: string | null;
  notes: string;
};
