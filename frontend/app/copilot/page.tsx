'use client';

import React, { useState } from 'react';
import ChatInterface from '../../components/ChatInterface';
import GraphViewer from '../../components/GraphViewer';

interface Citation {
  id: number;
  filename: string;
  page: number;
  snippet: string;
}

export default function CopilotPage() {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [graphEvidence, setGraphEvidence] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [activeTab, setActiveTab] = useState<'citations' | 'graph'>('citations');

  const handleCitationsChange = (newCitations: Citation[]) => {
    setCitations(newCitations);
    // Switch to citations tab
    setActiveTab('citations');
  };

  const handleGraphChange = (newGraph: any) => {
    // Map graph to format expected by GraphViewer
    const nodes = (newGraph.nodes || []).map((n: any) => ({
      id: n.name,
      name: n.name,
      label: n.label,
      confidence: 1.0
    }));
    const edges = newGraph.edges || [];
    setGraphEvidence({ nodes, edges });
    
    // Switch to graph tab if nodes found
    if (nodes.length > 0) {
      setActiveTab('graph');
    }
  };

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Expert Knowledge Copilot</h1>
        <p className="page-desc">Ask natural language questions to reason over plants operational manuals and safety logs</p>
      </header>

      <div className="split-layout">
        <div>
          <ChatInterface 
            onCitationsChange={handleCitationsChange}
            onGraphChange={handleGraphChange}
          />
        </div>

        <div>
          <div className="card-panel" style={{ height: '600px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', borderBottom: '1px solid var(--card-border)', marginBottom: '1rem', paddingBottom: '0.5rem', gap: '1rem' }}>
              <button 
                onClick={() => setActiveTab('citations')}
                style={{ 
                  background: 'none', 
                  border: 'none', 
                  color: activeTab === 'citations' ? 'var(--accent-teal)' : 'var(--text-secondary)',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  cursor: 'pointer',
                  borderBottom: activeTab === 'citations' ? '2px solid var(--accent-teal)' : 'none',
                  paddingBottom: '0.5rem'
                }}
              >
                Cited Documents ({citations.length})
              </button>
              <button 
                onClick={() => setActiveTab('graph')}
                style={{ 
                  background: 'none', 
                  border: 'none', 
                  color: activeTab === 'graph' ? 'var(--accent-teal)' : 'var(--text-secondary)',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  cursor: 'pointer',
                  borderBottom: activeTab === 'graph' ? '2px solid var(--accent-teal)' : 'none',
                  paddingBottom: '0.5rem'
                }}
              >
                Graph Evidence ({graphEvidence.nodes.length})
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
              {activeTab === 'citations' ? (
                citations.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '4rem' }}>
                    No citations surfaced yet. Submit a query to see grounded source document citations.
                  </p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                    {citations.map((c) => (
                      <div key={c.id} style={{ borderLeft: '3px solid var(--accent-teal)', paddingLeft: '0.75rem' }}>
                        <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
                          [{c.id}] {c.filename} <span style={{ color: 'var(--text-muted)' }}>(Page {c.page})</span>
                        </h4>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5, fontStyle: 'italic' }}>
                          "{c.snippet}"
                        </p>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                graphEvidence.nodes.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '4rem' }}>
                    No matching knowledge path found for current query.
                  </p>
                ) : (
                  <div style={{ height: '100%', minHeight: '380px' }}>
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                      Topology Subgraph:
                    </h4>
                    <div style={{ height: '340px' }}>
                      <GraphViewer data={graphEvidence} />
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
