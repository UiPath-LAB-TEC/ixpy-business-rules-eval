import { ArrowDown, ArrowRight, ArrowUp, ChevronsUpDown, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { api } from '../api/client';
import { StateBlock, useAsync } from './useAsync';

type SortDirection = 'asc' | 'desc';

type SortColumn = {
  label: string;
  value: string;
  defaultDirection: SortDirection;
};

const SORT_COLUMNS: SortColumn[] = [
  { label: 'Filename', value: 'filename', defaultDirection: 'asc' },
  { label: 'Failed', value: 'failed_rules', defaultDirection: 'desc' },
  { label: 'Pass Rate', value: 'pass_rate', defaultDirection: 'asc' },
  { label: 'Worst Diff', value: 'largest_absolute_difference', defaultDirection: 'desc' },
  { label: 'Warnings', value: 'warning_count', defaultDirection: 'desc' },
  { label: 'Review', value: 'review_status', defaultDirection: 'asc' },
];

const RULE_FILTER_OPTIONS = [
  'debit_amounts_equal_subtotal_debits',
  'credit_amounts_equal_subtotal_credits',
  'total_debits_equal_subtotal_debits_plus_due_to_borrower',
  'total_credits_equal_subtotal_credits_plus_due_from_borrower',
  'total_credits_equal_subtotal_credits_plus_due_from_buyer',
  'total_debits_balance_total_credits',
  'borrower_balance_fields_are_mutually_exclusive',
];

const REVIEW_STATUS_OPTIONS = [
  { value: 'unreviewed', label: 'Unreviewed' },
  { value: 'in_review', label: 'In review' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'ignored', label: 'Ignored' },
  { value: 'needs_extraction_fix', label: 'Needs extraction fix' },
  { value: 'added_to_training', label: 'Added to training' },
  { value: 'archived', label: 'Archived' },
];

const DEFAULT_DIRECTIONS = new Map<string, SortDirection>([
  ['highest_value', 'desc'],
  ...SORT_COLUMNS.map((column) => [column.value, column.defaultDirection] as const),
]);

export function DocumentsPage({ navigate }: { navigate: (path: string) => void }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('failed');
  const [rule, setRule] = useState('');
  const [reviewStatus, setReviewStatus] = useState('');
  const [sort, setSort] = useState('highest_value');
  const [direction, setDirection] = useState<SortDirection>('desc');
  const params = useMemo(() => {
    const next = new URLSearchParams({ status, sort, direction, limit: '25' });
    if (search) next.set('search', search);
    if (rule.trim()) next.set('rule', rule.trim());
    if (reviewStatus) next.set('review_status', reviewStatus);
    return next;
  }, [search, status, rule, reviewStatus, sort, direction]);
  const { data, error, loading } = useAsync(() => api.documents(params), [params.toString()]);

  function updateSort(nextSort: string) {
    setSort((currentSort) => {
      if (currentSort === nextSort) {
        setDirection((currentDirection) => (currentDirection === 'asc' ? 'desc' : 'asc'));
        return currentSort;
      }
      setDirection(DEFAULT_DIRECTIONS.get(nextSort) ?? 'desc');
      return nextSort;
    });
  }

  function selectSort(nextSort: string) {
    setSort(nextSort);
    setDirection(DEFAULT_DIRECTIONS.get(nextSort) ?? 'desc');
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Documents</h1>
          <p>Search, filter, and sort rule-evaluated documents.</p>
        </div>
      </header>
      <div className="toolbar">
        <label className="search-box">
          <Search size={17} aria-hidden />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search filename" />
        </label>
        <select aria-label="Status filter" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="failed">Failed</option>
          <option value="passed">Passed</option>
          <option value="">All evaluated</option>
        </select>
        <select aria-label="Rule filter" value={rule} onChange={(event) => setRule(event.target.value)}>
          <option value="">All rules</option>
          {RULE_FILTER_OPTIONS.map((ruleName) => (
            <option key={ruleName} value={ruleName}>{ruleName}</option>
          ))}
        </select>
        <select aria-label="Review stage filter" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
          <option value="">All review stages</option>
          {REVIEW_STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select aria-label="Sort documents" value={sort} onChange={(event) => selectSort(event.target.value)}>
          <option value="highest_value">Highest value first</option>
          <option value="failed_rules">Failed-rule count</option>
          <option value="largest_absolute_difference">Largest difference</option>
          <option value="pass_rate">Lowest pass rate</option>
          <option value="filename">Filename</option>
          <option value="warning_count">Warnings</option>
          <option value="review_status">Review status</option>
        </select>
      </div>
      <StateBlock loading={loading} error={error} empty={data?.items.length === 0} />
      {data && data.items.length > 0 && (
        <table className="wide-table">
          <thead>
            <tr>
              {SORT_COLUMNS.map((column) => (
                <SortableHeader
                  key={column.value}
                  column={column}
                  active={sort === column.value}
                  direction={direction}
                  onSort={updateSort}
                />
              ))}
              <th aria-label="Actions"></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((doc) => (
              <tr key={doc.filename}>
                <td>{doc.filename}</td>
                <td>{doc.rules_failed}</td>
                <td>{doc.pass_rate}%</td>
                <td>{money(doc.largest_absolute_difference)}</td>
                <td>{doc.warning_count}</td>
                <td>{doc.review_status}</td>
                <td>
                  <button className="icon-only" title="Open review" onClick={() => navigate(`/review/${encodeURIComponent(doc.filename)}?${params.toString()}`)}>
                    <ArrowRight size={17} aria-hidden />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function money(value: number | null) {
  return value == null ? 'n/a' : `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function SortableHeader({
  column,
  active,
  direction,
  onSort,
}: {
  column: SortColumn;
  active: boolean;
  direction: SortDirection;
  onSort: (value: string) => void;
}) {
  const Icon = active ? (direction === 'asc' ? ArrowUp : ArrowDown) : ChevronsUpDown;
  const nextDirection = active && direction === 'asc' ? 'descending' : 'ascending';
  return (
    <th aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        className={active ? 'sort-header active' : 'sort-header'}
        onClick={() => onSort(column.value)}
        aria-label={`Sort by ${column.label} ${nextDirection}`}
        title={`Sort by ${column.label}`}
      >
        <span>{column.label}</span>
        <Icon size={14} aria-hidden />
      </button>
    </th>
  );
}
