'use client';

import React, { useState, useEffect } from 'react';
import GraphViewer from '../../components/GraphViewer';
import { authenticatedFetch } from '../../utils/api';

interface Node {
  id: string;
  name: string;
  label: string;
  confidence: number;
  properties?: any;
}

interface Edge {
  source: string;
  target: string;
  type: string;
  confidence: number;
}

export default function GraphPage() {
  const [rawGraph, setRawGraph] = useState<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const [filteredGraph, setFilteredGraph] = useState<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLabels, setSelectedLabels] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [loading, setLoading] = useState(true);

  // Available labels in system
  const labelsList = ["Asset", "Incident", "Person", "Procedure", "Regulation", "FailureMode", "Equipment", "LessonLearned", "AuditFinding"];

  const fetchGraphData = async () => {
    setLoading(true);
    try {
      const response = await authenticatedFetch('/api/graph/data');
      if (response.ok) {
        const data = await response.json();
        setRawGraph(data);
        setFilteredGraph(data);
      }
    } catch (e) {
      console.error("Failed fetching graph data", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphData();
  }, []);

  // Filter graph nodes and edges dynamically based on search and labels selected
  useEffect(() => {
    let nodes = rawGraph.nodes;
    
    // 1. Search term filter
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      nodes = nodes.filter(n => n.name.toLowerCase().includes(term) || n.label.toLowerCase().includes(term));
    }
    
    // 2. Node label filter
    if (selectedLabels.length > 0) {
      nodes = nodes.filter(n => selectedLabels.includes(n.label));
    }
    
    // Extract node IDs for valid edges
    const nodeIds = new Set(nodes.map(n => n.id));
    
    // Filter edges so that they connect only remaining nodes
    const edges = rawGraph.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
    
    setFilteredGraph({ nodes, edges });
  }, [searchTerm, selectedLabels, rawGraph]);

  const handleLabelToggle = (label: string) => {
    setSelectedLabels(prev => 
      prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
    );
  };

  const handleNodeClick = (node: Node) => {
    setSelectedNode(node);
  };

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Knowledge Graph Explorer</h1>
        <p className="page-desc">Explore interconnected assets, failure modes, people, and regulations</p>
      </header>

      {/* Graph Filter Controls */}
      <div className="card-panel" style={{ marginBottom: '1.5rem', display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center' }}>
        <div style={{ flex: 1, minWidth: '200px' }}>
          <label className="form-label">Search Entity</label>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by name or category..."
            className="form-input"
            style={{ height: '40px' }}
          />
        </div>

        <div style={{ flex: 2, minWidth: '300px' }}>
          <label className="form-label">Filter Node Labels</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {labelsList.map(label => {
              const active = selectedLabels.includes(label);
              return (
                <button
                  key={label}
                  onClick={() => handleLabelToggle(label)}
                  style={{
                    border: '1px solid var(--card-border)',
                    borderRadius: '20px',
                    padding: '0.35rem 0.75rem',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    background: active ? 'rgba(14, 165, 233, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                    color: active ? 'var(--accent-teal)' : 'var(--text-secondary)',
                    borderColor: active ? 'var(--accent-teal)' : 'var(--card-border)',
                    transition: 'var(--transition-fast)'
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        
        <button onClick={fetchGraphData} className="btn btn-secondary" style={{ height: '40px', padding: '0.5rem 1rem' }}>
          🔄 Reload Graph
        </button>
      </div>

      {/* Main Graph Grid */}
      <div className="split-layout" style={{ gridTemplateColumns: '3fr 1fr' }}>
        <div className="card-panel" style={{ padding: '0.5rem', height: '620px', display: 'flex', flexDirection: 'column' }}>
          {loading ? (
            <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center' }}>
              <div className="thinking-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          ) : filteredGraph.nodes.length === 0 ? (
            <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              No graph entities found matching current filters.
            </div>
          ) : (
            <div style={{ flex: 1 }}>
              <GraphViewer data={filteredGraph} onNodeClick={handleNodeClick} />
            </div>
          )}
        </div>

        <div>
          {selectedNode ? (
            <div className="card-panel" style={{ height: '620px', overflowY: 'auto' }}>
              <span 
                className="badge" 
                style={{ 
                  background: 'rgba(255,255,255,0.05)', 
                  border: '1px solid var(--card-border)',
                  color: 'var(--text-secondary)',
                  marginBottom: '0.75rem' 
                }}
              >
                {selectedNode.label.toUpperCase()}
              </span>
              
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '1rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
                {selectedNode.name}
              </h2>

              <div style={{ marginBottom: '1.25rem' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Provenance Confidence:</span>
                <span className="badge badge-completed">
                  {Math.round(selectedNode.confidence * 100)}%
                </span>
              </div>

              {selectedNode.properties && Object.keys(selectedNode.properties).length > 0 ? (
                <div>
                  <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Entity Properties
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
                    {Object.entries(selectedNode.properties).map(([k, v]) => (
                      <div key={k} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--card-border)', padding: '0.75rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>{k}</span>
                        <span style={{ fontSize: '0.85rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.5rem' }}>No extra properties defined for this entity.</p>
              )}

              <button 
                className="btn btn-primary" 
                style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem' }}
                onClick={async () => {
                  setLoading(true);
                  try {
                    const res = await authenticatedFetch(`/api/graph/expand/${encodeURIComponent(selectedNode.name)}`);
                    if (res.ok) {
                      const data = await res.json();
                      
                      setRawGraph(prev => {
                        const newNodes = [...prev.nodes];
                        const newEdges = [...prev.edges];
                        const existingNodeIds = new Set(prev.nodes.map(n => n.id));
                        const existingEdgeKeys = new Set(prev.edges.map(e => `${e.source}-${e.target}-${e.type}`));
                        
                        data.nodes.forEach((n: Node) => {
                          if (!existingNodeIds.has(n.id)) {
                            newNodes.push(n);
                            existingNodeIds.add(n.id);
                          }
                        });
                        
                        data.edges.forEach((e: Edge) => {
                          const key = `${e.source}-${e.target}-${e.type}`;
                          if (!existingEdgeKeys.has(key)) {
                            newEdges.push(e);
                            existingEdgeKeys.add(key);
                          }
                        });
                        
                        return { nodes: newNodes, edges: newEdges };
                      });
                    }
                  } catch (e) {
                    console.error("Failed to expand graph", e);
                  } finally {
                    setLoading(false);
                  }
                }}
              >
                <span>🌐</span> Expand Neighborhood
              </button>
            </div>
          ) : (
            <div className="card-panel" style={{ height: '620px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '2rem' }}>
              <span style={{ fontSize: '2.5rem', display: 'block', marginBottom: '1rem' }}>🔍</span>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, marginBottom: '0.5rem' }}>Node Inspector</h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                Click on any node in the knowledge network canvas to inspect its parameters, types, and properties.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
