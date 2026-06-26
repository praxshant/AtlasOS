'use client';

import React, { useState, useRef } from 'react';
import { authenticatedFetch } from '../utils/api';

interface UploadResult {
  filename: string;
  chunks: number;
  entities: number;
}

interface DocumentUploadProps {
  onUploadSuccess?: () => void;
}

export default function DocumentUpload({ onUploadSuccess }: DocumentUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [errorText, setErrorText] = useState('');
  const [successResult, setSuccessResult] = useState<UploadResult | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      uploadFile(e.target.files[0]);
    }
  };

  const onButtonClick = () => {
    fileInputRef.current?.click();
  };

  const pollJobStatus = (jobId: string, filename: string) => {
    let elapsed = 0;
    const interval = setInterval(async () => {
      elapsed += 2000;
      if (elapsed > 60000) {
        clearInterval(interval);
        setLoading(false);
        setErrorText("Processing timeout (60s). The ingestion worker may be offline or heavily loaded.");
        setStatusText('');
        return;
      }
      try {
        const response = await authenticatedFetch(`/api/jobs/${jobId}`);
        if (!response.ok) throw new Error("Failed to fetch job status");
        
        const data = await response.json();
        
        if (data.status === 'completed') {
          clearInterval(interval);
          setLoading(false);
          setSuccessResult({
            filename: filename,
            chunks: data.chunks_extracted,
            entities: data.entities_extracted
          });
          setStatusText('');
          if (onUploadSuccess) onUploadSuccess();
        } else if (data.status === 'failed') {
          clearInterval(interval);
          setLoading(false);
          setErrorText(`Processing failed: ${data.error || 'Unknown error'}`);
          setStatusText('');
        } else {
          setStatusText(`Analyzing document (extracted: ${data.chunks_extracted} chunks, ${data.entities_extracted} entities)...`);
        }
      } catch (err: any) {
        console.error(err);
        clearInterval(interval);
        setLoading(false);
        setErrorText("Lost connection to processing worker.");
        setStatusText('');
      }
    }, 2000);
  };

  const uploadFile = async (file: File) => {
    setLoading(true);
    setErrorText('');
    setSuccessResult(null);
    setStatusText('Uploading file...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('source', 'upload');

    try {
      const response = await authenticatedFetch('/api/upload', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Upload failed');
      }

      const data = await response.json();
      setStatusText('Queueing document intelligence ingestion worker...');
      pollJobStatus(data.job_id, file.name);

    } catch (err: any) {
      setLoading(false);
      setErrorText(err.message || 'Failed to upload document.');
      setStatusText('');
    }
  };

  return (
    <div className="card-panel" style={{ marginBottom: '2rem' }}>
      <div 
        className={`upload-zone ${dragActive ? 'active' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input 
          ref={fileInputRef}
          type="file" 
          className="hidden" 
          style={{ display: 'none' }}
          onChange={handleChange}
          accept=".pdf,.docx,.txt,.log"
        />
        
        <span className="upload-icon">📤</span>
        <h3 className="upload-title">Drag & drop your files here</h3>
        <p className="upload-hint" style={{ marginBottom: '1rem' }}>Supports PDF, DOCX, TXT, and operational logs</p>
        
        <button 
          type="button" 
          className="btn btn-secondary" 
          onClick={onButtonClick}
          disabled={loading}
        >
          Select File
        </button>
      </div>

      {loading && (
        <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
          <div className="thinking-dots" style={{ marginBottom: '0.5rem' }}>
            <span></span>
            <span></span>
            <span></span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>{statusText}</p>
        </div>
      )}

      {errorText && (
        <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '8px', color: 'var(--accent-red)', fontSize: '0.9rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div><strong>Error: </strong> {errorText}</div>
          <button onClick={() => setErrorText('')} className="btn btn-secondary" style={{ padding: '0.25rem 0.75rem', fontSize: '0.8rem' }}>Dismiss</button>
        </div>
      )}

      {successResult && (
        <div style={{ marginTop: '1.5rem', padding: '1.25rem', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.15)', borderRadius: '8px' }}>
          <h4 style={{ color: 'var(--accent-green)', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.95rem' }}>✓ Ingestion Successful</h4>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            Successfully processed <strong>{successResult.filename}</strong>. Segmented into <strong>{successResult.chunks}</strong> text chunks and extracted <strong>{successResult.entities}</strong> distinct nodes for the Knowledge Graph.
          </p>
        </div>
      )}
    </div>
  );
}
