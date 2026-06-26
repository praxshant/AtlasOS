'use client';

import React, { useState, useEffect } from 'react';
import { authenticatedFetch } from '../../utils/api';

interface GapItem {
  regulation: string;
  requirement: string;
  finding: string;
  risk_level: 'Low' | 'Medium' | 'High';
  recommendation: string;
}

interface ComplianceReport {
  gaps: GapItem[];
  overall_risk: 'Low' | 'Medium' | 'High';
  cited_docs?: string[];
}

interface DocumentItem {
  id: number;
  filename: string;
  status: string;
}

export default function CompliancePage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<number | ''>('');
  const [scopeFilter, setScopeFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    // Fetch completed documents to analyze
    const fetchDocs = async () => {
      try {
        const response = await authenticatedFetch('/api/documents');
        if (response.ok) {
          const data = await response.json();
          // Filter to completed ones
          const completed = data.filter((d: any) => d.status === 'completed');
          setDocuments(completed);
          if (completed.length > 0) {
            setSelectedDocId(completed[0].id);
          }
        }
      } catch (e) {
        console.error("Failed fetching documents", e);
      }
    };
    fetchDocs();
  }, []);

  const handleCheckCompliance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocId) return;

    setLoading(true);
    setError('');
    setReport(null);

    try {
      const response = await authenticatedFetch('/api/compliance/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: selectedDocId,
          regulation_scope: scopeFilter || null
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();
      setReport(data);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Failed to complete compliance audit.');
    } finally {
      setLoading(false);
    }
  };

  const getRiskBadge = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'high': return 'badge-risk-high';
      case 'medium': return 'badge-risk-medium';
      default: return 'badge-risk-low';
    }
  };

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Compliance Intelligence</h1>
        <p className="page-desc">Audit documents and operational logs against regulatory compliance requirements</p>
      </header>

      <div className="split-layout">
        <div>
          <div className="card-panel">
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>Run Audit Inquest</h2>
            <form onSubmit={handleCheckCompliance} style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'end' }}>
              <div className="form-group" style={{ flex: 1, minWidth: '200px', marginBottom: 0 }}>
                <label className="form-label">Select Document to Review</label>
                <select
                  value={selectedDocId}
                  onChange={(e) => setSelectedDocId(Number(e.target.value))}
                  className="form-input"
                  disabled={loading || documents.length === 0}
                  style={{ background: 'var(--bg-secondary)', height: '45px' }}
                >
                  {documents.length === 0 ? (
                    <option value="">No completed documents available</option>
                  ) : (
                    documents.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.filename}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div className="form-group" style={{ width: '160px', marginBottom: 0 }}>
                <label className="form-label">Scope Filter</label>
                <input
                  type="text"
                  value={scopeFilter}
                  onChange={(e) => setScopeFilter(e.target.value)}
                  placeholder="e.g. OISD, PESO"
                  className="form-input"
                  style={{ height: '45px' }}
                  disabled={loading || documents.length === 0}
                />
              </div>

              <button 
                type="submit" 
                className="btn btn-primary" 
                disabled={loading || !selectedDocId}
                style={{ height: '45px' }}
              >
                {loading ? 'Auditing...' : 'Evaluate Gaps'}
              </button>
            </form>
          </div>

          {loading && (
            <div className="card-panel" style={{ marginTop: '1.5rem', textAlign: 'center', padding: '3rem' }}>
              <div className="thinking-dots" style={{ marginBottom: '1rem' }}>
                <span></span>
                <span></span>
                <span></span>
              </div>
              <p style={{ color: 'var(--text-secondary)' }}>Comparing document facts with regulatory codes in Neo4j...</p>
            </div>
          )}

          {error && (
            <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '8px', color: 'var(--accent-red)', fontSize: '0.9rem' }}>
              {error}
            </div>
          )}

          {report && (
            <div className="card-panel" style={{ marginTop: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.75rem', marginBottom: '1.25rem' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Identified Compliance Gaps</h2>
                <div>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginRight: '0.5rem' }}>Overall Risk Rating:</span>
                  <span className={`badge ${getRiskBadge(report.overall_risk)}`}>
                    {report.overall_risk} Risk
                  </span>
                </div>
              </div>

              <div className="data-table-container">
                {report.gaps.length === 0 ? (
                  <p style={{ color: 'var(--accent-green)', textAlign: 'center', padding: '2.5rem', fontWeight: 600 }}>
                    ✓ 100% Compliant. No gaps detected for the active document.
                  </p>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th style={{ width: '20%' }}>Regulation</th>
                        <th style={{ width: '35%' }}>Finding / Gap Detected</th>
                        <th style={{ width: '15%' }}>Risk Level</th>
                        <th style={{ width: '30%' }}>Recommendation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.gaps.map((gap, i) => (
                        <tr key={i}>
                          <td style={{ fontWeight: 600, verticalAlign: 'top' }}>
                            {gap.regulation}
                          </td>
                          <td style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.5, verticalAlign: 'top' }}>
                            <p style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>Requirement: {gap.requirement}</p>
                            <p style={{ fontStyle: 'italic' }}>Finding: {gap.finding}</p>
                          </td>
                          <td style={{ verticalAlign: 'top' }}>
                            <span className={`badge ${getRiskBadge(gap.risk_level)}`}>
                              {gap.risk_level}
                            </span>
                          </td>
                          <td style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.5, verticalAlign: 'top' }}>
                            {gap.recommendation}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
                <button 
                  onClick={() => window.print()} 
                  className="btn btn-secondary"
                  style={{ fontSize: '0.85rem', padding: '0.6rem 1.2rem' }}
                >
                  🖨️ Export PDF for Audit Readiness
                </button>
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="card-panel">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem' }}>Active Regulation Catalog</h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1rem' }}>
              The knowledge graph stores and queries safety guidelines dynamically:
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--card-border)', padding: '0.75rem', borderRadius: '6px' }}>
                <span className="badge badge-pending" style={{ background: 'rgba(245, 158, 11, 0.1)', color: 'var(--accent-amber)', fontSize: '0.7rem', padding: '0.1rem 0.3rem', marginBottom: '0.25rem' }}>OISD-105</span>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Work Permit Systems</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Governs hot work, cold work, vessel entry, and electrical lockouts.</p>
              </div>
              <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--card-border)', padding: '0.75rem', borderRadius: '6px' }}>
                <span className="badge badge-completed" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-green)', fontSize: '0.7rem', padding: '0.1rem 0.3rem', marginBottom: '0.25rem' }}>FA-36</span>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Factory Act Section 36</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Details safety measures concerning dangerous fumes and pressure systems.</p>
              </div>
              <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--card-border)', padding: '0.75rem', borderRadius: '6px' }}>
                <span className="badge badge-processing" style={{ background: 'rgba(14, 165, 233, 0.1)', color: 'var(--accent-teal)', fontSize: '0.7rem', padding: '0.1rem 0.3rem', marginBottom: '0.25rem' }}>PESO-GCR</span>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>PESO Gas Cylinders</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Specifies distances, layouts, and certifications of pressurized facilities.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
