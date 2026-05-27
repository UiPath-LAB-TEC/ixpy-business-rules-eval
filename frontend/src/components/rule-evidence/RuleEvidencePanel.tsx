import { Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { api } from '../../api/client';
import type { EvidenceAnnotation, EvidenceDetail, Explanation, RecomputeResult, ReviewPayload, RuleDiagnosisEvidence, RuleResult } from '../../api/types';

export function RuleEvidencePanel({
  filename,
  rules,
  selectedRule,
  explanation,
  onSelectRule,
  onSelectEvidence,
}: {
  filename: string;
  rules: RuleResult[];
  selectedRule: string | null;
  explanation: Explanation | null;
  onSelectRule: (ruleName: string) => void;
  onSelectEvidence: (detail: EvidenceDetail) => void;
}) {
  const [review, setReview] = useState<ReviewPayload>({ status: 'unreviewed', root_cause: null, notes: '' });
  const [saved, setSaved] = useState(false);
  const [annotations, setAnnotations] = useState<Record<number, EvidenceAnnotation>>({});
  const [recompute, setRecompute] = useState<RecomputeResult | null>(null);
  const [annotationMessage, setAnnotationMessage] = useState<string | null>(null);
  const annotationPayload = useMemo(() => Object.values(annotations), [annotations]);

  useEffect(() => {
    if (explanation?.result) {
      setReview({
        status: explanation.result.review_status ?? 'unreviewed',
        root_cause: explanation.result.review_root_cause ?? explanation.result.root_cause,
        notes: explanation.result.review_notes ?? '',
      });
    }
    setSaved(false);
    setRecompute(null);
    setAnnotationMessage(null);
  }, [
    filename,
    selectedRule,
    explanation?.result?.filename,
    explanation?.result?.rule_name,
    explanation?.result?.review_status,
    explanation?.result?.review_root_cause,
    explanation?.result?.root_cause,
    explanation?.result?.review_notes,
  ]);

  useEffect(() => {
    const next: Record<number, EvidenceAnnotation> = {};
    for (const row of explanation?.details ?? []) {
      if (row.detail_type === 'computed_value') continue;
      next[row.detail_id] = {
        detail_id: row.detail_id,
        corrected_amount: row.amount,
        include_row: row.detail_type !== 'excluded_row',
        root_cause: null,
        notes: '',
      };
    }
    setAnnotations(next);
  }, [filename, selectedRule, explanation?.details]);

  async function save() {
    if (!selectedRule) return;
    const next = await api.saveReview(filename, selectedRule, review);
    setReview(next);
    setSaved(true);
  }

  async function saveAnnotations() {
    if (!selectedRule) return;
    await api.saveAnnotations(filename, selectedRule, annotationPayload);
    const result = await api.recomputeAnnotations(filename, selectedRule, annotationPayload);
    setRecompute(result);
    setAnnotationMessage('Annotations saved');
  }

  useEffect(() => {
    if (!selectedRule || annotationPayload.length === 0) {
      setRecompute(null);
      return;
    }
    let active = true;
    api.recomputeAnnotations(filename, selectedRule, annotationPayload)
      .then((result) => {
        if (active) setRecompute(result);
      })
      .catch(() => {
        if (active) setRecompute(null);
      });
    return () => {
      active = false;
    };
  }, [annotationPayload, filename, selectedRule]);

  function updateAnnotation(detailId: number, patch: Partial<EvidenceAnnotation>) {
    setAnnotations((current) => ({
      ...current,
      [detailId]: { ...current[detailId], detail_id: detailId, notes: '', corrected_amount: null, include_row: true, root_cause: null, ...patch },
    }));
  }

  function selectRuleWithKeyboard(event: KeyboardEvent<HTMLDivElement>, ruleName: string) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelectRule(ruleName);
  }

  const computed = explanation?.details.filter((row) => row.detail_type === 'computed_value') ?? [];
  const regularFields = explanation?.details.filter((row) => (
    row.detail_type === 'expected_source' || (row.detail_type === 'actual_source' && !isTableEvidence(row))
  )) ?? [];
  const tableRows = explanation?.details.filter((row) => row.detail_type === 'included_row' || (row.detail_type === 'actual_source' && isTableEvidence(row))) ?? [];
  const excludedRows = explanation?.details.filter((row) => row.detail_type === 'excluded_row') ?? [];
  const tableSum = tableRows.reduce((total, row) => total + (row.amount ?? 0), 0);

  return (
    <section className="rule-panel" aria-label="Business rule evidence">
      <div className="rule-list">
        {rules.map((rule) => (
          <div
            role="button"
            tabIndex={0}
            key={rule.rule_name}
            className={selectedRule === rule.rule_name ? 'rule-choice active' : 'rule-choice'}
            onClick={() => onSelectRule(rule.rule_name)}
            onKeyDown={(event) => selectRuleWithKeyboard(event, rule.rule_name)}
          >
            <span className="rule-choice-name">{rule.rule_name}</span>
            <strong>{truthy(rule.rule_passed) ? 'PASS' : 'FAIL'}</strong>
          </div>
        ))}
      </div>
      {explanation && (
        <div className="rule-detail">
          <h2>{explanation.result.label ?? explanation.result.rule_name}</h2>
          <p>{explanation.result.formula}</p>
          <DiagnosisPanel diagnosis={explanation.diagnosis} evidence={explanation.diagnosis_evidence} />
          <h3>Computed sums</h3>
          <div className="math-grid">
            {computed.map((row) => (
              <div key={row.detail_id}>
                <span>{row.evidence_role}</span>
                <strong>{row.amount == null ? row.normalized_value : money(row.amount)}</strong>
              </div>
            ))}
          </div>
          <div className="cause-line">
            <span>Status: {truthy(explanation.result.rule_passed) ? 'passed' : 'failed'}</span>
            <span>Likely root cause: {review.root_cause ?? explanation.result.root_cause}</span>
          </div>
          {explanation.suggested_root_causes && explanation.suggested_root_causes.length > 0 && (
            <div className="suggested-causes">
              {explanation.suggested_root_causes.map((cause) => <button key={cause} onClick={() => setReview({ ...review, root_cause: cause })}>{cause}</button>)}
            </div>
          )}
          <EvidenceSection title="Regular field extractions" rows={regularFields} onSelectEvidence={onSelectEvidence} showRow={false} />
          <EvidenceSection
            title="Table data extractions"
            rows={tableRows}
            onSelectEvidence={onSelectEvidence}
            summaryLabel="Included table sum"
            summaryValue={money(tableSum)}
          />
          <EvidenceSection title="Excluded table rows" rows={excludedRows} onSelectEvidence={onSelectEvidence} />
          <AnnotationSection
            rows={[...regularFields, ...tableRows, ...excludedRows]}
            annotations={annotations}
            recompute={recompute}
            onUpdate={updateAnnotation}
            onSave={saveAnnotations}
            message={annotationMessage}
          />
          <h3>Warnings</h3>
          <div className="warning-list">
            {explanation.logs.filter((log) => log.level === 'warning').map((log) => (
              <span key={log.log_id}>{log.message}</span>
            ))}
            {explanation.logs.filter((log) => log.level === 'warning').length === 0 && <span>No structured warnings for this document.</span>}
          </div>
          <div className="review-box">
            <select aria-label="Review status" value={review.status} onChange={(event) => setReview({ ...review, status: event.target.value })}>
              <option value="unreviewed">Unreviewed</option>
              <option value="in_review">In review</option>
              <option value="reviewed">Reviewed</option>
              <option value="ignored">Ignored</option>
              <option value="needs_extraction_fix">Needs extraction fix</option>
              <option value="added_to_training">Added to training</option>
              <option value="archived">Archived</option>
            </select>
            <select aria-label="Root cause" value={review.root_cause ?? ''} onChange={(event) => setReview({ ...review, root_cause: event.target.value || null })}>
              <option value="">Auto</option>
              <option value="missing field">Missing field</option>
              <option value="parse failure">Parse failure</option>
              <option value="extraction mismatch">Extraction mismatch</option>
              <option value="OCR issue">OCR issue</option>
              <option value="row inclusion error">Row inclusion error</option>
              <option value="duplicate/rollup issue">Duplicate/rollup issue</option>
              <option value="rule logic issue">Rule logic issue</option>
              <option value="document inconsistency">Document inconsistency</option>
              <option value="unknown">Unknown</option>
            </select>
            <textarea aria-label="Review notes" value={review.notes} onChange={(event) => setReview({ ...review, notes: event.target.value })} />
            <button className="primary-button" onClick={save}><Save size={17} aria-hidden />Save Review</button>
            {saved && <span className="saved-label">Saved</span>}
          </div>
        </div>
      )}
    </section>
  );
}

