import { Sidebar } from './Sidebar';
import { TopNav } from './TopNav';
import { useUIStore } from '../../store';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { isSidebarOpen } = useUIStore();

  return (
    <div className="min-h-screen bg-background flex text-on-surface font-sans">
      <Sidebar />
      <div
        className={`flex-1 flex flex-col min-h-screen transition-all duration-300 ${isSidebarOpen ? 'ml-60' : 'ml-0'}`}
      >
        <TopNav />
        <main className="flex-1 pt-14 p-5 max-w-[1400px] mx-auto w-full">{children}</main>
      </div>
    </div>
  );
}
