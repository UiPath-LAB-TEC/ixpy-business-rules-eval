import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { App } from './App';
import { analytics, dashboard, documentDetail, explanation, logs, runs, totalCreditsExplanation, totalDebitsExplanation, trainingExceptions } from './test/fixtures';

const REVIEW_VIEWER_WIDTH_KEY = 'business-rule-ui.review.viewerWidthPercent';

function mockLocalStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, String(value)),
    removeItem: (key: string) => values.delete(key),
    clear: () => values.clear(),
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    get length() {
      return values.size;
    },
  } as Storage;
}

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const debitRule = {
      ...documentDetail.rules[0],
      rule_name: 'debit_amounts_equal_subtotal_debits',
      rule_passed: 1,
      summary: 'passed',
      root_cause: 'unknown',
    };
    const borrowerBalanceRule = {
      ...documentDetail.rules[0],
      rule_name: 'borrower_balance_fields_are_mutually_exclusive',
      rule_passed: 1,
      summary: 'passed',
      root_cause: 'unknown',
    };
    const shuffledDocumentDetail = {
      ...documentDetail,
      document: { ...documentDetail.document, filename: 'shuffled_rules.pdf' },
      rules: [borrowerBalanceRule, documentDetail.rules[1], debitRule, documentDetail.rules[2], documentDetail.rules[0]].map((rule) => ({ ...rule, filename: 'shuffled_rules.pdf' })),
    };
    const ruleFilteredNextDetail = withFilename(documentDetail, 'rule_filtered_next.pdf');
    const rulePassedCurrentDetail = passedCreditDocument('rule_passed_current.pdf');
    const rulePassedNextDetail = passedCreditDocument('rule_passed_next.pdf');
    if (url.includes('/dashboard')) return json(dashboard);
    if (url.includes('/archive')) return json({ filename: 'fail_balancing.pdf', rule_name: 'credit_amounts_equal_subtotal_credits', source_path: '/docs/fail_balancing.pdf', archive_path: '/docs/archive/fail_balancing.pdf' });
    if (url.includes('/documents/shuffled_rules.pdf') && !url.includes('/file')) return json(shuffledDocumentDetail);
    if (url.includes('/documents/rule_filtered_next.pdf') && !url.includes('/file')) return json(ruleFilteredNextDetail);
    if (url.includes('/documents/rule_passed_current.pdf') && !url.includes('/file')) return json(rulePassedCurrentDetail);
    if (url.includes('/documents/rule_passed_next.pdf') && !url.includes('/file')) return json(rulePassedNextDetail);
    if (url.includes('/documents/next_document.pdf') && !url.includes('/file')) return json({ ...documentDetail, document: { ...documentDetail.document, filename: 'next_document.pdf' } });
    if (url.includes('/documents/fail_balancing.pdf') && !url.includes('/file')) return json(documentDetail);
    if (url.includes('/documents?')) {
      const params = new URL(url, 'http://localhost').searchParams;
      const rule = params.get('rule');
      const status = params.get('status');
      const limit = Number(params.get('limit') ?? 25);
      if (rule === 'credit_amounts_equal_subtotal_credits' && limit === 1000 && status === 'failed') {
        const items = [dashboard.recent_documents[0], documentSummary('rule_filtered_next.pdf', 1)];
        return json({ items, total: items.length, limit, offset: 0 });
      }
      if (rule === 'credit_amounts_equal_subtotal_credits' && limit === 1000 && status === 'passed') {
        const items = [documentSummary('rule_passed_current.pdf', 0), documentSummary('rule_passed_next.pdf', 0)];
        return json({ items, total: items.length, limit, offset: 0 });
      }
      return json({ items: dashboard.recent_documents, total: dashboard.recent_documents.length, limit: 25, offset: 0 });
    }
    if (url.includes('/evaluations/next_document.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json({
      ...explanation,
      result: { ...explanation.result, filename: 'next_document.pdf' },
      details: explanation.details.map((detail) => ({ ...detail, filename: 'next_document.pdf' })),
    });
    if (url.includes('/evaluations/rule_filtered_next.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json(withExplanationFilename('rule_filtered_next.pdf'));
    if (url.includes('/evaluations/rule_passed_current.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json(withExplanationFilename('rule_passed_current.pdf', 1));
    if (url.includes('/evaluations/rule_passed_next.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json(withExplanationFilename('rule_passed_next.pdf', 1));
    if (url.includes('/evaluations/shuffled_rules.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json({
      ...explanation,
      result: { ...explanation.result, filename: 'shuffled_rules.pdf' },
      details: explanation.details.map((detail) => ({ ...detail, filename: 'shuffled_rules.pdf' })),
    });
    if (url.includes('/evaluations/fail_balancing.pdf/total_credits_equal_subtotal_credits_plus_due_from_borrower/explanation')) return json(totalCreditsExplanation);
    if (url.includes('/evaluations/fail_balancing.pdf/total_debits_equal_subtotal_debits_plus_due_to_borrower/explanation')) return json(totalDebitsExplanation);
    if (url.includes('/evaluations/fail_balancing.pdf/credit_amounts_equal_subtotal_credits/explanation')) return json(explanation);
    if (url.includes('/analytics')) return json(analytics);
    if (url.includes('/runs')) return json(runs);
    if (url.includes('/logs')) return json(logs);
    if (url.includes('/training-exceptions/export')) return json({ manifest_path: '/docs/exceptions/manifest.csv', exported_count: 1 });
    if (url.includes('/training-exceptions/fail_balancing.pdf')) return json({ removed: true });
    if (url.includes('/training-exceptions')) return json(trainingExceptions);
    if (url.includes('/annotations/fail_balancing.pdf/credit_amounts_equal_subtotal_credits/recompute')) return json({
      original: { expected_total: 250, actual_total: 275, difference: 25, rule_passed: false },
      corrected: { expected_total: 250, actual_total: 125, difference: -125, rule_passed: false },
    });
    if (url.includes('/annotations/fail_balancing.pdf/credit_amounts_equal_subtotal_credits')) return json({ annotations: [] });
    if (url.includes('/training-exception')) return json({ filename: 'fail_balancing.pdf', source_path: '/docs/fail_balancing.pdf', exception_path: '/docs/exceptions/fail_balancing.pdf', already_exists: false });
    if (url.includes('/reviews/')) return json({ status: 'reviewed', root_cause: 'extraction mismatch', notes: 'saved' });
    return json({});
  });
}

function withFilename(detail: typeof documentDetail, filename: string) {
  return {
    ...detail,
    document: { ...detail.document, filename },
    rules: detail.rules.map((rule) => ({ ...rule, filename })),
  };
}

function passedCreditDocument(filename: string) {
  return {
    ...documentDetail,
    document: { ...documentDetail.document, filename },
    rules: [
      {
        ...documentDetail.rules[0],
        filename,
        rule_passed: 1,
        actual_total: documentDetail.rules[0].expected_total,
        difference: 0,
        absolute_difference: 0,
        root_cause: 'unknown',
        summary: 'passed',
      },
    ],
  };
}

function documentSummary(filename: string, rulesFailed: number) {
  return {
    ...dashboard.recent_documents[0],
    filename,
    rules_failed: rulesFailed,
    rules_passed: rulesFailed === 0 ? 1 : 0,
    pass_rate: rulesFailed === 0 ? 100 : 0,
    largest_absolute_difference: rulesFailed === 0 ? 0 : 25,
    review_status: 'unreviewed',
  };
}

function withExplanationFilename(filename: string, rulePassed = 0) {
  return {
    ...explanation,
    result: {
      ...explanation.result,
      filename,
      rule_passed: rulePassed,
      actual_total: rulePassed ? explanation.result.expected_total : explanation.result.actual_total,
      difference: rulePassed ? 0 : explanation.result.difference,
      absolute_difference: rulePassed ? 0 : explanation.result.absolute_difference,
      root_cause: rulePassed ? 'unknown' : explanation.result.root_cause,
      summary: rulePassed ? 'passed' : explanation.result.summary,
    },
    details: explanation.details.map((detail) => ({ ...detail, filename })),
  };
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('business-rule-ui app', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch());
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: mockLocalStorage(),
    });
    window.history.pushState(null, '', '/dashboard');
  });

  test('renders dashboard without console errors', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy();
    expect(await screen.findByText('credit_amounts_equal_subtotal_credits')).toBeTruthy();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  test('collapses the far-left navigation by default and can expand it', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy();
    const shell = document.querySelector('.app-shell');

    expect(shell?.classList.contains('sidebar-collapsed')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));

    expect(shell?.classList.contains('sidebar-collapsed')).toBe(false);
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));

    expect(shell?.classList.contains('sidebar-collapsed')).toBe(true);
  });

  test('renders review workflow evidence and fallback-free highlight data', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());
    expect(screen.getByRole('region', { name: 'Document viewer' })).toBeTruthy();
    expect(screen.getByText('Computed sums')).toBeTruthy();
    expect(screen.getByText('Regular field extractions')).toBeTruthy();
    expect(screen.getByText('Table data extractions')).toBeTruthy();
    expect(screen.getByText('Excluded table rows')).toBeTruthy();
    expect(screen.getAllByText('Subtotal Credits Amount').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Credit Amount').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Statement Table > Summary Totals and Balance / Subtotal Credits Amount')).toBeNull();
    expect(screen.queryByText('Statement Table > Credits / Credit Amount')).toBeNull();
  });

  test('renders diagnosis and classifier evidence for failed rules', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    const diagnosisRegion = await screen.findByRole('region', { name: 'Failure diagnosis' });

    expect(within(diagnosisRegion).getByText('Amount appears to be assigned to the wrong column')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('high confidence')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('The mismatch is consistent with a line item amount being extracted under credits instead of debits.')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('Verify the highlighted row amount and confirm whether it belongs in the debit or credit column.')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('amount_extracted_in_wrong_column')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('line_item_column_assignment')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('Aggregate Adjustment')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('twice the aggregate adjustment is approximately the gap')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('15')).toBeTruthy();
    expect(within(diagnosisRegion).getByText('-452.48')).toBeTruthy();
  });

  test('omits row column for regular field evidence and keeps value columns ordered', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Regular field extractions')).toBeTruthy());

    const regularFieldsTable = within(screen.getByRole('region', { name: 'Regular field extractions' })).getByRole('table');
    const tableRowsTable = within(screen.getByRole('region', { name: 'Table data extractions' })).getByRole('table');
    const regularHeaders = within(regularFieldsTable).getAllByRole('columnheader').map((header) => header.textContent);
    const tableHeaders = within(tableRowsTable).getAllByRole('columnheader').map((header) => header.textContent);

    expect(regularHeaders).toEqual(['Role', 'Field', 'Amount', 'Normalized', 'Raw']);
    expect(tableHeaders).toEqual(['Role', 'Field', 'Row', 'Amount', 'Normalized', 'Raw']);
    expect(within(tableRowsTable).getByText('Credit Amount')).toBeTruthy();
    expect(within(tableRowsTable).queryByText('credit-amount')).toBeNull();
  });

  test('shows borrower balance fields as regular evidence', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: /total_credits_equal_subtotal_credits_plus_due_from_borrower/ }));

    await waitFor(() => expect(screen.getByText('Total credits equal subtotal credits plus due from borrower')).toBeTruthy());
    expect(screen.getAllByText('Due From Borrower').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('due-from-borrower / Due From Borrower')).toBeNull();
    expect(screen.getAllByText('$50.00').length).toBeGreaterThanOrEqual(1);

    fireEvent.click(await screen.findByRole('button', { name: /total_debits_equal_subtotal_debits_plus_due_to_borrower/ }));

    await waitFor(() => expect(screen.getByText('Total debits equal subtotal debits plus due to borrower')).toBeTruthy());
    expect(screen.getAllByText('Due To Borrower').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('due-to-borrower / Due To Borrower')).toBeNull();
    expect(screen.getAllByText('$25.00').length).toBeGreaterThanOrEqual(1);
  });

  test('rule names in the selector render as selectable text', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    const ruleChoice = await screen.findByRole('button', { name: /credit_amounts_equal_subtotal_credits/ });
    const ruleName = ruleChoice.querySelector('.rule-choice-name');

    expect(ruleChoice.tagName).not.toBe('BUTTON');
    expect(ruleName?.textContent).toBe('credit_amounts_equal_subtotal_credits');
  });

  test('orders review rules consistently and selects the first failing rule', async () => {
    window.history.pushState(null, '', '/review/shuffled_rules.pdf');
    render(<App />);
    expect(await screen.findByText('shuffled_rules.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());

    const displayedRuleNames = Array.from(document.querySelectorAll('.rule-choice-name')).map((node) => node.textContent);

    expect(displayedRuleNames).toEqual([
      'debit_amounts_equal_subtotal_debits',
      'credit_amounts_equal_subtotal_credits',
      'total_debits_equal_subtotal_debits_plus_due_to_borrower',
      'total_credits_equal_subtotal_credits_plus_due_from_borrower',
      'borrower_balance_fields_are_mutually_exclusive',
    ]);
    expect(screen.getByRole('button', { name: /credit_amounts_equal_subtotal_credits/ }).classList.contains('active')).toBe(true);
  });

  test('document viewer exposes working zoom controls', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    const zoomIn = await screen.findByRole('button', { name: 'Zoom in' });
    const zoomOut = await screen.findByRole('button', { name: 'Zoom out' });
    const resetZoom = await screen.findByRole('button', { name: 'Reset zoom' });
    expect(screen.getByText('100%')).toBeTruthy();
    fireEvent.click(zoomIn);
    expect(screen.getByText('125%')).toBeTruthy();
    fireEvent.click(zoomOut);
    expect(screen.getByText('100%')).toBeTruthy();
    fireEvent.click(resetZoom);
    expect(screen.getByText('100%')).toBeTruthy();
  });

  test('review split between document viewer and business rules is adjustable and persisted', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());

    const layout = document.querySelector('.review-layout') as HTMLElement;
    const resizer = screen.getByRole('separator', { name: 'Resize document viewer and business rules' });
    layout.getBoundingClientRect = () => ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 1000,
      bottom: 800,
      width: 1000,
      height: 800,
      toJSON: () => ({}),
    });

    expect(layout.style.getPropertyValue('--review-viewer-width')).toBe('38%');

    fireEvent.pointerDown(resizer, { pointerId: 1, clientX: 380 });
    fireEvent.pointerMove(resizer, { pointerId: 1, clientX: 500 });
    fireEvent.pointerUp(resizer, { pointerId: 1 });

    await waitFor(() => expect(layout.style.getPropertyValue('--review-viewer-width')).toBe('50%'));
    expect(window.localStorage.getItem(REVIEW_VIEWER_WIDTH_KEY)).toBe('50');

    cleanup();
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    const restoredLayout = document.querySelector('.review-layout') as HTMLElement;
    expect(restoredLayout.style.getPropertyValue('--review-viewer-width')).toBe('50%');
  });

  test('review page navigates to the next document from the current documents list', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();
    fireEvent.click(screen.getAllByTitle('Open review')[0]);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    expect(window.location.pathname).toBe('/review/fail_balancing.pdf');
    expect(window.location.search).toContain('status=failed');

    fireEvent.click(await screen.findByRole('button', { name: 'Next failed doc' }));

    expect(await screen.findByRole('heading', { name: 'next_document.pdf' })).toBeTruthy();
    expect(window.location.pathname).toBe('/review/next_document.pdf');
    expect(window.location.search).toContain('sort=highest_value');
  });

  test('review form resets after saving and moving to the next document', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();
    fireEvent.click(screen.getAllByTitle('Open review')[0]);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    fireEvent.change(await screen.findByLabelText('Review status'), { target: { value: 'reviewed' } });
    fireEvent.change(screen.getByLabelText('Review notes'), { target: { value: 'previous document note' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Review' }));
    expect(await screen.findByText('Saved')).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: 'Next failed doc' }));

    expect(await screen.findByRole('heading', { name: 'next_document.pdf' })).toBeTruthy();
    await waitFor(() => expect(screen.queryByText('Saved')).toBeNull());
    expect((screen.getByLabelText('Review status') as HTMLSelectElement).value).toBe('unreviewed');
    expect((screen.getByLabelText('Review notes') as HTMLTextAreaElement).value).toBe('');
  });

  test('adds the current document to training exceptions from the review header', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    const addToTrainingButton = await screen.findByRole('button', { name: 'Add to training' });
    await waitFor(() => expect(addToTrainingButton.hasAttribute('disabled')).toBe(false));
    fireEvent.click(addToTrainingButton);

    expect(await screen.findByRole('button', { name: 'Added' })).toBeTruthy();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/documents/fail_balancing.pdf/training-exception?rule_name=credit_amounts_equal_subtotal_credits'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('archives bad training data from the review header', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    const archiveButton = await screen.findByRole('button', { name: 'Archive' });
    await waitFor(() => expect(archiveButton.hasAttribute('disabled')).toBe(false));
    fireEvent.click(archiveButton);

    await waitFor(() => expect(archiveButton.textContent).toContain('Archived'));
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/documents/fail_balancing.pdf/archive?rule_name=credit_amounts_equal_subtotal_credits'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('review header actions persist immediately and keyboard shortcuts advance within the failed queue', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf?status=failed&sort=highest_value&search=balancing');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());

    fireEvent.click(await screen.findByRole('button', { name: 'Mark reviewed' }));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/reviews/fail_balancing.pdf/credit_amounts_equal_subtotal_credits'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"status":"reviewed"') }),
    ));

    fireEvent.keyDown(window, { key: 'n' });

    expect(await screen.findByRole('heading', { name: 'next_document.pdf' })).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());
    expect(window.location.search).toContain('sort=highest_value');
    expect(window.location.search).toContain('search=balancing');

    fireEvent.keyDown(window, { key: 'i' });
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/reviews/next_document.pdf/credit_amounts_equal_subtotal_credits'),
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"status":"ignored"') }),
    ));

    fireEvent.keyDown(window, { key: 'a' });
    expect(await screen.findByRole('button', { name: 'Added' })).toBeTruthy();
  });

  test('documents default to highest value sort and preserve it when opening review', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();
    expect((screen.getByLabelText('Sort documents') as HTMLSelectElement).value).toBe('highest_value');

    fireEvent.click(screen.getAllByTitle('Open review')[0]);

    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    expect(window.location.search).toContain('sort=highest_value');
  });

  test('documents table headers update the server-backed sort order', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();

    const expectedHeaders = ['Filename', 'Failed', 'Pass Rate', 'Worst Diff', 'Warnings', 'Review'];
    for (const header of expectedHeaders) {
      expect(screen.getByRole('button', { name: new RegExp(`Sort by ${header}`) })).toBeTruthy();
    }

    fireEvent.click(screen.getByRole('button', { name: /Sort by Filename/ }));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/documents?status=failed&sort=filename&direction=asc&limit=25'),
      expect.any(Object),
    ));

    fireEvent.click(screen.getByRole('button', { name: /Sort by Filename/ }));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/documents?status=failed&sort=filename&direction=desc&limit=25'),
      expect.any(Object),
    ));
  });

  test('documents can be filtered by rule name and preserve the filter when opening review', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();

    const ruleFilter = screen.getByLabelText('Rule filter') as HTMLSelectElement;
    expect(ruleFilter.tagName).toBe('SELECT');

    fireEvent.change(ruleFilter, { target: { value: 'credit_amounts_equal_subtotal_credits' } });

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('rule=credit_amounts_equal_subtotal_credits'),
      expect.any(Object),
    ));

    fireEvent.click(screen.getAllByTitle('Open review')[0]);

    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    expect(window.location.search).toContain('rule=credit_amounts_equal_subtotal_credits');
  });

  test('documents can be filtered by review stage and preserve the filter when opening review', async () => {
    window.history.pushState(null, '', '/documents');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Documents' })).toBeTruthy();

    const reviewFilter = screen.getByLabelText('Review stage filter') as HTMLSelectElement;
    expect(reviewFilter.tagName).toBe('SELECT');

    fireEvent.change(reviewFilter, { target: { value: 'ignored' } });

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('review_status=ignored'),
      expect.any(Object),
    ));

    fireEvent.click(screen.getAllByTitle('Open review')[0]);

    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    expect(window.location.search).toContain('review_status=ignored');
  });

  test('review next navigation stays within the rule-filtered failed queue', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf?status=failed&sort=highest_value&rule=credit_amounts_equal_subtotal_credits');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    fireEvent.click(await screen.findByRole('button', { name: 'Next failed doc' }));

    expect(await screen.findByRole('heading', { name: 'rule_filtered_next.pdf' })).toBeTruthy();
    expect(window.location.pathname).toBe('/review/rule_filtered_next.pdf');
    expect(window.location.search).toContain('rule=credit_amounts_equal_subtotal_credits');
  });

  test('review next navigation also works for a rule-filtered passed queue', async () => {
    window.history.pushState(null, '', '/review/rule_passed_current.pdf?status=passed&sort=filename&rule=credit_amounts_equal_subtotal_credits');
    render(<App />);
    expect(await screen.findByText('rule_passed_current.pdf')).toBeTruthy();
    await waitFor(() => expect(screen.getByText('Credit line items equal subtotal credits')).toBeTruthy());

    fireEvent.click(await screen.findByRole('button', { name: 'Next failed doc' }));

    expect(await screen.findByRole('heading', { name: 'rule_passed_next.pdf' })).toBeTruthy();
    expect(window.location.pathname).toBe('/review/rule_passed_next.pdf');
    expect(window.location.search).toContain('status=passed');
    expect(window.location.search).toContain('rule=credit_amounts_equal_subtotal_credits');
  });

  test('rules page lists borrower balance fields and formulas', async () => {
    window.history.pushState(null, '', '/rules');
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Rules' })).toBeTruthy();
    expect(screen.getByText('borrower_balance_fields_are_mutually_exclusive')).toBeTruthy();
    expect(screen.getByText('total_debits_equal_subtotal_debits_plus_due_to_borrower')).toBeTruthy();
    expect(screen.getByText('total_credits_equal_subtotal_credits_plus_due_from_borrower')).toBeTruthy();
    expect(screen.getByText(/subtotal debits \+ due to borrower/)).toBeTruthy();
    expect(screen.getByText(/subtotal credits \+ due from borrower/)).toBeTruthy();
  });

  test('dashboard renders review status metrics and recurring root causes', async () => {
    render(<App />);

    expect(await screen.findByText('Unreviewed Failed')).toBeTruthy();
    expect(screen.getByText('Added to Training')).toBeTruthy();
    expect(screen.getByText('Ignored')).toBeTruthy();
    expect(screen.getByText('Top Recurring Root Causes')).toBeTruthy();
    expect(screen.getByText('missing due-from-borrower fields')).toBeTruthy();
  });

  test('training exception queue lists files and supports remove and export actions', async () => {
    window.history.pushState(null, '', '/training-exceptions');
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Training Exceptions' })).toBeTruthy();
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();
    expect(screen.getByText('/docs/exceptions/fail_balancing.pdf')).toBeTruthy();
    expect(screen.getByText('extraction mismatch')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Export queue' }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/training-exceptions/export'),
      expect.objectContaining({ method: 'POST' }),
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining('/api/training-exceptions/fail_balancing.pdf'),
      expect.objectContaining({ method: 'DELETE' }),
    ));
  });

  test('review UI supports inline annotations and side-by-side corrected recomputation', async () => {
    window.history.pushState(null, '', '/review/fail_balancing.pdf');
    render(<App />);
    expect(await screen.findByText('fail_balancing.pdf')).toBeTruthy();

    expect(await screen.findByText('Evidence annotations')).toBeTruthy();
    expect(await screen.findByText('Original result')).toBeTruthy();
    fireEvent.change(screen.getAllByLabelText('Corrected amount')[0], { target: { value: '125.00' } });
    fireEvent.change(screen.getAllByLabelText('Annotation root cause')[0], { target: { value: 'duplicate row' } });
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Include row' })[0]);
    fireEvent.change(screen.getAllByLabelText('Annotation notes')[0], { target: { value: 'remove duplicated row' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save annotations' }));

    expect(await screen.findByText('Annotations saved')).toBeTruthy();
    expect(screen.getByText('Corrected result')).toBeTruthy();
    expect(screen.getAllByText('$250.00').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('$125.00')).toBeTruthy();
  });

  test('renders analytics and runs pages with controlled states', async () => {
    window.history.pushState(null, '', '/analytics');
    render(<App />);
    expect(await screen.findByText('Pass Rate by Rule')).toBeTruthy();
    cleanup();
    window.history.pushState(null, '', '/runs');
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Runs / Logs' })).toBeTruthy();
    expect(await screen.findByText('Could not parse numeric value from: USD')).toBeTruthy();
  });
});
