import { Sidebar } from './Sidebar';

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        {children}
      </main>
    </div>
  );
}
