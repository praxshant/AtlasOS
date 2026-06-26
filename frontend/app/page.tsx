'use client';

import React, { useState, useEffect } from 'react';
import DocumentUpload from '../components/DocumentUpload';
import { authenticatedFetch } from '../utils/api';

interface Stats {
  documents: number;
  chunks: number;
  entities: number;
  graph_nodes: number;
  graph_edges: number;
}

interface DocumentItem {
  id: number;
  filename: string;
  file_type: string;
  status: string;
  upload_time: string;
  source: string;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats>({
    documents: 0,
    chunks: 0,
    entities: 0,
    graph_nodes: 0,
    graph_edges: 0
  });
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStats = async () => {
    try {
      const response = await authenticatedFetch('/api/stats');
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (e) {
      console.error("Failed fetching stats", e);
    }
  };

  const fetchDocuments = async () => {
    try {
      const response = await authenticatedFetch('/api/documents');
      if (response.ok) {
        const data = await response.json();
        setDocuments(data);
      }
    } catch (e) {
      console.error("Failed fetching documents", e);
    }
  };

  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStats(), fetchDocuments()]);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  const getBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed': return 'badge-completed';
      case 'processing': return 'badge-processing';
      case 'failed': return 'badge-failed';
      default: return 'badge-pending';
    }
  };

  return (
    <div>
      <header className="page-header">
        <h1 className="page-title">Operational Intelligence Dashboard</h1>
        <p className="page-desc">ATLASOS: Industrial Knowledge Ingestion and Semantic Verification Platform</p>
      </header>

      {/* Stats Counter Section */}
      <section className="stats-grid">
        <div className="card-panel stat-card teal">
          <span className="stat-label">Ingested Files</span>
          <span className="stat-value">{stats.documents} <span>docs</span></span>
        </div>
        <div className="card-panel stat-card coral">
          <span className="stat-label">Text Segments</span>
          <span className="stat-value">{stats.chunks} <span>chunks</span></span>
        </div>
        <div className="card-panel stat-card amber">
          <span className="stat-label">Extracted Entities</span>
          <span className="stat-value">{stats.entities} <span>entities</span></span>
        </div>
        <div className="card-panel stat-card purple">
          <span className="stat-label">Graph Entities</span>
          <span className="stat-value">{stats.graph_nodes} <span>total</span></span>
        </div>
        <div className="card-panel stat-card green">
          <span className="stat-label">Graph Edges</span>
          <span className="stat-value">{stats.graph_edges} <span>edges</span></span>
        </div>
      </section>

      {/* Ingestion Split Layout */}
      <div className="split-layout">
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>Ingest Operational Documents</h2>
          <DocumentUpload onUploadSuccess={loadData} />

          <div className="card-panel" style={{ marginTop: '1.5rem' }}>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1.25rem' }}>Document Registry</h2>
            <div className="data-table-container">
              {loading ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <div className="thinking-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              ) : documents.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>No documents uploaded yet. Upload a document to start indexing.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Filename</th>
                      <th>Format</th>
                      <th>Source</th>
                      <th>Status</th>
                      <th>Upload Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((doc) => (
                      <tr key={doc.id}>
                        <td style={{ fontWeight: 500 }}>{doc.filename}</td>
                        <td><span style={{ fontSize: '0.8rem', background: 'var(--bg-tertiary)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>{doc.file_type}</span></td>
                        <td style={{ color: 'var(--text-secondary)' }}>{doc.source}</td>
                        <td>
                          <span className={`badge ${getBadgeClass(doc.status)}`}>
                            {doc.status}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                          {new Date(doc.upload_time).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

        <div>
          <div className="card-panel">
            <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '1rem' }}>Operational Scope</h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '1rem' }}>
              ATLASOS bridges the gap between text records (PDF reports, procedures) and topological relations.
            </p>
            <ul style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <li><strong>Relational mapping</strong>: Verifies structured records with ACID safety.</li>
              <li><strong>Vector encoding</strong>: Embeds 512-word text chunks into Qdrant for fast semantic lookup.</li>
              <li><strong>Graph synthesis</strong>: Extracts Asset, Incident, and Regulation relationships into Neo4j.</li>
              <li><strong>LangGraph Reasoning</strong>: Powers deep agent inspections for Root Cause and Compliance.</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
