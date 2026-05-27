import { BarChart3, ClipboardList, FileSearch, Gauge, History, ListChecks, PanelLeftClose, PanelLeftOpen, Settings, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { DashboardPage } from './pages/DashboardPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { ReviewPage } from './pages/ReviewPage';
import { RulesPage } from './pages/RulesPage';
import { RunsPage } from './pages/RunsPage';
import { SettingsPage } from './pages/SettingsPage';
import { TrainingExceptionsPage } from './pages/TrainingExceptionsPage';

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: Gauge },
  { path: '/documents', label: 'Documents', icon: FileSearch },
  { path: '/training-exceptions', label: 'Training', icon: Upload },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/runs', label: 'Runs / Logs', icon: History },
  { path: '/rules', label: 'Rules', icon: ListChecks },
  { path: '/settings', label: 'Settings', icon: Settings },
];

export function App() {
  const [location, setLocation] = useState(() => ({
    pathname: window.location.pathname === '/' ? '/dashboard' : window.location.pathname,
    search: window.location.search,
  }));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const path = location.pathname;
  const reviewFilename = useMemo(() => (path.startsWith('/review/') ? decodeURIComponent(path.slice('/review/'.length)) : null), [path]);

  function navigate(nextPath: string) {
    window.history.pushState(null, '', nextPath);
    setLocation({ pathname: window.location.pathname, search: window.location.search });
  }

  window.onpopstate = () => setLocation({ pathname: window.location.pathname, search: window.location.search });

  return (
    <div className={sidebarCollapsed ? 'app-shell sidebar-collapsed' : 'app-shell'}>
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <ClipboardList size={22} aria-hidden />
          <span>business-rule-ui</span>
          <button
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="sidebar-toggle"
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={() => setSidebarCollapsed((current) => !current)}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={18} aria-hidden /> : <PanelLeftClose size={18} aria-hidden />}
          </button>
        </div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = path === item.path;
            return (
              <button
                aria-label={item.label}
                className={active ? 'nav-item active' : 'nav-item'}
                key={item.path}
                title={sidebarCollapsed ? item.label : undefined}
                onClick={() => navigate(item.path)}
              >
                <Icon size={17} aria-hidden />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <main className="main-panel">
        {path === '/dashboard' && <DashboardPage navigate={navigate} />}
        {path === '/documents' && <DocumentsPage navigate={navigate} />}
        {path === '/training-exceptions' && <TrainingExceptionsPage />}
        {reviewFilename && <ReviewPage filename={reviewFilename} listSearch={location.search} navigate={navigate} />}
        {path === '/analytics' && <AnalyticsPage navigate={navigate} />}
        {path === '/runs' && <RunsPage />}
        {path === '/rules' && <RulesPage />}
        {path === '/settings' && <SettingsPage />}
      </main>
    </div>
  );
}
