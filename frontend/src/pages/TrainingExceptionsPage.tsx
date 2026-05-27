import { Download, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { api } from '../api/client';
import type { TrainingExceptionQueueItem } from '../api/types';
import { StateBlock, useAsync } from './useAsync';

export function TrainingExceptionsPage() {
  const { data, error, loading } = useAsync(api.trainingExceptions, []);
  const [items, setItems] = useState<TrainingExceptionQueueItem[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const queue = items ?? data?.items ?? [];

  async function remove(filename: string) {
    await api.removeTrainingException(filename);
    setItems(queue.filter((item) => item.filename !== filename));
    setMessage('Removed');
  }

  async function exportQueue() {
    const result = await api.exportTrainingExceptions();
    const count = result.exported_count ?? queue.length;
    setMessage(`Exported ${count}`);
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Training Exceptions</h1>
          <p>Files marked for dataset handoff with copied paths and review metadata.</p>
        </div>
        <button className="primary-button" onClick={exportQueue} disabled={queue.length === 0}>
          <Download size={17} aria-hidden />
          Export queue
        </button>
      </header>
      {message && <p className="saved-label">{message}</p>}
      <StateBlock loading={loading} error={error} empty={queue.length === 0} />
      {queue.length > 0 && (
        <table className="wide-table">
          <thead>
            <tr><th>Filename</th><th>Rule</th><th>Copied path</th><th>Root cause</th><th>Status</th><th>Totals</th><th></th></tr>
          </thead>
          <tbody>
            {queue.map((item) => (
              <tr key={item.filename}>
                <td>{item.filename}</td>
                <td>{item.rule_name ?? 'n/a'}</td>
                <td>{item.exception_path}</td>
                <td>{item.root_cause ?? 'n/a'}</td>
                <td>{item.review_status ?? 'added_to_training'}</td>
                <td>{money(item.expected_total)} / {money(item.actual_total)}</td>
                <td>
                  <button className="inline-action danger" onClick={() => remove(item.filename)}>
                    <Trash2 size={16} aria-hidden />
                    Remove
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

function money(value: number | null | undefined) {
  return value == null ? 'n/a' : `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
