import type { CSSProperties } from 'react';
import type { Analytics } from '../api/types';
import { api } from '../api/client';
import { StateBlock, useAsync } from './useAsync';

export function AnalyticsPage({ navigate }: { navigate: (path: string) => void }) {
  const { data, error, loading } = useAsync(api.analytics, []);
  const summary = data ? analyticsSummary(data) : null;
  const maxRuleFailures = Math.max(1, ...(data?.rule_pass_rates ?? []).map((rule) => rule.total_failed));
  const maxDifference = Math.max(1, ...(data?.largest_differences ?? []).map((row) => row.absolute_difference ?? 0));
  const maxRootCause = Math.max(1, ...(data?.root_cause_counts ?? []).map((cause) => cause.count));
  const maxDiagnosis = Math.max(1, ...(data?.diagnosis_counts ?? []).map((diagnosis) => diagnosis.count));
  const maxReviewStatus = Math.max(1, ...(data?.review_status_counts ?? []).map((stage) => stage.count));

  return (
    <section className="page analytics-page">
      <header className="page-header">
        <div>
          <h1>Analytics</h1>
          <p>Rule health, failure patterns, review progress, document outliers, and extraction confidence.</p>
        </div>
      </header>
      <StateBlock loading={loading} error={error} />
      {data && summary && (
        <>
          <div className="metric-grid analytics-metrics">
            <Metric label="Evaluated Docs" value={summary.evaluated_documents.toLocaleString()} detail={`${summary.total_documents.toLocaleString()} total`} />
            <Metric label="Pass Rate" value={percent(summary.pass_rate)} detail={`${summary.passed_evaluations.toLocaleString()} / ${summary.total_evaluations.toLocaleString()} evals`} />
            <Metric label="Failed Evals" value={summary.failed_evaluations.toLocaleString()} detail={`${money(summary.average_failed_absolute_difference)} avg gap`} tone="bad" />
            <Metric label="Avg Field Confidence" value={confidenceValue(data.confidence.avg_confidence)} detail={`OCR ${confidenceValue(data.confidence.avg_ocr_confidence)}`} />
          </div>

          <div className="content-grid two">
            <section className="panel analytics-panel">
              <PanelHeader title="Pass Rate by Rule" detail={`${data.rule_pass_rates.length} rules`} />
              <div className="analytics-bar-list">
                {data.rule_pass_rates.map((rule) => (
                  <div className="analytics-rule-row" key={rule.rule_name}>
                    <div className="analytics-row-heading">
                      <span>{rule.rule_name}</span>
                      <strong>{percent(rule.pass_rate_percentage)}</strong>
                    </div>
                    <div className="stacked-bar" aria-label={`${rule.rule_name} pass rate`}>
                      <span className="stacked-bar-pass" style={barWidth(rule.pass_rate_percentage)} />
                    </div>
                    <div className="analytics-row-detail">
                      <span>{rule.total_failed.toLocaleString()} failed</span>
                      <span>{rule.total_evaluated.toLocaleString()} evaluated</span>
                      <span>{money(rule.avg_absolute_difference)} avg failed gap</span>
                    </div>
                  </div>
                ))}
                {data.rule_pass_rates.length === 0 && <EmptyAnalytics label="No rule evaluations found." />}
              </div>
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Failure Diagnosis" detail={`${data.diagnosis_counts?.length ?? 0} patterns`} />
              <div className="analytics-bar-list">
                {(data.diagnosis_counts ?? []).map((diagnosis) => (
                  <BarRow
                    key={diagnosis.reason_code}
                    label={diagnosis.title || diagnosis.reason_code}
                    value={diagnosis.count}
                    max={maxDiagnosis}
                    detail={`${diagnosis.reason_code} | ${diagnosis.confidence} confidence`}
                  />
                ))}
                {(data.diagnosis_counts ?? []).length === 0 && data.root_cause_counts.map((cause) => (
                  <BarRow key={cause.root_cause} label={cause.root_cause} value={cause.count} max={maxRootCause} />
                ))}
                {(data.diagnosis_counts ?? []).length === 0 && data.root_cause_counts.length === 0 && <EmptyAnalytics label="No failed-rule diagnoses found." />}
              </div>
            </section>

            <section className="panel analytics-panel analytics-panel-wide">
              <PanelHeader title="Largest Differences" detail="Click a row to review" />
              <table className="analytics-table">
                <thead><tr><th>Document</th><th>Rule</th><th>Gap</th></tr></thead>
                <tbody>
                  {data.largest_differences.map((row) => (
                    <tr key={`${row.filename}-${row.rule_name}`} onClick={() => navigate(`/review/${encodeURIComponent(row.filename)}?status=failed&sort=highest_value`)}>
                      <td>{row.filename}</td>
                      <td>{row.rule_name}</td>
                      <td>
                        <span className="inline-bar" style={barWidth(((row.absolute_difference ?? 0) / maxDifference) * 100)} />
                        <strong>{money(row.absolute_difference)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.largest_differences.length === 0 && <EmptyAnalytics label="No failed differences found." />}
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Failed Documents" detail={`${data.failed_documents.length} shown`} />
              <table className="analytics-table">
                <thead><tr><th>Document</th><th>Failed</th><th>Worst Gap</th><th>Review</th></tr></thead>
                <tbody>
                  {data.failed_documents.map((doc) => (
                    <tr key={doc.filename} onClick={() => navigate(`/review/${encodeURIComponent(doc.filename)}?status=failed&sort=highest_value`)}>
                      <td>{doc.filename}</td>
                      <td>{doc.rules_failed}</td>
                      <td>{money(doc.largest_absolute_difference)}</td>
                      <td>{friendlyStatus(doc.review_status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.failed_documents.length === 0 && <EmptyAnalytics label="No failed documents found." />}
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Review Stages" detail={`${(data.review_status_counts ?? []).reduce((sum, row) => sum + row.count, 0)} docs`} />
              <div className="analytics-bar-list">
                {(data.review_status_counts ?? []).map((stage) => (
                  <BarRow key={stage.status} label={friendlyStatus(stage.status)} value={stage.count} max={maxReviewStatus} />
                ))}
                {(data.review_status_counts ?? []).length === 0 && <EmptyAnalytics label="No review-stage data found." />}
              </div>
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Root Causes" detail={`${data.root_cause_counts.length} causes`} />
              <div className="analytics-bar-list">
                {data.root_cause_counts.map((cause) => (
                  <BarRow key={cause.root_cause} label={cause.root_cause} value={cause.count} max={maxRootCause} />
                ))}
                {data.root_cause_counts.length === 0 && <EmptyAnalytics label="No root cause data found." />}
              </div>
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Extraction Confidence" detail={`${data.field_confidence?.length ?? 0} fields`} />
              <table className="analytics-table">
                <thead><tr><th>Field</th><th>Rows</th><th>Field Conf.</th><th>OCR Conf.</th><th>Missing</th></tr></thead>
                <tbody>
                  {(data.field_confidence ?? []).map((field) => (
                    <tr key={`${field.field_id}-${field.field}`}>
                      <td>{friendlyField(field.field || field.field_id)}</td>
                      <td>{field.extraction_count.toLocaleString()}</td>
                      <td>{confidenceValue(field.avg_confidence)}</td>
                      <td>{confidenceValue(field.avg_ocr_confidence)}</td>
                      <td>{field.missing_count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(data.field_confidence ?? []).length === 0 && <EmptyAnalytics label="No extraction confidence data found." />}
            </section>

            <section className="panel analytics-panel">
              <PanelHeader title="Warnings and No-Rule Docs" detail={`${data.warning_frequency.length} warning groups`} />
              <div className="analytics-split-list">
                <div>
                  <h3>Warnings</h3>
                  {data.warning_frequency.map((warning) => (
                    <div className="stat-row" key={`${warning.event_type}-${warning.raw_value}`}>
                      <span>{warning.event_type}: {warning.raw_value ?? 'n/a'}</span>
                      <strong>{warning.count}</strong>
                    </div>
                  ))}
                  {data.warning_frequency.length === 0 && <EmptyAnalytics label="No warnings found." />}
                </div>
                <div>
                  <h3>No-Rule Documents</h3>
                  {data.no_rule_documents.slice(0, 8).map((doc) => (
                    <div className="stat-row" key={doc.filename}><span>{doc.filename}</span></div>
                  ))}
                  {data.no_rule_documents.length === 0 && <EmptyAnalytics label="Every extracted document has rule evaluations." />}
                </div>
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}

function PanelHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="analytics-panel-header">
      <h2>{title}</h2>
      <span>{detail}</span>
    </div>
  );
}

function Metric({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: 'bad' | 'warn' }) {
  return (
    <div className={tone ? `metric ${tone}` : 'metric'}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function BarRow({ label, value, max, detail }: { label: string; value: number; max: number; detail?: string }) {
  return (
    <div className="analytics-bar-row">
      <div className="analytics-row-heading">
        <span>{label}</span>
        <strong>{value.toLocaleString()}</strong>
      </div>
      <div className="analytics-bar" aria-hidden>
        <span style={barWidth((value / max) * 100)} />
      </div>
      {detail && <div className="analytics-row-detail"><span>{detail}</span></div>}
    </div>
  );
}

function EmptyAnalytics({ label }: { label: string }) {
  return <div className="empty-evidence-row">{label}</div>;
}

function analyticsSummary(data: Analytics) {
  if (data.summary) return data.summary;
  const totalEvaluations = data.rule_pass_rates.reduce((sum, rule) => sum + rule.total_evaluated, 0);
  const failedEvaluations = data.rule_pass_rates.reduce((sum, rule) => sum + rule.total_failed, 0);
  const passedEvaluations = data.rule_pass_rates.reduce((sum, rule) => sum + rule.total_passed, 0);
  return {
    total_documents: data.failed_documents.length + data.no_rule_documents.length,
    evaluated_documents: data.failed_documents.length,
    no_rule_documents: data.no_rule_documents.length,
    total_evaluations: totalEvaluations,
    passed_evaluations: passedEvaluations,
    failed_evaluations: failedEvaluations,
    pass_rate: totalEvaluations ? (passedEvaluations * 100) / totalEvaluations : 0,
    average_failed_absolute_difference: average(data.rule_pass_rates.map((rule) => rule.avg_absolute_difference ?? 0)),
  };
}

function average(values: number[]) {
  const usable = values.filter((value) => Number.isFinite(value));
  return usable.length ? usable.reduce((sum, value) => sum + value, 0) / usable.length : 0;
}

function barWidth(percentValue: number): CSSProperties {
  const width = Math.max(0, Math.min(100, percentValue));
  return { '--bar-width': `${width}%` } as CSSProperties;
}

function percent(value: number | null | undefined) {
  return value == null ? 'n/a' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function confidenceValue(value: unknown) {
  if (typeof value !== 'number') return 'n/a';
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function money(value: number | null | undefined) {
  return value == null ? 'n/a' : `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function friendlyStatus(status: string | null | undefined) {
  return friendlyField(status ?? 'unreviewed');
}

function friendlyField(value: string | null | undefined) {
  if (!value) return 'n/a';
  const leaf = value.includes('>') ? value.split('>').at(-1)?.trim() : value;
  return (leaf || value)
    .replaceAll('-', ' ')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
