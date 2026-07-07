import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { BookOpen } from 'lucide-react';

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: ok ? 'var(--status-ok)' : 'var(--status-danger)',
      opacity: ok ? 1 : 0.4,
    }} />
  );
}

function riskBadge(level: string) {
  const l = (level || '').toLowerCase();
  if (l === 'critical') return 'badge-danger';
  if (l === 'high') return 'badge-warn';
  if (l === 'medium') return 'badge-info';
  return 'badge-neutral';
}

export function Coverage() {
  const { data: gapsData, isLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => getJson<any>('/knowledge/gaps'),
  });

  const gaps = gapsData?.gaps || [];
  const totalEquipment = gapsData?.total_equipment || 0;
  const covered = gaps.filter((g: any) => (g.coverage_score ?? 0) >= 50).length;
  const critical = gaps.filter((g: any) => g.risk_level === 'Critical').length;
  const avgCoverage = gaps.length > 0
    ? Math.round(gaps.reduce((s: number, g: any) => s + (g.coverage_score || 0), 0) / gaps.length)
    : 0;

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>Knowledge Coverage</h1>
          <p className="page-subtitle">Asset documentation and SOP coverage analysis</p>
        </div>
        <BookOpen size={20} style={{ color: 'var(--accent)', opacity: 0.6 }} />
      </div>

      {isLoading ? (
        <>
          <div className="stat-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            {[...Array(4)].map((_, i) => <div key={i} className="skeleton" style={{ height: 72 }} />)}
          </div>
          <div className="skeleton" style={{ height: 400 }} />
        </>
      ) : totalEquipment === 0 ? (
        <div className="card">
          <div className="empty-state">
            <BookOpen size={28} style={{ opacity: 0.3 }} />
            <span>No assets found. Upload industrial documents to extract assets and compute coverage scores.</span>
          </div>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="stat-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <div className="card"><div className="stat-block"><span className="stat-value">{totalEquipment}</span><span className="stat-label">Total Assets</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value" style={{ color: 'var(--status-ok)' }}>{covered}</span><span className="stat-label">Well Covered</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value" style={{ color: 'var(--status-danger)' }}>{critical}</span><span className="stat-label">Critical Risk</span></div></div>
            <div className="card"><div className="stat-block"><span className="stat-value">{avgCoverage}%</span><span className="stat-label">Avg Coverage</span></div></div>
          </div>

          {/* Coverage Table */}
          <div className="card">
            <div className="card-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 'var(--space-2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                <h3>Asset Coverage Matrix</h3>
                <span className="page-header-meta">{gaps.length} assets</span>
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', background: 'var(--bg-layer-2)', padding: 'var(--space-2)', borderRadius: 'var(--radius)', width: '100%' }}>
                <strong>Coverage Formula:</strong> SOP (25%) + Incident History (20%) + Maintenance (20%) + Compliance (20%) + Expert Owner (15%)
              </div>
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Risk Level</th>
                  <th>Risk Score</th>
                  <th>Coverage</th>
                  <th style={{ textAlign: 'center' }}>SOP</th>
                  <th style={{ textAlign: 'center' }}>Maintenance</th>
                  <th style={{ textAlign: 'center' }}>Incident</th>
                  <th style={{ textAlign: 'center' }}>Compliance</th>
                  <th style={{ textAlign: 'center' }}>Expert</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((gap: any, i: number) => {
                  const score = gap.coverage_score || 0;
                  const fillCls = score >= 80 ? 'ok' : score >= 50 ? '' : 'danger';
                  return (
                    <tr key={i}>
                      <td className="doc-name">{gap.asset || gap.equipment}</td>
                      <td><span className={`badge ${riskBadge(gap.risk_level)}`}>{gap.risk_level}</span></td>
                      <td className="text-mono text-tertiary">{(gap.risk_score || 0).toFixed(2)}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <div className="inline-bar" style={{ width: 64 }}>
                            <div className={`inline-bar-fill ${fillCls}`} style={{ width: `${score}%` }} />
                          </div>
                          <span className="text-mono text-tertiary" style={{ fontSize: 'var(--text-xs)' }}>{score}%</span>
                        </div>
                      </td>
                      <td style={{ textAlign: 'center' }}><StatusDot ok={gap.has_sop} /></td>
                      <td style={{ textAlign: 'center' }}><StatusDot ok={gap.has_maintenance} /></td>
                      <td style={{ textAlign: 'center' }}><StatusDot ok={gap.has_incident_history} /></td>
                      <td style={{ textAlign: 'center' }}><StatusDot ok={gap.has_compliance} /></td>
                      <td style={{ textAlign: 'center' }}><StatusDot ok={gap.has_expert} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
