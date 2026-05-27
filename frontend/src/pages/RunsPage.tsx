import { api } from '../api/client';
import { StateBlock, useAsync } from './useAsync';

export function RunsPage() {
  const runs = useAsync(api.runs, []);
  const logs = useAsync(api.logs, []);
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Runs / Logs</h1>
          <p>Evaluator history and structured diagnostics.</p>
        </div>
      </header>
      <StateBlock loading={runs.loading || logs.loading} error={runs.error ?? logs.error} />
      <div className="content-grid two">
        <section className="panel">
          <h2>Runs</h2>
          <table>
            <thead><tr><th>ID</th><th>Status</th><th>Docs</th><th>Results</th><th>Warnings</th></tr></thead>
            <tbody>
              {runs.data?.map((run) => (
                <tr key={run.run_id}><td>{run.run_id}</td><td>{run.status}</td><td>{run.document_count}</td><td>{run.result_count}</td><td>{run.warning_count}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel">
          <h2>Logs</h2>
          <div className="log-list">
            {logs.data?.items.map((log) => (
              <div className={log.level === 'warning' ? 'log-line warn' : 'log-line'} key={log.log_id}>
                <span>{log.level}</span><strong>{log.filename ?? 'run'}</strong><p>{log.message}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

