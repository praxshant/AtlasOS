import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Users } from 'lucide-react';

function riskBadge(level: string) {
  const l = (level || '').toLowerCase();
  if (l === 'critical') return 'badge-danger';
  if (l === 'high') return 'badge-warn';
  if (l === 'medium') return 'badge-info';
  return 'badge-neutral';
}

export function Engineers() {
  const { data, isLoading } = useQuery({
    queryKey: ['engineers'],
    queryFn: () => getJson<any>('/engineers'),
  });

  const engineers = data?.engineers || [];
  const summary = data?.summary || {};

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>Engineer Intelligence</h1>
          <p className="page-subtitle">Personnel expertise mapping and succession risk analysis</p>
        </div>
        <Users size={20} style={{ color: 'var(--accent)', opacity: 0.6 }} />
      </div>

      {isLoading ? (
        <>
          <div className="stat-row">
            {[...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ height: 72 }} />)}
          </div>
          <div className="skeleton" style={{ height: 400 }} />
        </>
      ) : engineers.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <Users size={28} style={{ opacity: 0.3 }} />
            <span>No engineers found. Engineer data is extracted from maintenance logs and inspection reports.</span>
          </div>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="stat-row">
            <div className="card"><div className="stat-block"><span className="stat-value">{summary.total_engineers || 0}</span><span className="stat-label">Mapped Engineers</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value" style={{ color: 'var(--status-danger)' }}>{summary.high_risk_count || 0}</span><span className="stat-label">High Risk</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value">{(summary.avg_expertise_score || 0).toFixed(1)}</span><span className="stat-label">Avg Expertise</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value" style={{ color: 'var(--status-warn)' }}>{summary.critical_assets_unprotected || 0}</span><span className="stat-label">Unprotected Assets</span></div></div>
          </div>

          {/* Engineer Table */}
          <div className="card">
            <div className="card-header">
              <h3>Personnel Registry</h3>
              <span className="page-header-meta">{engineers.length} engineers</span>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Expertise Score</th>
                  <th>Centrality</th>
                  <th>Succession Risk</th>
                  <th>Assets</th>
                </tr>
              </thead>
              <tbody>
                {engineers.map((eng: any, i: number) => (
                  <tr key={i}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                        <div style={{
                          width: 28, height: 28, borderRadius: '50%',
                          background: 'var(--bg-subtle)',
                          border: '1px solid var(--border-default)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 'var(--text-xs)', fontWeight: 700,
                          color: 'var(--text-secondary)', flexShrink: 0,
                          textTransform: 'uppercase',
                        }}>
                          {(eng.name || '??').substring(0, 2)}
                        </div>
                        {eng.name}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                        <div className="inline-bar" style={{ width: 56 }}>
                          <div
                            className={`inline-bar-fill ${(eng.expertise_score || 0) >= 7 ? 'ok' : (eng.expertise_score || 0) >= 4 ? '' : 'danger'}`}
                            style={{ width: `${((eng.expertise_score || 0) / 10) * 100}%` }}
                          />
                        </div>
                        <span className="text-mono text-tertiary" style={{ fontSize: 'var(--text-xs)' }}>
                          {(eng.expertise_score || 0).toFixed(1)}
                        </span>
                      </div>
                    </td>
                    <td className="text-mono text-tertiary">{(eng.centrality || 0).toFixed(3)}</td>
                    <td><span className={`badge ${riskBadge(eng.succession_risk)}`}>{eng.succession_risk || 'Low'}</span></td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(eng.assets || []).slice(0, 3).map((a: string, ai: number) => (
                          <span key={ai} className="badge badge-neutral" style={{ fontFamily: 'var(--font-mono)' }}>{a}</span>
                        ))}
                        {(eng.assets || []).length > 3 && (
                          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                            +{eng.assets.length - 3} more
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