function DiagnosisPanel({
  diagnosis,
  evidence,
}: {
  diagnosis: Explanation['diagnosis'];
  evidence: RuleDiagnosisEvidence | null | undefined;
}) {
  const hasDiagnosis = Boolean(diagnosis && Object.values(diagnosis).some((value) => value != null && String(value).trim() !== ''));
  const scalarEvidence = orderedEvidenceEntries(evidence).filter(([key, value]) => key !== 'absolute_difference' && isScalarEvidence(value));
  const matchedRows = evidenceRecordArray(evidence?.matched_rows);
  const summaryFields = evidenceRecordArray(evidence?.summary_fields);
  const handledKeys = new Set(['matched_rows', 'summary_fields']);
  const dynamicTables = orderedEvidenceEntries(evidence)
    .filter(([key, value]) => !handledKeys.has(key) && Array.isArray(value))
    .map(([key, value]) => ({ key, rows: evidenceRecordArray(value) }))
    .filter((entry) => entry.rows.length > 0);
  const nestedEvidence = orderedEvidenceEntries(evidence)
    .filter(([key, value]) => !handledKeys.has(key) && isRecord(value));
  const hasEvidence = scalarEvidence.length > 0 || matchedRows.length > 0 || summaryFields.length > 0 || dynamicTables.length > 0 || nestedEvidence.length > 0;

  if (!hasDiagnosis && !hasEvidence) return null;

  return (
    <section className="diagnosis-panel" aria-label="Failure diagnosis">
      <div className="diagnosis-header">
        <h3>{diagnosis?.title || 'Failure diagnosis'}</h3>
        {diagnosis?.confidence && <span className={`diagnosis-confidence ${String(diagnosis.confidence).toLowerCase()}`}>{String(diagnosis.confidence).toLowerCase()} confidence</span>}
      </div>
      {diagnosis?.message && <p className="diagnosis-message">{diagnosis.message}</p>}
      {diagnosis?.recommended_action && (
        <p className="diagnosis-action">
          <strong>Recommended action</strong>
          <span>{diagnosis.recommended_action}</span>
        </p>
      )}
      {(diagnosis?.reason_code || diagnosis?.reason_group) && (
        <div className="diagnosis-chips">
          {diagnosis.reason_code && <code>{diagnosis.reason_code}</code>}
          {diagnosis.reason_group && <code>{diagnosis.reason_group}</code>}
        </div>
      )}
      {scalarEvidence.length > 0 && (
        <dl className="diagnosis-grid">
          {scalarEvidence.map(([key, value]) => (
            <div key={key}>
              <dt>{labelFromKey(key)}</dt>
              <dd>{formatDiagnosisValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      <DiagnosisEvidenceTable
        title="Matched rows"
        rows={matchedRows}
        preferredColumns={['row_index', 'description', 'amount', 'amount_field', 'field_id', 'why_relevant']}
      />
      <DiagnosisEvidenceTable
        title="Summary fields"
        rows={summaryFields}
        preferredColumns={['field', 'amount']}
      />
      {dynamicTables.map((entry) => (
        <DiagnosisEvidenceTable key={entry.key} title={labelFromKey(entry.key)} rows={entry.rows} />
      ))}
      {nestedEvidence.length > 0 && (
        <div className="diagnosis-nested">
          {nestedEvidence.map(([key, value]) => (
            <div key={key}>
              <h4>{labelFromKey(key)}</h4>
              <dl>
                {isRecord(value) && orderedEvidenceEntries(value).map(([nestedKey, nestedValue]) => (
                  <div key={nestedKey}>
                    <dt>{labelFromKey(nestedKey)}</dt>
                    <dd>{formatDiagnosisValue(nestedValue)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DiagnosisEvidenceTable({
  title,
  rows,
  preferredColumns = [],
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  preferredColumns?: string[];
}) {
  if (rows.length === 0) return null;
  const discoveredColumns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const columns = [
    ...preferredColumns.filter((column) => discoveredColumns.includes(column)),
    ...discoveredColumns.filter((column) => !preferredColumns.includes(column)).sort(),
  ];

  return (
    <section className="diagnosis-evidence-section" aria-label={title}>
      <h4>{title}</h4>
      <table className="diagnosis-evidence-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{labelFromKey(column)}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => <td key={column}>{formatDiagnosisValue(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function EvidenceSection({
  title,
  rows,
  onSelectEvidence,
  summaryLabel,
  summaryValue,
  showRow = true,
}: {
  title: string;
  rows: EvidenceDetail[];
  onSelectEvidence: (detail: EvidenceDetail) => void;
  summaryLabel?: string;
  summaryValue?: string;
  showRow?: boolean;
}) {
  return (
    <section className="evidence-section" aria-label={title}>
      <div className="evidence-section-header">
        <h3>{title}</h3>
        {summaryLabel && <span>{summaryLabel}: <strong>{summaryValue}</strong></span>}
      </div>
      {rows.length === 0 ? (
        <div className="empty-evidence-row">No rows for this rule side.</div>
      ) : (
        <table className="evidence-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Field</th>
              {showRow && <th>Row</th>}
              <th>Amount</th>
              <th>Normalized</th>
              <th>Raw</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.detail_id} onClick={() => onSelectEvidence(row)} tabIndex={0}>
                <td>{row.evidence_role}</td>
                <td>{displayFieldName(row)}</td>
                {showRow && <td>{row.row_index ?? 'n/a'}:{row.column_index ?? 'n/a'}</td>}
                <td>{row.amount == null ? 'n/a' : money(row.amount)}</td>
                <td>{row.normalized_value ?? 'n/a'}</td>
                <td>{row.raw_value ?? row.reason ?? 'n/a'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function AnnotationSection({
  rows,
  annotations,
  recompute,
  onUpdate,
  onSave,
  message,
}: {
  rows: EvidenceDetail[];
  annotations: Record<number, EvidenceAnnotation>;
  recompute: RecomputeResult | null;
  onUpdate: (detailId: number, patch: Partial<EvidenceAnnotation>) => void;
  onSave: () => void;
  message: string | null;
}) {
  if (rows.length === 0) return null;
  return (
    <section className="annotation-section">
      <div className="evidence-section-header">
        <h3>Evidence annotations</h3>
        <button className="primary-button" onClick={onSave}>Save annotations</button>
      </div>
      <table className="evidence-table annotation-table">
        <thead>
          <tr><th>Field</th><th>Raw</th><th>Corrected amount</th><th>Include</th><th>Root cause</th><th>Notes</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const annotation = annotations[row.detail_id];
            return (
              <tr key={row.detail_id}>
                <td>{displayFieldName(row)}</td>
                <td>{row.raw_value ?? row.reason ?? 'n/a'}</td>
                <td>
                  <input
                    aria-label="Corrected amount"
                    inputMode="decimal"
                    value={annotation?.corrected_amount ?? ''}
                    onChange={(event) => onUpdate(row.detail_id, { corrected_amount: event.target.value === '' ? null : Number(event.target.value) })}
                  />
                </td>
                <td>
                  <label className="checkbox-label">
                    <input
                      aria-label="Include row"
                      type="checkbox"
                      checked={annotation?.include_row ?? false}
                      onChange={(event) => onUpdate(row.detail_id, { include_row: event.target.checked })}
                    />
                  </label>
                </td>
                <td>
                  <input
                    aria-label="Annotation root cause"
                    value={annotation?.root_cause ?? ''}
                    onChange={(event) => onUpdate(row.detail_id, { root_cause: event.target.value || null })}
                  />
                </td>
                <td>
                  <input
                    aria-label="Annotation notes"
                    value={annotation?.notes ?? ''}
                    onChange={(event) => onUpdate(row.detail_id, { notes: event.target.value })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {message && <p className="saved-label">{message}</p>}
      {recompute?.original && recompute?.corrected && (
        <div className="recompute-grid">
          <ResultCard title="Original result" result={recompute.original} />
          <ResultCard title="Corrected result" result={recompute.corrected} />
        </div>
      )}
    </section>
  );
}

function ResultCard({
  title,
  result,
}: {
  title: string;
  result: RecomputeResult['original'];
}) {
  return (
    <div>
      <h3>{title}</h3>
      <dl>
        <dt>Expected</dt><dd>{moneyNullable(result.expected_total)}</dd>
        <dt>Actual</dt><dd>{moneyNullable(result.actual_total)}</dd>
        <dt>Difference</dt><dd>{moneyNullable(result.difference)}</dd>
        <dt>Status</dt><dd>{truthy(result.rule_passed) ? 'pass' : 'fail'}</dd>
      </dl>
    </div>
  );
}

function orderedEvidenceEntries(evidence: Record<string, unknown> | null | undefined) {
  if (!evidence) return [];
  const order = ['formula', 'expected_total', 'actual_total', 'difference', 'absolute_difference', 'matched_rows', 'summary_fields'];
  return Object.entries(evidence).sort(([left], [right]) => {
    const leftIndex = order.indexOf(left);
    const rightIndex = order.indexOf(right);
    if (leftIndex !== -1 || rightIndex !== -1) {
      return (leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex) - (rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex);
    }
    return left.localeCompare(right);
  });
}

function evidenceRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isScalarEvidence(value: unknown) {
  return value == null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
}

function labelFromKey(key: string) {
  return key
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDiagnosisValue(value: unknown): string {
  if (value == null || value === '') return 'n/a';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(formatDiagnosisValue).join(', ');
  return JSON.stringify(value);
}

function truthy(value: boolean | number) {
  return value === true || value === 1;
}

function isTableEvidence(row: EvidenceDetail) {
  return row.source_field_id === 'items' || row.source_field_id?.startsWith('Statement Table');
}

function displayFieldName(row: EvidenceDetail) {
  return friendlyFieldName(row.source_field || row.source_field_id);
}

function friendlyFieldName(value: string | null | undefined) {
  if (!value) return 'n/a';
  const leaf = value.includes('>') ? value.split('>').at(-1)?.trim() : value;
  const normalized = (leaf || value).replaceAll('-', ' ').replaceAll('_', ' ');
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function money(value: number) {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function moneyNullable(value: number | null) {
  return value == null ? 'n/a' : money(value);
}
