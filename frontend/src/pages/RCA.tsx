import { useState } from 'react';
import { authenticatedFetch } from '../api/client';
import { GitBranch, Loader2, Play, ShieldCheck, AlertTriangle } from 'lucide-react';

const STEPS = [
  { id: 'parsing',   label: 'Parsing incident description' },
  { id: 'retrieval', label: 'Retrieving contextual knowledge' },
  { id: 'analysis',  label: 'Building causal tree' },
];

const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

function FaultNode({ node, depth }: { node: any; depth: number }) {
  if (!node) return null;
  const label = node.event || node.description || node.name || JSON.stringify(node);
  const children = node.children || node.causes || [];
  const badgeCls = depth === 0 ? 'badge-danger' : children.length === 0 ? 'badge-info' : 'badge-neutral';

  return (
    <div style={{ marginLeft: depth > 0 ? 'var(--space-6)' : 0, borderLeft: depth > 0 ? '1px solid var(--border-default)' : 'none', paddingLeft: depth > 0 ? 'var(--space-3)' : 0 }}>
      <div style={{ padding: 'var(--space-1) 0' }}>
        <span className={`badge ${badgeCls}`}>{label}</span>
      </div>
      {children.map((child: any, i: number) => (
        <FaultNode key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

export function RCA() {
  const [input, setInput] = useState('');
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAnalysis = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError(null);
    setReport(null);

    setStep('parsing');
    await delay(900);
    setStep('retrieval');
    await delay(1200);
    setStep('analysis');

    try {
      const res = await authenticatedFetch('/rca/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_description: input }),
      });
      const data = await res.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message || 'Analysis failed. Please try again.');
    }
    setLoading(false);
    setStep(null);
  };

  const faultTree = (() => {
    try { return typeof report?.fault_tree === 'string' ? JSON.parse(report.fault_tree) : report?.fault_tree; }
    catch { return null; }
  })();

  const whyChain = (() => {
    try {
      const w = typeof report?.why_chain === 'string' ? JSON.parse(report.why_chain) : report?.why_chain;
      return Array.isArray(w) ? w : null;
    } catch { return null; }
  })();

  const recommendations = (() => {
    try {
      const r = typeof report?.recommendations === 'string' ? JSON.parse(report.recommendations) : report?.recommendations;
      return Array.isArray(r) ? r : null;
    } catch { return null; }
  })();

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>Root Cause Analysis</h1>
          <p className="page-subtitle">AI-driven causal tree generation</p>
        </div>
        <button
          className="btn-primary"
          onClick={runAnalysis}
          disabled={loading || !input.trim()}
        >
          {loading ? 'Analyzing...' : 'Analyze Incident'}
        </button>
      </div>

      {/* Input Card */}
      <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="card-header">
          <h3>Incident Description</h3>
        </div>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe the incident, failure, or anomaly in detail — e.g. 'Pump P-104 seal failure caused downstream contamination on 2025-03-12...'"
          disabled={loading}
          style={{
            width: '100%',
            minHeight: 120,
            background: 'var(--bg-subtle)',
            border: '1px solid var(--border-default)',
            borderRadius: 5,
            padding: 'var(--space-3)',
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
            resize: 'vertical',
            outline: 'none',
            fontFamily: 'inherit',
            lineHeight: 'var(--line-height-base)',
            boxSizing: 'border-box',
          }}
          onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
          onBlur={e => (e.target.style.borderColor = 'var(--border-default)')}
        />
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: 'var(--status-danger-dim)', border: '1px solid var(--status-danger)',
          borderRadius: 5, padding: 'var(--space-3) var(--space-4)',
          color: 'var(--status-danger)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-4)',
        }}>{error}</div>
      )}

      {/* Progress Steps */}
      {loading && step && (
        <div className="card" style={{ marginBottom: 'var(--space-6)' }}>
          <div className="card-header"><h3>Analyzing...</h3></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {STEPS.map((s) => {
              const stepIdx = STEPS.findIndex(x => x.id === step);
              const thisIdx = STEPS.findIndex(x => x.id === s.id);
              const done = thisIdx < stepIdx;
              const active = s.id === step;
              return (
                <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                  {done ? (
                    <span style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--status-ok-dim)', color: 'var(--status-ok)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, flexShrink: 0 }}>✓</span>
                  ) : active ? (
                    <Loader2 size={20} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                  ) : (
                    <span style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--bg-subtle)', border: '1px solid var(--border-default)', flexShrink: 0 }} />
                  )}
                  <span style={{
                    fontSize: 'var(--text-sm)',
                    color: done ? 'var(--status-ok)' : active ? 'var(--text-primary)' : 'var(--text-tertiary)',
                    fontWeight: active ? 500 : 400,
                  }}>{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Report */}
      {report && !loading && (
        <div className="card">
          <div className="card-header">
            <h3>RCA Report</h3>
            <span className="badge badge-ok">COMPLETE</span>
          </div>

          {/* Fault Tree */}
          {faultTree && (
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <p style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>Fault Tree</p>
              <FaultNode node={faultTree} depth={0} />
            </div>
          )}

          {/* 5-Whys Chain */}
          {whyChain && whyChain.length > 0 && (
            <div style={{ marginBottom: 'var(--space-6)' }}>
              <p style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>5-Whys Chain</p>
              <div style={{ paddingLeft: 'var(--space-2)', borderLeft: '2px solid var(--border-default)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {whyChain.map((why: any, i: number) => {
                  const text = typeof why === 'string' ? why : why.description || JSON.stringify(why);
                  const clean = text.replace(/^why\s*\d*\s*[:-]?\s*/i, '');
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-3)', position: 'relative' }}>
                      <div style={{
                        width: 22, height: 22, borderRadius: '50%', background: 'var(--accent-dim)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--accent)', flexShrink: 0,
                        marginLeft: -12,
                      }}>{i + 1}</div>
                      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 'var(--line-height-base)', margin: 0 }}>{clean}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Fallback */}
          {!faultTree && !whyChain && (
            <pre style={{
              fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
              whiteSpace: 'pre-wrap', overflowX: 'auto', background: 'var(--bg-subtle)',
              padding: 'var(--space-4)', borderRadius: 5, maxHeight: 400, overflowY: 'auto',
            }}>
              {JSON.stringify(report, null, 2)}
            </pre>
          )}

          {/* Recommendations */}
          {recommendations && recommendations.length > 0 && (
            <div style={{ marginTop: 'var(--space-6)', paddingTop: 'var(--space-6)', borderTop: '1px solid var(--border-default)' }}>
              <p style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>Recommendations</p>
              <ul style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', listStyle: 'none', padding: 0, margin: 0 }}>
                {recommendations.map((rec: string, i: number) => (
                  <li key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)',
                    padding: 'var(--space-2) var(--space-3)',
                    background: 'var(--status-ok-dim)', border: '1px solid var(--status-ok)',
                    borderRadius: 5, fontSize: 'var(--text-sm)', color: 'var(--text-primary)',
                  }}>
                    <ShieldCheck size={14} style={{ color: 'var(--status-ok)', marginTop: 2, flexShrink: 0 }} />
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ marginTop: 'var(--space-6)', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn-secondary"
              onClick={() => {
                const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'rca-report.json'; a.click();
              }}
            >
              Export Report
            </button>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!report && !loading && !error && (
        <div className="card">
          <div className="empty-state">
            <GitBranch size={28} style={{ opacity: 0.3 }} />
            <span>Describe an incident above to generate a root cause analysis using your knowledge graph.</span>
          </div>
        </div>
      )}
    </div>
  );
}
