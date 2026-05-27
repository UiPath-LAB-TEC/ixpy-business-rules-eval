import { AlertTriangle, ArrowRight, Download } from 'lucide-react';
import { api } from '../api/client';
import { StateBlock, useAsync } from './useAsync';

export function DashboardPage({ navigate }: { navigate: (path: string) => void }) {
  const { data, error, loading } = useAsync(api.dashboard, []);

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Settlement-statement rule health, warnings, and failed documents.</p>
        </div>
        <a className="icon-button" href={api.failedRulesCsvUrl()} title="Export failed rules CSV">
          <Download size={18} aria-hidden />
          Export CSV
        </a>
      </header>
      <StateBlock loading={loading} error={error} />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Documents" value={data.total_documents} />
            <Metric label="Evaluated" value={data.evaluated_documents} />
            <Metric label="No Rule" value={data.no_rule_documents} />
            <Metric label="Evaluations" value={data.total_evaluations} />
            <Metric label="Passed" value={data.passed_evaluations} />
            <Metric label="Failed" value={data.failed_evaluations} tone="bad" />
            <Metric label="Pass Rate" value={`${data.pass_rate}%`} />
            <Metric label="Warnings" value={data.warning_count} tone="warn" />
            <Metric label="Unreviewed Failed" value={data.unreviewed_failed_documents ?? 0} tone="bad" />
            <Metric label="Reviewed" value={data.reviewed_documents ?? 0} />
            <Metric label="Added to Training" value={data.added_to_training_documents ?? 0} />
            <Metric label="Ignored" value={data.ignored_documents ?? 0} />
          </div>
          <div className="content-grid two">
            <section className="panel">
              <h2>Worst Rules</h2>
              <table>
                <thead>
                  <tr><th>Rule</th><th>Pass Rate</th><th>Failed</th></tr>
                </thead>
                <tbody>
                  {data.worst_rules.map((rule) => (
                    <tr key={rule.rule_name}>
                      <td>{rule.rule_name}</td>
                      <td>{rule.pass_rate_percentage}%</td>
                      <td>{rule.total_failed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="panel">
              <h2>Recent Failed Documents</h2>
              <div className="document-list">
                {data.recent_documents.map((doc) => (
                  <button className="document-row" key={doc.filename} onClick={() => navigate(`/review/${encodeURIComponent(doc.filename)}?status=failed&sort=highest_value&limit=10`)}>
                    <AlertTriangle size={16} aria-hidden />
                    <span>{doc.filename}</span>
                    <strong>{doc.rules_failed}</strong>
                    <ArrowRight size={16} aria-hidden />
                  </button>
                ))}
              </div>
            </section>
            <section className="panel">
              <h2>Top Recurring Root Causes</h2>
              <table>
                <thead>
                  <tr><th>Root cause</th><th>Count</th></tr>
                </thead>
                <tbody>
                  {(data.top_recurring_root_causes ?? []).map((cause) => (
                    <tr key={cause.root_cause}>
                      <td>{cause.root_cause}</td>
                      <td>{cause.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </>
      )}
    </section>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: 'bad' | 'warn' }) {
  return (
    <div className={`metric ${tone ?? ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
