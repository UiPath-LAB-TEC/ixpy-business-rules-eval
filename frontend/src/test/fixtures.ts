import type { Analytics, Dashboard, DocumentDetail, Explanation, LogEntry, Run } from '../api/types';

export const dashboard: Dashboard = {
  run_id: 1,
  total_documents: 4,
  evaluated_documents: 3,
  no_rule_documents: 1,
  total_evaluations: 10,
  passed_evaluations: 5,
  failed_evaluations: 5,
  pass_rate: 50,
  warning_count: 2,
  average_failed_absolute_difference: 22.5,
  unreviewed_failed_documents: 2,
  reviewed_documents: 1,
  added_to_training_documents: 1,
  ignored_documents: 0,
  top_recurring_root_causes: [{ root_cause: 'missing due-from-borrower fields', count: 3 }, { root_cause: 'extraction mismatch', count: 2 }],
  worst_rules: [{ rule_name: 'credit_amounts_equal_subtotal_credits', total_evaluated: 3, total_passed: 1, total_failed: 2, pass_rate_percentage: 33.33, avg_absolute_difference: 25 }],
  recent_documents: [
    {
      filename: 'fail_balancing.pdf',
      document_type_id: 'settlement_statement',
      rules_evaluated: 4,
      rules_passed: 2,
      rules_failed: 2,
      pass_rate: 50,
      largest_absolute_difference: 40,
      warning_count: 0,
      avg_confidence: 0.9,
      avg_ocr_confidence: 0.91,
      review_status: 'unreviewed',
      root_cause: 'extraction mismatch',
    },
    {
      filename: 'next_document.pdf',
      document_type_id: 'settlement_statement',
      rules_evaluated: 4,
      rules_passed: 1,
      rules_failed: 3,
      pass_rate: 25,
      largest_absolute_difference: 55,
      warning_count: 1,
      avg_confidence: 0.86,
      avg_ocr_confidence: 0.88,
      review_status: 'unreviewed',
      root_cause: 'extraction mismatch',
    },
  ],
};

export const documentDetail: DocumentDetail = {
  document: {
    filename: 'fail_balancing.pdf',
    document_type_id: 'settlement_statement',
    document_path: 'tests/fixtures/docs/fail_balancing.pdf',
    page_count: 1,
    has_coordinates: 1,
    latest_run_id: 1,
  },
  rules: [
    {
      result_id: 1,
      run_id: 1,
      filename: 'fail_balancing.pdf',
      rule_name: 'credit_amounts_equal_subtotal_credits',
      expected_total: 250,
      actual_total: 275,
      difference: 25,
      absolute_difference: 25,
      tolerance: 0.01,
      rule_passed: 0,
      root_cause: 'extraction mismatch',
      summary: 'failed',
      review_status: 'unreviewed',
    },
    {
      result_id: 2,
      run_id: 1,
      filename: 'fail_balancing.pdf',
      rule_name: 'total_credits_equal_subtotal_credits_plus_due_from_borrower',
      expected_total: 300,
      actual_total: 300,
      difference: 0,
      absolute_difference: 0,
      tolerance: 0.01,
      rule_passed: 1,
      root_cause: 'unknown',
      summary: 'passed',
      review_status: 'unreviewed',
    },
    {
      result_id: 3,
      run_id: 1,
      filename: 'fail_balancing.pdf',
      rule_name: 'total_debits_equal_subtotal_debits_plus_due_to_borrower',
      expected_total: 325,
      actual_total: 325,
      difference: 0,
      absolute_difference: 0,
      tolerance: 0.01,
      rule_passed: 1,
      root_cause: 'unknown',
      summary: 'passed',
      review_status: 'unreviewed',
    },
  ],
};

