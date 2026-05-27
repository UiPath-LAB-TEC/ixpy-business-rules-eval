import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import type { EvidenceDetail } from '../../api/types';
import { DocumentViewer } from './DocumentViewer';

const scrollIntoView = vi.fn();
const renderPage = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }));
const getPage = vi.fn((pageNumber: number) => Promise.resolve({
  getViewport: () => ({ width: 612, height: 792 }),
  render: renderPage,
  pageNumber,
}));

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage,
      destroy: vi.fn(),
    }),
  })),
}));

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: '/pdf.worker.min.mjs',
}));

const originalUserAgent = navigator.userAgent;
const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(navigator, 'userAgent', {
    configurable: true,
    value: 'Mozilla/5.0',
  });
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
});

afterEach(() => {
  Object.defineProperty(navigator, 'userAgent', {
    configurable: true,
    value: originalUserAgent,
  });
  HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
});

describe('DocumentViewer', () => {
  test('renders all PDF pages without visible next-page controls', async () => {
    render(<DocumentViewer filename="sample.pdf" evidence={null} />);

    await waitFor(() => expect(screen.getByText('Page 1 / 3')).toBeTruthy());

    expect(screen.getByLabelText('PDF page 1')).toBeTruthy();
    expect(screen.getByLabelText('PDF page 2')).toBeTruthy();
    expect(screen.getByLabelText('PDF page 3')).toBeTruthy();
    await waitFor(() => expect(getPage).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.getByLabelText('PDF page 3').className).toContain('ready'));
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Previous page' })).toBeNull();

    scrollIntoView.mockClear();
    fireEvent.keyDown(screen.getByRole('region', { name: 'Document viewer' }).querySelector('.page-surface')!, { key: 'PageDown' });

    expect(screen.getByText('Page 2 / 3')).toBeTruthy();
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  test('scrolls to the evidence page and places the highlight on that page', async () => {
    const evidence: EvidenceDetail = {
      detail_id: 1,
      filename: 'sample.pdf',
      rule_name: 'sample_rule',
      detail_type: 'included_row',
      evidence_role: 'actual_total',
      source_field_id: 'items',
      source_field: 'amount',
      row_index: 1,
      column_index: 2,
      raw_value: '100.00',
      normalized_value: '100.00',
      amount: 100,
      page_number: 2,
      bbox: { x: 0.2, y: 0.3, width: 0.1, height: 0.05 },
      reason: null,
      severity: 'info',
    };

    render(<DocumentViewer filename="sample.pdf" evidence={evidence} />);

    await waitFor(() => expect(screen.getByText('Page 2 / 3')).toBeTruthy());

    const pageTwo = screen.getByLabelText('PDF page 2');
    expect(pageTwo.querySelector('.highlight-box')).toBeTruthy();
    expect(screen.getByLabelText('PDF page 1').querySelector('.highlight-box')).toBeNull();
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });
});
