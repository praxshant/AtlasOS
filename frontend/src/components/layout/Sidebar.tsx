import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Share2,
  BookOpen,
  Users,
  ShieldCheck,
  GitBranch,
  LogOut,
  FileText,
} from 'lucide-react';
import { useAuthStore } from '../../store';

const navGroups = [
  {
    label: 'OVERVIEW',
    links: [
      { href: '/', label: 'Dashboard', icon: LayoutDashboard },
      { href: '/documents', label: 'Document Registry', icon: FileText },
    ],
  },
  {
    label: 'INTELLIGENCE',
    links: [
      { href: '/copilot', label: 'AI Copilot', icon: MessageSquare },
      { href: '/graph', label: 'Knowledge Graph', icon: Share2 },
      { href: '/coverage', label: 'Knowledge Coverage', icon: BookOpen },
      { href: '/engineers', label: 'Engineer Intelligence', icon: Users },
    ],
  },
  {
    label: 'OPERATIONS',
    links: [
      { href: '/compliance', label: 'Compliance Audit', icon: ShieldCheck },
      { href: '/rca', label: 'Root Cause Analysis', icon: GitBranch },
    ],
  },
];

export function Sidebar() {
  const setToken = useAuthStore((state) => state.setToken);

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div>
          <span className="brand-atlas">ATLAS</span>
          <span className="brand-os">OS</span>
        </div>
        <p className="brand-tagline">INDUSTRIAL INTELLIGENCE</p>
      </div>

      <nav className="sidebar-nav">
        {navGroups.map((group) => (
          <div className="nav-group" key={group.label}>
            <p className="nav-group-label">{group.label}</p>
            {group.links.map((link) => {
              const Icon = link.icon;
              return (
                <NavLink
                  key={link.href}
                  to={link.href}
                  className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                >
                  <Icon size={15} />
                  {link.label}
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>

      <div style={{ padding: 'var(--space-4)', borderTop: '1px solid var(--border-default)' }}>
        <button
          onClick={() => setToken(null)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            width: '100%',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--status-danger)',
            fontSize: 'var(--text-sm)',
            fontWeight: 'var(--font-weight-medium)',
            padding: 'var(--space-2) var(--space-4)',
          }}
        >
          <LogOut size={15} />
          Logout
        </button>
      </div>
    </aside>
  );
}
