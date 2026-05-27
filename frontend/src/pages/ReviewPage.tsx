import { Archive, ArrowLeft, ArrowRight, Check, FolderPlus, Hammer, XCircle } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react';
import { api } from '../api/client';
import type { EvidenceDetail, Explanation } from '../api/types';
import { DocumentViewer } from '../components/document-viewer/DocumentViewer';
import { RuleEvidencePanel } from '../components/rule-evidence/RuleEvidencePanel';
import { StateBlock, useAsync } from './useAsync';

const REVIEW_VIEWER_WIDTH_KEY = 'business-rule-ui.review.viewerWidthPercent';
const DEFAULT_VIEWER_WIDTH_PERCENT = 38;
const MIN_VIEWER_WIDTH_PERCENT = 28;
const MAX_VIEWER_WIDTH_PERCENT = 58;
const REVIEW_RULE_ORDER = [
  'debit_amounts_equal_subtotal_debits',
  'credit_amounts_equal_subtotal_credits',
  'total_debits_equal_subtotal_debits_plus_due_to_borrower',
  'total_credits_equal_subtotal_credits_plus_due_from_borrower',
  'total_credits_equal_subtotal_credits_plus_due_from_buyer',
  'total_debits_balance_total_credits',
  'borrower_balance_fields_are_mutually_exclusive',
];
const REVIEW_RULE_RANK = new Map(REVIEW_RULE_ORDER.map((ruleName, index) => [ruleName, index]));