export const explanation: Explanation = {
  result: {
    ...documentDetail.rules[0],
    label: 'Credit line items equal subtotal credits',
    formula: 'sum(included credit line items) = subtotal credits',
    review_root_cause: 'extraction mismatch',
    review_notes: '',
  },
  diagnosis: {
    title: 'Amount appears to be assigned to the wrong column',
    message: 'The mismatch is consistent with a line item amount being extracted under credits instead of debits.',
    confidence: 'high',
    reason_code: 'amount_extracted_in_wrong_column',
    reason_group: 'line_item_column_assignment',
    recommended_action: 'Verify the highlighted row amount and confirm whether it belongs in the debit or credit column.',
  },
  diagnosis_evidence: {
    formula: 'sum(credit line items) == subtotal credits',
    expected_total: '250.00',
    actual_total: '275.00',
    difference: '25.00',
    absolute_difference: '25.00',
    matched_rows: [
      {
        field_id: 'items',
        row_index: 15,
        description: 'Aggregate Adjustment',
        amount_field: 'Credit Amount',
        amount: '-452.48',
        why_relevant: 'twice the aggregate adjustment is approximately the gap',
      },
    ],
  },
  details: [
    { detail_id: 10, filename: 'fail_balancing.pdf', rule_name: 'credit_amounts_equal_subtotal_credits', detail_type: 'computed_value', evidence_role: 'expected_total', source_field_id: null, source_field: null, row_index: null, column_index: null, raw_value: null, normalized_value: '250', amount: 250, page_number: null, bbox: null, reason: null, severity: 'info' },
    { detail_id: 12, filename: 'fail_balancing.pdf', rule_name: 'credit_amounts_equal_subtotal_credits', detail_type: 'expected_source', evidence_role: 'expected_total', source_field_id: 'Statement Table > Summary Totals and Balance', source_field: 'Subtotal Credits Amount', row_index: 0, column_index: 1, raw_value: '250.00', normalized_value: '250.00', amount: 250, page_number: 1, bbox: null, reason: null, severity: 'info', metadata: { confidence: 0.93, ocr_confidence: 0.94 } },
    { detail_id: 11, filename: 'fail_balancing.pdf', rule_name: 'credit_amounts_equal_subtotal_credits', detail_type: 'included_row', evidence_role: 'actual_total', source_field_id: 'items', source_field: 'credit-amount', row_index: 2, column_index: 1, raw_value: '150.00', normalized_value: '150.00', amount: 150, page_number: 1, bbox: { x: 0.2, y: 0.3, width: 0.14, height: 0.04 }, reason: null, severity: 'info', metadata: { confidence: 0.83, ocr_confidence: 0.85 } },
    { detail_id: 13, filename: 'fail_balancing.pdf', rule_name: 'credit_amounts_equal_subtotal_credits', detail_type: 'excluded_row', evidence_role: 'excluded', source_field_id: 'Statement Table > Credits', source_field: 'Credit Amount', row_index: 3, column_index: 1, raw_value: '250.00', normalized_value: null, amount: null, page_number: 1, bbox: null, reason: 'rollup row excluded', severity: 'info', metadata: { confidence: 0.88, ocr_confidence: 0.89 } },
  ],
  logs: [],
};

export const totalCreditsExplanation: Explanation = {
  result: {
    ...documentDetail.rules[1],
    label: 'Total credits equal subtotal credits plus due from borrower',
    formula: 'total credits = subtotal credits + due from borrower',
    review_root_cause: 'unknown',
    review_notes: '',
  },
  details: [
    { detail_id: 20, filename: 'fail_balancing.pdf', rule_name: 'total_credits_equal_subtotal_credits_plus_due_from_borrower', detail_type: 'computed_value', evidence_role: 'actual_total', source_field_id: null, source_field: null, row_index: null, column_index: null, raw_value: null, normalized_value: '300', amount: 300, page_number: null, bbox: null, reason: null, severity: 'info' },
    { detail_id: 21, filename: 'fail_balancing.pdf', rule_name: 'total_credits_equal_subtotal_credits_plus_due_from_borrower', detail_type: 'expected_source', evidence_role: 'expected_total', source_field_id: 'total-credits-amount', source_field: 'Total Credits Amount', row_index: -1, column_index: -1, raw_value: '300.00', normalized_value: '300.00', amount: 300, page_number: 1, bbox: null, reason: null, severity: 'info' },
    { detail_id: 22, filename: 'fail_balancing.pdf', rule_name: 'total_credits_equal_subtotal_credits_plus_due_from_borrower', detail_type: 'actual_source', evidence_role: 'actual_total', source_field_id: 'subtotal-credits-amount', source_field: 'Subtotal Credits Amount', row_index: -1, column_index: -1, raw_value: '250.00', normalized_value: '250.00', amount: 250, page_number: 1, bbox: null, reason: null, severity: 'info' },
    { detail_id: 23, filename: 'fail_balancing.pdf', rule_name: 'total_credits_equal_subtotal_credits_plus_due_from_borrower', detail_type: 'actual_source', evidence_role: 'actual_total', source_field_id: 'due-from-borrower', source_field: 'Due From Borrower', row_index: -1, column_index: -1, raw_value: '50.00', normalized_value: '50.00', amount: 50, page_number: 1, bbox: null, reason: null, severity: 'info' },
  ],
  logs: [],
};

