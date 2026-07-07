import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJson, authenticatedFetch } from '../api/client';
import { ShieldCheck, Play, Loader2, AlertTriangle, CheckCircle } from 'lucide-react';

function severityBadge(severity: string) {
  const s = (severity || '').toLowerCase();
  if (s === 'critical' || s === 'high') return 'badge-danger';
  if (s === 'medium') return 'badge-warn';
  return 'badge-neutral';
}

export function Compliance() {
  const { data: documentsRaw, isLoading: docsLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });

  const documents = (Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || []).filter(
    (d: any) => d.status === 'completed'
  );

  const [results, setResults] = useState<any[]>([]);
  const [running, setRunning] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAudit = async (docId: number) => {
    setRunning(docId);
    setError(null);
    try {
      const res = await authenticatedFetch('/compliance/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: docId }),
      });
      const data = await res.json();
      setResults((prev) => [...prev.filter((r) => r.document_id !== docId), { document_id: docId, ...data }]);
    } catch {
      setError('Audit failed. Please try again.');
    }
    setRunning(null);
  };

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>Compliance Audit</h1>
          <p className="page-subtitle">Evaluate documents against safety regulations</p>
        </div>
        <ShieldCheck size={20} style={{ color: 'var(--accent)', opacity: 0.6 }} />
      </div>

      {error && (
        <div className="error-banner" style={{
          background: 'var(--status-danger-dim)',
          border: '1px solid var(--status-danger)',
          borderRadius: 5,
          padding: 'var(--space-3) var(--space-4)',
          color: 'var(--status-danger)',
          fontSize: 'var(--text-sm)',
          marginBottom: 'var(--space-4)',
        }}>{error}</div>
      )}

      {/* Document Selector */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="card-header">
          <h3>Select Document to Audit</h3>
          <span className="page-header-meta">{documents.length} processed documents</span>
        </div>
        {docsLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[...Array(3)].map((_, i) => <div key={i} className="skeleton" style={{ height: 36 }} />)}
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <ShieldCheck size={28} style={{ opacity: 0.3 }} />
            <span>No processed documents available. Upload and process documents first.</span>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th style={{ width: 120 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc: any) => (
                <tr key={doc.id}>
                  <td className="doc-name">{doc.filename}</td>
                  <td><span className="badge badge-neutral">{doc.file_type || 'DOC'}</span></td>
                  <td>
                    <button
                      onClick={() => runAudit(doc.id)}
                      disabled={running === doc.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 'var(--space-1)',
                        background: 'none',
                        border: 'none',
                        cursor: running === doc.id ? 'not-allowed' : 'pointer',
                        color: 'var(--accent)',
                        fontSize: 'var(--text-sm)',
                        fontWeight: 500,
                        opacity: running === doc.id ? 0.5 : 1,
                        padding: 0,
                      }}
                    >
                      {running === doc.id ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={12} />}
                      {running === doc.id ? 'Running...' : 'Run Audit'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Results */}
      {results.map((r) => {
        const docName = documents.find((d: any) => d.id === r.document_id)?.filename || `Document ${r.document_id}`;
        const gapCount = r.gaps?.length ?? 0;
        const hasCritical = r.gaps?.some((g: any) => g.risk_level === 'Critical' || g.risk_level === 'High');
        const statusLabel = gapCount === 0 ? 'PASS' : hasCritical ? 'FAIL' : 'PARTIAL';
        const statusCls = gapCount === 0 ? 'badge-ok' : hasCritical ? 'badge-danger' : 'badge-warn';

        return (
          <div key={r.document_id} className="card" style={{ marginBottom: 'var(--space-6)' }}>
            <div className="card-header">
              <h3>Audit Report — {docName}</h3>
              <span className={`badge ${statusCls}`}>{statusLabel}</span>
            </div>

            {/* Score Row */}
            <div className="stat-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 'var(--space-6)' }}>
              <div className="card" style={{ background: 'var(--bg-subtle)' }}>
                <div className="stat-block">
                  <span className="stat-value" style={{ color: 'var(--accent)' }}>{r.compliance_score ?? 100}%</span>
                  <span className="stat-label">Compliance Score</span>
                </div>
              </div>
              <div className="card" style={{ background: 'var(--bg-subtle)' }}>
                <div className="stat-block">
                  <span className="stat-value" style={{ color: 'var(--status-ok)' }}>{r.compliant_count ?? 0}</span>
                  <span className="stat-label">Requirements Met</span>
                </div>
              </div>
              <div className="card" style={{ background: 'var(--bg-subtle)' }}>
                <div className="stat-block">
                  <span className="stat-value" style={{ color: gapCount > 0 ? 'var(--status-danger)' : 'var(--status-ok)' }}>{gapCount}</span>
                  <span className="stat-label">Gaps Found</span>
                </div>
              </div>
            </div>

            {/* Gap Table */}
            {gapCount === 0 ? (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                padding: 'var(--space-4)', background: 'var(--status-ok-dim)',
                border: '1px solid var(--status-ok)', borderRadius: 5,
                color: 'var(--status-ok)', fontSize: 'var(--text-sm)',
              }}>
                <CheckCircle size={16} />
                <span>All requirements satisfied. No compliance gaps detected.</span>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Regulation</th>
                    <th>Requirement</th>
                    <th>Finding</th>
                    <th>Risk</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {r.gaps.map((gap: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                        {gap.regulation}
                      </td>
                      <td style={{ color: 'var(--text-primary)', fontSize: 'var(--text-sm)', maxWidth: 200 }}>{gap.requirement}</td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', maxWidth: 220 }}>{gap.finding}</td>
                      <td><span className={`badge ${severityBadge(gap.risk_level)}`}>{gap.risk_level}</span></td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', maxWidth: 240 }}>{gap.recommendation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn-secondary"
                onClick={() => {
                  const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url; a.download = `audit-${r.document_id}.json`; a.click();
                }}
              >
                Export Report
              </button>
            </div>
          </div>
        );
      })}

      {/* Empty results state */}
      {results.length === 0 && !docsLoading && documents.length > 0 && (
        <div className="card">
          <div className="empty-state">
            <AlertTriangle size={28} style={{ opacity: 0.3 }} />
            <span>Select a document above and click "Run Audit" to evaluate compliance.</span>
          </div>
        </div>
      )}
    </div>
  );
}
