import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getJson } from '../api/client';
import { FileText, Activity, Database, Zap, AlertTriangle, BarChart2, Share2, Users } from 'lucide-react';

function StatCard({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="card">
      <div className="stat-block">
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  );
}

function StatRowSkeleton() {
  return (
    <div className="stat-row">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 72 }} />
      ))}
    </div>
  );
}

function TableSkeleton({ rows }: { rows: number }) {
  return (
    <div style={{ padding: 'var(--space-2)' }}>
      {[...Array(rows)].map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 36, marginBottom: 8 }} />
      ))}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <FileText size={28} style={{ opacity: 0.3 }} />
      <span>{message}</span>
    </div>
  );
}

function statusBadgeClass(status: string) {
  if (!status) return 'badge-neutral';
  const s = status.toLowerCase();
  if (s === 'completed' || s === 'ok') return 'badge-ok';
  if (s === 'failed' || s === 'error') return 'badge-danger';
  if (s === 'processing' || s === 'pending') return 'badge-warn';
  return 'badge-neutral';
}

function formatDate(ts: string) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ts; }
}

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: () => getJson<any>('/stats'),
  });

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => getJson<any>('/system/health'),
  });

  const { data: documentsRaw, isLoading: docsLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });

  const loading = statsLoading;
  const documents = Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || [];

  const systemStatus = (stats?.active_jobs ?? 0) > 0 ? 'PROCESSING' : 'OPERATIONAL';
  const statusClass = (stats?.active_jobs ?? 0) > 0 ? 'badge-warn' : 'badge-ok';

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Industrial Knowledge Platform</p>
        </div>
        <div>
          {!loading && <span className={`badge ${statusClass}`}>SYSTEM: {systemStatus}</span>}
        </div>
      </div>

      {/* Stat Row */}
      {loading ? (
        <StatRowSkeleton />
      ) : (
        <div className="stat-row">
          <StatCard value={stats?.total_documents ?? 0} label="Documents" />
          <StatCard value={stats?.total_chunks ?? 0} label="Vector Chunks" />
          <StatCard value={stats?.graph_nodes ?? 0} label="Graph Nodes" />
          <StatCard value={stats?.graph_edges ?? 0} label="Relationships" />
        </div>
      )}

      {/* Second KPI Row */}
      {!loading && (
        <div className="stat-row" style={{ marginTop: 0 }}>
          <StatCard value={`${stats?.knowledge_coverage_avg ?? 0}%`} label="Avg Coverage" />
          <StatCard value={stats?.total_assets ?? 0} label="Assets Tracked" />
          <StatCard value={stats?.critical_gaps ?? 0} label="Critical Gaps" />
          <StatCard value={stats?.engineers_at_risk ?? 0} label="Engineers at Risk" />
        </div>
      )}

      {/* Main Grid */}
      <div className="dashboard-grid">
        {/* Document Registry */}
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3>Document Registry</h3>
              <span className="page-header-meta">{documents.length} documents</span>
            </div>
            <Link to="/documents" className="btn btn-secondary" style={{ fontSize: 'var(--text-xs)', padding: 'var(--space-1) var(--space-3)' }}>
              Manage
            </Link>
          </div>
          {docsLoading ? (
            <TableSkeleton rows={5} />
          ) : documents.length === 0 ? (
            <EmptyState message="No documents ingested yet. Upload a document to begin." />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {documents.slice(0, 10).map((doc: any) => (
                  <tr key={doc.id}>
                    <td className="doc-name">{doc.filename || doc.name}</td>
                    <td><span className="badge badge-neutral">{doc.file_type || doc.type || 'DOC'}</span></td>
                    <td><span className={`badge ${statusBadgeClass(doc.status)}`}>{doc.status}</span></td>
                    <td className="text-mono text-tertiary">{formatDate(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Right Column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          {/* System Health */}
          <div className="card">
            <div className="card-header">
              <h3>System Health</h3>
            </div>
            {health ? (
              <table className="data-table">
                <tbody>
                  {[
                    { name: 'PostgreSQL', data: health.postgresql },
                    { name: 'Neo4j', data: health.neo4j },
                    { name: 'Qdrant', data: health.qdrant },
                    { name: 'Redis', data: health.redis },
                  ].map(({ name, data }) => (
                    <tr key={name}>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <span style={{
                            display: 'inline-block',
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: data?.status === 'ok' ? 'var(--status-ok)' : 'var(--status-danger)',
                            flexShrink: 0,
                          }} />
                          {name}
                        </div>
                      </td>
                      <td className="text-mono text-tertiary">
                        <span className={`badge ${data?.status === 'ok' ? 'badge-ok' : 'badge-danger'}`}>
                          {data?.status ?? 'N/A'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <TableSkeleton rows={4} />
            )}
          </div>

          {/* Quick Links */}
          <div className="card">
            <div className="card-header">
              <h3>Quick Access</h3>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {[
                { icon: Share2, label: 'Knowledge Graph', href: '/graph' },
                { icon: BarChart2, label: 'Compliance Audit', href: '/compliance' },
                { icon: Database, label: 'Knowledge Coverage', href: '/coverage' },
                { icon: Users, label: 'Engineer Intelligence', href: '/engineers' },
              ].map(({ icon: Icon, label, href }) => (
                <a
                  key={href}
                  href={href}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-3)',
                    padding: 'var(--space-2) var(--space-3)',
                    borderRadius: 5,
                    color: 'var(--text-secondary)',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 500,
                    textDecoration: 'none',
                    transition: 'color 0.12s, background 0.12s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = 'var(--text-primary)'; (e.currentTarget as HTMLElement).style.background = 'var(--bg-subtle)'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)'; (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                >
                  <Icon size={14} style={{ color: 'var(--accent)' }} />
                  {label}
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
