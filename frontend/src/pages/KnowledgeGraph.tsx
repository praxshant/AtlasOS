import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Share2, Filter } from 'lucide-react';

function groupByLabel(nodes: any[]) {
  return nodes.reduce((acc: Record<string, any[]>, node) => {
    const label = node.label || node.type || 'Entity';
    if (!acc[label]) acc[label] = [];
    acc[label].push(node);
    return acc;
  }, {});
}

function labelColor(label: string): string {
  const map: Record<string, string> = {
    Asset: 'var(--accent)',
    Equipment: 'var(--accent)',
    Person: 'var(--status-ok)',
    Incident: 'var(--status-danger)',
    Procedure: 'var(--status-warn)',
    Regulation: 'var(--text-secondary)',
  };
  return map[label] || 'var(--text-tertiary)';
}

export function KnowledgeGraph() {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDocId, setSelectedDocId] = useState<string>('');

  const { data: docsData } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });
  const documents = Array.isArray(docsData) ? docsData : docsData?.documents || [];

  const { data, isLoading } = useQuery({
    queryKey: ['graph-data', selectedDocId],
    queryFn: () => getJson<any>(`/graph/data${selectedDocId ? `?document_ids=${selectedDocId}` : ''}`),
  });

  const rawNodes = data?.nodes || [];
  const rawEdges = data?.edges || [];

  const normalize = (s: string) => (s || '').toLowerCase().replace(/[- ]/g, '');

  const filteredNodes = searchTerm.trim()
    ? rawNodes.filter((n: any) =>
        normalize(n.name).includes(normalize(searchTerm)) ||
        normalize(n.id).includes(normalize(searchTerm))
      )
    : rawNodes;

  const filteredNodeIds = new Set(filteredNodes.map((n: any) => n.id));
  const filteredEdges = searchTerm.trim()
    ? rawEdges.filter((e: any) => filteredNodeIds.has(e.source) || filteredNodeIds.has(e.target))
    : rawEdges;

  const nodeTypeCount = new Set(rawNodes.map((n: any) => n.label || n.type)).size;
  const grouped = groupByLabel(filteredNodes);

  return (
    <div>
      {/* Page Header */}
      <div className="page-header" style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Knowledge Graph</h1>
          <p className="page-subtitle">Entity relationship map</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'var(--bg-subtle)', padding: '4px 12px', borderRadius: '6px', border: '1px solid var(--border-default)' }}>
            <Filter size={14} className="text-on-surface-variant" />
            <select
              value={selectedDocId}
              onChange={e => setSelectedDocId(e.target.value)}
              style={{ background: 'transparent', border: 'none', fontSize: 'var(--text-sm)', color: 'var(--text-primary)', outline: 'none' }}
            >
              <option value="">All Documents</option>
              {documents.map((doc: any) => (
                <option key={doc.id} value={doc.id}>{doc.filename}</option>
              ))}
            </select>
          </div>
          <div className="graph-search-bar" style={{ margin: 0 }}>
            <input
              className="input-field"
              type="text"
              placeholder="Search nodes..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="btn-secondary" onClick={() => setSearchTerm('')}>Clear</button>
            )}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="stat-row" style={{ marginBottom: 'var(--space-6)' }}>
        <div className="card"><div className="stat-block"><span className="stat-value">{rawNodes.length}</span><span className="stat-label">Total Nodes</span></div></div>
        <div className="card"><div className="stat-block"><span className="stat-value">{rawEdges.length}</span><span className="stat-label">Relationships</span></div></div>
        <div className="card"><div className="stat-block"><span className="stat-value">{nodeTypeCount}</span><span className="stat-label">Entity Types</span></div></div>
        {searchTerm && (
          <div className="card"><div className="stat-block"><span className="stat-value">{filteredNodes.length}</span><span className="stat-label">Filtered</span></div></div>
        )}
      </div>

      {isLoading ? (
        <div className="skeleton" style={{ height: 400 }} />
      ) : rawNodes.length === 0 && !selectedDocId ? (
        <div className="card">
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 'var(--space-16)', textAlign: 'center', color: 'var(--text-tertiary)' }}>
            <Share2 size={32} style={{ marginBottom: 'var(--space-4)', opacity: 0.4 }} />
            <p style={{ fontSize: 'var(--text-sm)' }}>No graph data yet. Upload and process documents to build the knowledge graph.</p>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-6)' }}>
          {/* Node Groups */}
          <div className="card">
            <div className="card-header">
              <h3>Entities by Type</h3>
              <span className="page-header-meta">{filteredNodes.length} nodes</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {Object.entries(grouped).map(([label, group]) => (
                <div key={label}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: labelColor(label), flexShrink: 0 }} />
                    <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-tertiary)' }}>
                      {label} ({(group as any[]).length})
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
                    {(group as any[]).map((node: any) => (
                      <span
                        key={node.id}
                        className="badge badge-neutral"
                        style={{ fontFamily: 'var(--font-mono)', cursor: 'default' }}
                      >
                        {node.name}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Relationship List */}
          <div className="card">
            <div className="card-header">
              <h3>Relationships</h3>
              <span className="page-header-meta">{filteredEdges.length}</span>
            </div>
            <div style={{ maxHeight: 500, overflowY: 'auto' }}>
              {filteredEdges.length === 0 ? (
                <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)', textAlign: 'center', padding: 'var(--space-6)' }}>No edges match.</p>
              ) : (
                filteredEdges.slice(0, 60).map((e: any, i: number) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-2)',
                      padding: 'var(--space-2) 0',
                      borderBottom: '1px solid var(--border-default)',
                      fontSize: 'var(--text-xs)',
                      flexWrap: 'wrap',
                    }}
                  >
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{e.source}</span>
                    <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>→{e.type}→</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{e.target}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
