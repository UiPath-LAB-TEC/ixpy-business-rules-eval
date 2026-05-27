export function SettingsPage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Runtime configuration is read from local environment variables.</p>
        </div>
      </header>
      <section className="panel">
        <table>
          <tbody>
            <tr><td>API base URL</td><td>{import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'}</td></tr>
            <tr><td>Database path</td><td>BUSINESS_RULE_DB</td></tr>
            <tr><td>Document root</td><td>BUSINESS_RULE_DOCUMENT_ROOT</td></tr>
          </tbody>
        </table>
      </section>
    </section>
  );
}

