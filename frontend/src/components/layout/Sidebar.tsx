import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  Network,
  Bot,
  ShieldCheck,
  GitBranch,
  TrendingDown,
  Users,
  ChevronDown,
  Upload,
  LogOut,
} from 'lucide-react';
import { useUIStore, useAuthStore } from '../../store';
import { cn } from '../ui/Card';

const navGroups = [
  {
    label: 'OVERVIEW',
    links: [
      { href: '/', label: 'Dashboard', icon: LayoutDashboard },
      { href: '/documents', label: 'Documents', icon: Upload },
    ],
  },
  {
    label: 'INTELLIGENCE',
    links: [
      { href: '/copilot', label: 'AI Copilot', icon: Bot },
      { href: '/graph', label: 'Knowledge Graph', icon: Network },
      { href: '/coverage', label: 'Coverage', icon: FileText },
      { href: '/engineers', label: 'Engineers', icon: Users },
    ],
  },
  {
    label: 'OPERATIONS',
    links: [
      { href: '/compliance', label: 'Compliance', icon: ShieldCheck },
      { href: '/rca', label: 'Root Cause Analysis', icon: GitBranch },
      { href: '/risk', label: 'Risk Analytics', icon: TrendingDown },
    ],
  },
];

export function Sidebar() {
  const { isSidebarOpen } = useUIStore();
  const location = useLocation();
  const setToken = useAuthStore((state) => state.setToken);

  if (!isSidebarOpen) return null;

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-surface-container-low border-r border-outline-variant flex flex-col z-50">
      <div className="p-4 flex flex-col h-full">
        {/* Logo */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-7 h-7 rounded-md bg-primary/20 flex items-center justify-center border border-primary/30">
            <span className="text-primary font-bold text-sm">A</span>
          </div>
          <div>
            <h1 className="font-semibold text-on-surface text-[15px] leading-tight tracking-tight">AtlasOS</h1>
          </div>
        </div>

        {/* Workspace */}
        <button className="flex items-center justify-between w-full px-2 py-1.5 mb-5 rounded-md hover:bg-surface-variant/30 transition-colors border border-outline-variant/50 text-xs">
          <span className="font-mono uppercase text-on-surface-variant tracking-wider">default</span>
          <ChevronDown size={12} className="text-on-surface-variant" />
        </button>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto space-y-5">
          {navGroups.map((group) => (
            <div key={group.label}>
              <p className="px-2 mb-1.5 text-[10px] font-mono text-on-surface-variant/60 tracking-widest">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.links.map((link) => {
                  const Icon = link.icon;
                  const isActive = link.href === '/' ? location.pathname === '/' : location.pathname.startsWith(link.href);
                  return (
                    <NavLink
                      key={link.href}
                      to={link.href}
                      className={cn(
                        'flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[13px] transition-colors',
                        isActive
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/20'
                      )}
                    >
                      <Icon size={15} strokeWidth={isActive ? 2.2 : 1.8} />
                      {link.label}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Logout */}
        <div className="pt-4 border-t border-outline-variant mt-auto">
          <button
            onClick={() => setToken(null)}
            className="flex items-center gap-2.5 w-full px-2 py-1.5 rounded-md text-[13px] text-red-400 hover:bg-red-500/10 transition-colors border-none bg-transparent cursor-pointer text-left"
          >
            <LogOut size={15} />
            Logout
          </button>
        </div>
      </div>
    </aside>
  );
}