export function ReviewPage({
  filename,
  listSearch,
  navigate,
}: {
  filename: string;
  listSearch: string;
  navigate: (path: string) => void;
}) {
  const reviewLayoutRef = useRef<HTMLDivElement | null>(null);
  const resizeCleanupRef = useRef<(() => void) | null>(null);
  const { data, error, loading } = useAsync(() => api.document(filename), [filename]);
  const sourceSearch = listSearch || '?status=failed&sort=highest_value';
  const filteredRule = useMemo(() => new URLSearchParams(sourceSearch).get('rule'), [sourceSearch]);
  const navigationParams = useMemo(() => {
    const params = new URLSearchParams(sourceSearch);
    if (!params.has('status')) params.set('status', 'failed');
    if (!params.has('sort')) params.set('sort', 'highest_value');
    params.set('limit', '1000');
    params.delete('offset');
    return params;
  }, [sourceSearch]);
  const { data: navigationList } = useAsync(() => api.documents(navigationParams), [navigationParams.toString()]);
  const sortedRules = useMemo(() => stableRuleOrder(data?.rules ?? []), [data?.rules]);
  const initialRule = useMemo(() => {
    if (filteredRule && sortedRules.some((rule) => rule.rule_name === filteredRule)) return filteredRule;
    const failed = sortedRules.find((rule) => rule.rule_passed === 0 || rule.rule_passed === false);
    return failed?.rule_name ?? sortedRules[0]?.rule_name ?? null;
  }, [filteredRule, sortedRules]);
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceDetail | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [exceptionStatus, setExceptionStatus] = useState<'idle' | 'copying' | 'copied' | 'exists'>('idle');
  const [exceptionError, setExceptionError] = useState<string | null>(null);
  const [archiveStatus, setArchiveStatus] = useState<'idle' | 'moving' | 'archived'>('idle');
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [reviewActionStatus, setReviewActionStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [reviewActionError, setReviewActionError] = useState<string | null>(null);
  const [viewerWidthPercent, setViewerWidthPercent] = useState(readPersistedViewerWidthPercent);
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => () => {
    resizeCleanupRef.current?.();
  }, []);

  useEffect(() => {
    setSelectedRule(initialRule);
    setExplanation(null);
    setSelectedEvidence(null);
    setExplanationError(null);
    setExceptionStatus('idle');
    setExceptionError(null);
    setArchiveStatus('idle');
    setArchiveError(null);
    setReviewActionStatus('idle');
    setReviewActionError(null);
  }, [filename, initialRule]);

  useEffect(() => {
    if (!selectedRule) return;
    setExplanation(null);
    setSelectedEvidence(null);
    setExplanationError(null);
    api.explanation(filename, selectedRule)
      .then((next) => {
        setExplanation(next);
        const firstEvidence = next.details.find((row) => row.detail_type !== 'computed_value') ?? null;
        setSelectedEvidence(firstEvidence);
      })
      .catch((err: unknown) => setExplanationError(err instanceof Error ? err.message : 'Rule explanation failed'));
  }, [filename, selectedRule]);

  const documents = navigationList?.items ?? [];
  const documentIndex = documents.findIndex((doc) => doc.filename === filename);
  const previousDocument = documentIndex > 0 ? documents[documentIndex - 1] : null;
  const nextDocument = documentIndex >= 0 && documentIndex < documents.length - 1 ? documents[documentIndex + 1] : null;

  function reviewPath(nextFilename: string) {
    return `/review/${encodeURIComponent(nextFilename)}${sourceSearch}`;
  }

  async function markReviewStatus(status: 'reviewed' | 'ignored' | 'needs_extraction_fix' | 'added_to_training') {
    if (!selectedRule) return;
    setReviewActionStatus('saving');
    setReviewActionError(null);
    try {
      await api.saveReview(filename, selectedRule, {
        status,
        root_cause: explanation?.result.review_root_cause ?? explanation?.result.root_cause ?? null,
        notes: explanation?.result.review_notes ?? '',
      });
      setReviewActionStatus('saved');
    } catch (err: unknown) {
      setReviewActionStatus('idle');
      setReviewActionError(err instanceof Error ? err.message : 'Could not save review');
    }
  }

  async function addTrainingException() {
    if (!selectedRule) return;
    setExceptionStatus('copying');
    setExceptionError(null);
    try {
      const result = await api.addTrainingException(filename, selectedRule);
      setExceptionStatus(result.already_exists ? 'exists' : 'copied');
      await markReviewStatus('added_to_training');
    } catch (err: unknown) {
      setExceptionStatus('idle');
      setExceptionError(err instanceof Error ? err.message : 'Could not copy document');
    }
  }

  async function archiveDocument() {
    if (!selectedRule) return;
    setArchiveStatus('moving');
    setArchiveError(null);
    try {
      await api.archiveDocument(filename, selectedRule);
      setArchiveStatus('archived');
    } catch (err: unknown) {
      setArchiveStatus('idle');
      setArchiveError(err instanceof Error ? err.message : 'Could not archive document');
    }
  }

  function goNext() {
    if (nextDocument) navigate(reviewPath(nextDocument.filename));
  }

  function setViewerWidth(nextPercent: number) {
    const clamped = clampViewerWidth(nextPercent);
    setViewerWidthPercent(clamped);
    persistViewerWidthPercent(clamped);
  }

  function setViewerWidthFromPointer(clientX: number) {
    const layout = reviewLayoutRef.current;
    if (!layout) return;
    const bounds = layout.getBoundingClientRect();
    if (bounds.width <= 0) return;
    setViewerWidth(((clientX - bounds.left) / bounds.width) * 100);
  }

  function beginResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    resizeCleanupRef.current?.();
    setIsResizing(true);
    setViewerWidthFromPointer(event.clientX);

    const pointerId = event.pointerId;
    const onPointerMove = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      setViewerWidthFromPointer(moveEvent.clientX);
    };
    const stopResize = (endEvent: PointerEvent) => {
      if (endEvent.pointerId !== pointerId) return;
      resizeCleanupRef.current?.();
      resizeCleanupRef.current = null;
      setIsResizing(false);
    };
    const cleanup = () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', stopResize);
      window.removeEventListener('pointercancel', stopResize);
    };

    resizeCleanupRef.current = cleanup;
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', stopResize);
    window.addEventListener('pointercancel', stopResize);
  }

  function onResizeKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const direction = event.key === 'ArrowLeft' ? -2 : 2;
    setViewerWidth(viewerWidthPercent + direction);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      const key = event.key.toLowerCase();
      if (key === 'a') {
        event.preventDefault();
        void addTrainingException();
      } else if (key === 'r') {
        event.preventDefault();
        void markReviewStatus('reviewed');
      } else if (key === 'i') {
        event.preventDefault();
        void markReviewStatus('ignored');
      } else if (key === 'n') {
        event.preventDefault();
        goNext();
      } else if (/^[1-4]$/.test(key)) {
        const index = Number(key) - 1;
        const rule = sortedRules[index];
        if (rule) {
          event.preventDefault();
          setSelectedRule(rule.rule_name);
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  return (
    <section className="page review-page">
      <header className="page-header">
        <div>
          <h1>{filename}</h1>
          <p>Document viewer, failed-rule math, structured evidence, warnings, and persisted review notes.</p>
          {(exceptionError || archiveError || reviewActionError) && <p className="error-text">{exceptionError ?? archiveError ?? reviewActionError}</p>}
          {reviewActionStatus === 'saved' && <p className="saved-label">Saved</p>}
        </div>
        <div className="review-document-nav" aria-label="Document navigation">
          <button disabled={!selectedRule || reviewActionStatus === 'saving'} onClick={() => markReviewStatus('reviewed')}>
            <Check size={17} aria-hidden />
            Mark reviewed
          </button>
          <button disabled={!selectedRule || reviewActionStatus === 'saving'} onClick={() => markReviewStatus('ignored')}>
            <XCircle size={17} aria-hidden />
            Ignore
          </button>
          <button disabled={!selectedRule || reviewActionStatus === 'saving'} onClick={() => markReviewStatus('needs_extraction_fix')}>
            <Hammer size={17} aria-hidden />
            Needs extraction fix
          </button>
          <button
            className="primary-button"
            disabled={exceptionStatus === 'copying' || exceptionStatus === 'copied' || exceptionStatus === 'exists'}
            onClick={addTrainingException}
          >
            <FolderPlus size={17} aria-hidden />
            {exceptionStatus === 'copying' && 'Adding...'}
            {exceptionStatus === 'copied' && 'Added'}
            {exceptionStatus === 'exists' && 'Already added'}
            {exceptionStatus === 'idle' && 'Add to training'}
          </button>
          <button
            disabled={!selectedRule || archiveStatus === 'moving' || archiveStatus === 'archived'}
            onClick={archiveDocument}
          >
            <Archive size={17} aria-hidden />
            {archiveStatus === 'moving' && 'Archiving...'}
            {archiveStatus === 'archived' && 'Archived'}
            {archiveStatus === 'idle' && 'Archive'}
          </button>
          <button disabled={!previousDocument} onClick={() => previousDocument && navigate(reviewPath(previousDocument.filename))}>
            <ArrowLeft size={17} aria-hidden />
            Previous document
          </button>
          <span>
            {documentIndex >= 0 ? `${documentIndex + 1} / ${documents.length}` : 'Not in current list'}
          </span>
          <button className="primary-button next-failed-button" disabled={!nextDocument} onClick={goNext}>
            Next failed doc
            <ArrowRight size={17} aria-hidden />
          </button>
        </div>
      </header>
      <StateBlock loading={loading} error={error ?? explanationError} empty={data?.rules.length === 0} />
      {data && (
        <div
          ref={reviewLayoutRef}
          className={isResizing ? 'review-layout is-resizing' : 'review-layout'}
          style={{ '--review-viewer-width': `${viewerWidthPercent}%` } as CSSProperties}
        >
          <DocumentViewer filename={filename} evidence={selectedEvidence} />
          <div
            aria-label="Resize document viewer and business rules"
            aria-orientation="vertical"
            aria-valuemax={MAX_VIEWER_WIDTH_PERCENT}
            aria-valuemin={MIN_VIEWER_WIDTH_PERCENT}
            aria-valuenow={viewerWidthPercent}
            className="review-resizer"
            role="separator"
            tabIndex={0}
            title="Resize document viewer and business rules"
            onKeyDown={onResizeKeyDown}
            onPointerDown={beginResize}
          />
          <RuleEvidencePanel
            filename={filename}
            rules={sortedRules}
            selectedRule={selectedRule}
            explanation={explanation}
            onSelectRule={setSelectedRule}
            onSelectEvidence={setSelectedEvidence}
          />
        </div>
      )}
    </section>
  );
}

function stableRuleOrder<T extends { rule_name: string }>(rules: T[]): T[] {
  return [...rules].sort((left, right) => {
    const leftRank = REVIEW_RULE_RANK.get(left.rule_name) ?? Number.MAX_SAFE_INTEGER;
    const rightRank = REVIEW_RULE_RANK.get(right.rule_name) ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.rule_name.localeCompare(right.rule_name);
  });
}

function readPersistedViewerWidthPercent() {
  if (typeof window === 'undefined') return DEFAULT_VIEWER_WIDTH_PERCENT;
  try {
    const rawValue = window.localStorage.getItem(REVIEW_VIEWER_WIDTH_KEY);
    if (!rawValue) return DEFAULT_VIEWER_WIDTH_PERCENT;
    return clampViewerWidth(Number(rawValue));
  } catch {
    return DEFAULT_VIEWER_WIDTH_PERCENT;
  }
}

function persistViewerWidthPercent(value: number) {
  try {
    window.localStorage.setItem(REVIEW_VIEWER_WIDTH_KEY, String(value));
  } catch {
    // Ignore storage failures; resizing should still work for the current session.
  }
}

function clampViewerWidth(value: number) {
  if (!Number.isFinite(value)) return DEFAULT_VIEWER_WIDTH_PERCENT;
  return Math.min(MAX_VIEWER_WIDTH_PERCENT, Math.max(MIN_VIEWER_WIDTH_PERCENT, Number(value.toFixed(1))));
}