export const totalDebitsExplanation: Explanation = {
  result: {
    ...documentDetail.rules[2],
    label: 'Total debits equal subtotal debits plus due to borrower',
    formula: 'total debits = subtotal debits + due to borrower',
    review_root_cause: 'unknown',
    review_notes: '',
  },
  details: [
    { detail_id: 30, filename: 'fail_balancing.pdf', rule_name: 'total_debits_equal_subtotal_debits_plus_due_to_borrower', detail_type: 'computed_value', evidence_role: 'actual_total', source_field_id: null, source_field: null, row_index: null, column_index: null, raw_value: null, normalized_value: '325', amount: 325, page_number: null, bbox: null, reason: null, severity: 'info' },
    { detail_id: 31, filename: 'fail_balancing.pdf', rule_name: 'total_debits_equal_subtotal_debits_plus_due_to_borrower', detail_type: 'expected_source', evidence_role: 'expected_total', source_field_id: 'total-debits-amount', source_field: 'Total Debits Amount', row_index: -1, column_index: -1, raw_value: '325.00', normalized_value: '325.00', amount: 325, page_number: 1, bbox: null, reason: null, severity: 'info' },
    { detail_id: 32, filename: 'fail_balancing.pdf', rule_name: 'total_debits_equal_subtotal_debits_plus_due_to_borrower', detail_type: 'actual_source', evidence_role: 'actual_total', source_field_id: 'subtotal-debits-amount', source_field: 'Subtotal Debits Amount', row_index: -1, column_index: -1, raw_value: '300.00', normalized_value: '300.00', amount: 300, page_number: 1, bbox: null, reason: null, severity: 'info' },
    { detail_id: 33, filename: 'fail_balancing.pdf', rule_name: 'total_debits_equal_subtotal_debits_plus_due_to_borrower', detail_type: 'actual_source', evidence_role: 'actual_total', source_field_id: 'due-to-borrower', source_field: 'Due To Borrower', row_index: -1, column_index: -1, raw_value: '25.00', normalized_value: '25.00', amount: 25, page_number: 1, bbox: null, reason: null, severity: 'info' },
  ],
  logs: [],
};

export const analytics: Analytics = {
  run_id: 1,
  summary: {
    total_documents: 4,
    evaluated_documents: 3,
    no_rule_documents: 1,
    total_evaluations: 10,
    passed_evaluations: 5,
    failed_evaluations: 5,
    pass_rate: 50,
    average_failed_absolute_difference: 22.5,
  },
  rule_pass_rates: dashboard.worst_rules,
  failed_documents: dashboard.recent_documents,
  largest_differences: documentDetail.rules,
  warning_frequency: [{ event_type: 'numeric_parse_failure', raw_value: 'USD', count: 1 }],
  no_rule_documents: [{ filename: 'no_rule.pdf' }],
  confidence: { available: true, avg_confidence: 0.9, avg_ocr_confidence: 0.91 },
  root_cause_counts: [{ root_cause: 'extraction mismatch', count: 1 }],
  diagnosis_counts: [{ reason_code: 'amount_extracted_in_wrong_column', title: 'Amount appears to be assigned to the wrong column', reason_group: 'line_item_column_assignment', confidence: 'high', count: 2 }],
  review_status_counts: [{ status: 'unreviewed', count: 2 }, { status: 'reviewed', count: 1 }],
  field_confidence: [
    { field_id: 'items', field: 'credit-amount', extraction_count: 8, avg_confidence: 0.83, avg_ocr_confidence: 0.85, missing_count: 0 },
    { field_id: 'subtotal-credits-amount', field: 'Subtotal Credits Amount', extraction_count: 3, avg_confidence: 0.93, avg_ocr_confidence: 0.94, missing_count: 0 },
  ],
};

export const runs: Run[] = [{ run_id: 1, evaluator_name: 'settlement_statement', started_at: '2026-05-15T00:00:00Z', completed_at: '2026-05-15T00:00:01Z', status: 'completed', document_count: 4, result_count: 10, warning_count: 2, error_message: null }];
export const logs: { items: LogEntry[]; total: number; limit: number; offset: number } = {
  items: [{ log_id: 1, run_id: 1, filename: 'warning_parse.pdf', level: 'warning', event_type: 'numeric_parse_failure', message: 'Could not parse numeric value from: USD', raw_value: 'USD', normalized_value: null, created_at: '2026-05-15T00:00:00Z' }],
  total: 1,
  limit: 25,
  offset: 0,
};

export const trainingExceptions = {
  items: [
    {
      filename: 'fail_balancing.pdf',
      source_path: '/docs/fail_balancing.pdf',
      exception_path: '/docs/exceptions/fail_balancing.pdf',
      already_exists: false,
      rule_name: 'credit_amounts_equal_subtotal_credits',
      root_cause: 'extraction mismatch',
      notes: 'needs training sample',
      review_status: 'added_to_training',
      expected_total: 250,
      actual_total: 275,
    },
  ],
};
