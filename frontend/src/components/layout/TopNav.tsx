import { Search, Bell, Menu } from 'lucide-react';
import { useUIStore } from '../../store';

export function TopNav() {
  const { isSidebarOpen, toggleSidebar } = useUIStore();

  return (
    <header
      className={`fixed top-0 right-0 h-14 bg-surface/80 backdrop-blur-md border-b border-outline-variant z-40 transition-all duration-300 flex items-center justify-between px-6 ${isSidebarOpen ? 'w-[calc(100%-15rem)]' : 'w-full'}`}
    >
      <div className="flex items-center gap-3">
        {!isSidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="text-on-surface-variant hover:text-primary transition-colors"
          >
            <Menu size={18} />
          </button>
        )}
      </div>

      <div className="flex items-center gap-4">
        <button className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-variant/30 rounded-md transition-colors">
          <Bell size={16} />
        </button>
        <div className="w-7 h-7 rounded-full bg-surface-variant border border-outline-variant/50 flex items-center justify-center">
          <span className="text-[10px] text-on-surface-variant font-medium">JD</span>
        </div>
      </div>
    </header>
  );
}
