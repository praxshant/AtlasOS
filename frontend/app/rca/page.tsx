'use client';

import React, { useState } from 'react';
import { authenticatedFetch } from '../../utils/api';

interface CauseNode {
  name: string;
  children?: CauseNode[];
}

interface ProbableCause {
  cause: string;
  confidence: number;
  evidence_refs: string[];
}

interface RCAReport {
  summary: string;
  probable_causes: ProbableCause[];
  cause_tree: CauseNode;
  confidence_score: number;
  cited_docs: string[];
}

// Recursive Cause Tree Node Component
function CausalTreeNode({ node, isRoot = false }: { node: CauseNode; isRoot?: boolean }) {
  return (
    <div className="tree-node" style={{ marginLeft: isRoot ? '0' : '1.5rem', borderLeft: isRoot ? 'none' : '1px dashed var(--text-muted)' }}>
      <div className={`node-content ${isRoot ? 'root' : ''}`} style={{ 
        background: isRoot ? 'rgba(249, 115, 22, 0.1)' : 'var(--bg-secondary)',
        border: isRoot ? '1px solid var(--accent-coral)' : '1px solid var(--card-border)',
        padding: '0.65rem 1rem',
        borderRadius: '6px',
        display: 'inline-block',
        fontSize: '0.9rem',
        marginBottom: '0.5rem',
        fontWeight: isRoot ? 600 : 400
      }}>
        {isRoot ? '🚨 ' : '↳ '} {node.name}
      </div>
      {node.children && node.children.map((child, idx) => (
        <CausalTreeNode key={idx} node={child} />
      ))}
    </div>
  );
}

export default function RCAPage() {
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'idle' | 'parsing' | 'retrieval' | 'synthesis' | 'done'>('idle');
  const [report, setReport] = useState<RCAReport | null>(null);
  const [error, setError] = useState('');

  const handleRunRCA = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;

    setLoading(true);
    setError('');
    setReport(null);

    // Simulate step progression for better UI experience
    setStep('parsing');
    
    try {
      // Step 1: parsing (quick delay)
      await new Promise(r => setTimeout(r, 800));
      setStep('retrieval');
      
      // Step 2: call API
      const response = await authenticatedFetch('/api/rca/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_description: description })
      });

      setStep('synthesis');
      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();
      setReport(data);
      setStep('done');
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Failed to complete Root Cause Analysis.');
      setStep('idle');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Root Cause Analysis (RCA)</h1>
        <p className="page-desc">Initiate automated investigation state machine to construct incident causal trees</p>
      </header>

      <div className="split-layout">
        <div>
          <div className="card-panel">
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>Initiate Investigation</h2>
            <form onSubmit={handleRunRCA}>
              <div className="form-group">
                <label className="form-label">Incident Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the incident (e.g., 'Oil leakage observed from seal of feed pump P-104 on Unit 3. Fire safety team notified. System shut down.')"
                  className="form-input"
                  disabled={loading}
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={loading || !description.trim()}>
                Run Analysis
              </button>
            </form>
          </div>

          {loading && (
            <div className="card-panel" style={{ marginTop: '1.5rem' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '1rem' }}>Investigation Progress</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                  <span style={{ color: step === 'parsing' ? 'var(--accent-teal)' : 'var(--text-secondary)' }}>
                    {step === 'parsing' ? '●' : '✓'} 1. Parsing Incident Parameters...
                  </span>
                  {step === 'parsing' && <span className="thinking-dots"><span></span><span></span><span></span></span>}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                  <span style={{ color: step === 'retrieval' ? 'var(--accent-teal)' : step === 'parsing' ? 'var(--text-muted)' : 'var(--text-secondary)' }}>
                    {step === 'retrieval' ? '●' : step === 'parsing' ? '○' : '✓'} 2. Retrieving Maintenance History & Similar Failures...
                  </span>
                  {step === 'retrieval' && <span className="thinking-dots"><span></span><span></span><span></span></span>}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                  <span style={{ color: step === 'synthesis' ? 'var(--accent-teal)' : (step === 'parsing' || step === 'retrieval') ? 'var(--text-muted)' : 'var(--text-secondary)' }}>
                    {step === 'synthesis' ? '●' : '○'} 3. Synthesizing Evidence & Constructing Causal Tree...
                  </span>
                  {step === 'synthesis' && <span className="thinking-dots"><span></span><span></span><span></span></span>}
                </div>
              </div>
            </div>
          )}

          {error && (
            <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '8px', color: 'var(--accent-red)', fontSize: '0.9rem' }}>
              {error}
            </div>
          )}

          {report && (
            <div className="card-panel" style={{ marginTop: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>RCA Executive Summary</h2>
                <div>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginRight: '0.5rem' }}>Confidence Score:</span>
                  <span className={`badge ${report.confidence_score > 0.7 ? 'badge-completed' : 'badge-pending'}`}>
                    {Math.round(report.confidence_score * 100)}%
                  </span>
                </div>
              </div>
              <p style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {report.summary}
              </p>

              <div style={{ marginTop: '1.5rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>Probable Causes</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {report.probable_causes.map((c, i) => (
                    <div key={i} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--card-border)', borderRadius: '8px', padding: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                      <div style={{ flex: 1 }}>
                        <p style={{ fontWeight: 500, fontSize: '0.95rem', marginBottom: '0.25rem' }}>{c.cause}</p>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                          Evidence references: {c.evidence_refs.join(', ') || 'N/A'}
                        </p>
                      </div>
                      <span className="badge badge-completed" style={{ background: 'rgba(14, 165, 233, 0.1)', color: 'var(--accent-teal)', border: '1px solid rgba(14, 165, 233, 0.2)' }}>
                        {Math.round(c.confidence * 100)}% Match
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div>
          {report ? (
            <div className="card-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>Causal Tree Topology</h3>
                <div className="cause-tree-container" style={{ background: 'var(--bg-secondary)' }}>
                  <CausalTreeNode node={report.cause_tree} isRoot={true} />
                </div>
              </div>

              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Cited Documents</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {report.cited_docs.length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No direct document references found.</p>
                  ) : (
                    report.cited_docs.map((doc, idx) => (
                      <div key={idx} style={{ padding: '0.5rem 0.75rem', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid var(--card-border)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        📄 {doc}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="card-panel" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
              <span style={{ fontSize: '3rem', display: 'block', marginBottom: '1rem' }}>🧭</span>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Investigation Panel</h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Submit an incident description on the left to view the constructed root cause hierarchy, contributing factors, and confidence scoring.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
