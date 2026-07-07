import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, RefreshCw, Trash2, Loader2 } from 'lucide-react';
import { getJson, authenticatedFetch } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Button } from '../components/ui/Button';

const ACCEPTED = '.pdf,.docx,.txt,.log,.csv,.xlsx,.xls,.pptx,.ppt,.json';

export function Documents() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [skippedFiles, setSkippedFiles] = useState<string[]>([]);
  const [sortConfig, setSortConfig] = useState<{key: string, direction: 'asc'|'desc'} | null>(null);

  const { data: documentsRaw, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents')
  });
  const documents = Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || [];

  const sortedDocuments = [...documents].sort((a, b) => {
    if (!sortConfig) return 0;
    const key = sortConfig.key;
    const valA = a[key];
    const valB = b[key];
    
    if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
    if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
    return 0;
  });

  const requestSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  useEffect(() => {
    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
    // We pass the token as a query parameter because EventSource doesn't support custom headers
    const eventSource = new EventSource(`/api/documents/stream?token=${token}`, { withCredentials: true });

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'document_update' && data.document) {
          queryClient.setQueryData(['documents'], (oldData: any) => {
            const oldDocs = Array.isArray(oldData) ? oldData : oldData?.documents || [];
            
            // If it's a deletion event and status is 'deleted', we might want to remove it
            if (data.document.status === 'deleted') {
              return oldDocs.filter((d: any) => d.id !== data.document.id);
            }

            const exists = oldDocs.some((d: any) => d.id === data.document.id);
            if (exists) {
              return oldDocs.map((d: any) => d.id === data.document.id ? data.document : d);
            } else {
              return [data.document, ...oldDocs];
            }
          });
        }
      } catch (err) {
        console.error('Failed to parse SSE message', err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [queryClient]);

async function calculateHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

  const handleUpload = useCallback(
    async (files: FileList) => {
      const arr = Array.from(files);
      const skipped: string[] = [];
      const toCheck: { file: File, hash: string }[] = [];

      // Phase 1: Local deduplication and Hashing
      for (const file of arr) {
        const existsInServer = documents.some((d: any) => d.filename === file.name);
        if (existsInServer) {
          skipped.push(file.name);
          continue;
        }
        
        try {
          const hash = await calculateHash(file);
          // Check if already in the current batch by hash
          if (toCheck.some(f => f.hash === hash)) {
            skipped.push(file.name);
          } else {
            toCheck.push({ file, hash });
          }
        } catch (e) {
          console.error("Failed to hash file", file.name, e);
        }
      }

      if (toCheck.length === 0) {
        if (skipped.length > 0) setSkippedFiles(skipped);
        return;
      }

      // Phase 2: Server Pre-flight Hash Check
      let existingHashes: string[] = [];
      try {
        const checkRes = await authenticatedFetch('/upload/check', {
          method: 'POST',
          body: { hashes: toCheck.map(f => f.hash) } as any
        });
        const checkData = await checkRes.json();
        existingHashes = checkData.existing_hashes || [];
      } catch (e) {
        console.error("Pre-flight hash check failed", e);
      }

      const toUpload = toCheck.filter(f => {
        if (existingHashes.includes(f.hash)) {
          skipped.push(f.file.name);
          return false;
        }
        return true;
      });

      if (skipped.length > 0) {
        setSkippedFiles(skipped);
      } else {
        setSkippedFiles([]);
      }

      if (toUpload.length === 0) return;

      setUploading((prev) => [...prev, ...toUpload.map(f => f.file.name)]);
      
      // Phase 3: Concurrency Controlled Upload Queue (Max 30)
      const maxConcurrent = 30;
      let active = 0;
      let index = 0;

      await new Promise<void>((resolve) => {
        const next = async () => {
          if (index >= toUpload.length && active === 0) {
            resolve();
            return;
          }
          while (active < maxConcurrent && index < toUpload.length) {
            const { file } = toUpload[index++];
            active++;
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('source', 'upload');
            
            authenticatedFetch('/upload', { method: 'POST', body: formData })
              .then(async (res) => {
                if (!res.ok) {
                  const data = await res.json().catch(() => ({}));
                  alert(`Upload failed for ${file.name}: ${data.detail || 'Unknown error'}`);
                }
              })
              .catch((e: any) => {
                alert(`Upload failed for ${file.name}: ${e.message}`);
              })
              .finally(() => {
                setUploading((prev) => prev.filter((n) => n !== file.name));
                active--;
                next();
              });
          }
        };
        next();
      });
      
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['graph-data'] });
    },
    [documents, queryClient]
  );

  const handleDelete = useCallback(
    async (docId: number) => {
      try {
        await authenticatedFetch(`/documents/${docId}`, { method: 'DELETE' });
        queryClient.invalidateQueries({ queryKey: ['documents'] });
        queryClient.invalidateQueries({ queryKey: ['stats'] });
        queryClient.invalidateQueries({ queryKey: ['graph-data'] });
      } catch {
        // deletion error
      }
    },
    [queryClient]
  );

  const [dragActive, setDragActive] = useState(false);

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Documents</h2>

      {/* Upload zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${dragActive ? 'border-primary bg-primary/5' : 'border-outline-variant/40 hover:border-primary/50 hover:bg-surface-variant/10'}`}
        onDragEnter={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => e.target.files && handleUpload(e.target.files)}
        />
        <Upload size={20} className="text-on-surface-variant mb-3" />
        <p className="text-sm font-medium">Drop files here or click to browse</p>
        <p className="text-xs text-on-surface-variant mt-1">PDF, DOCX, CSV, XLSX, PPTX — up to 10 MB</p>
      </div>

      {/* Uploading indicator */}
      {(uploading.length > 0 || skippedFiles.length > 0) && (
        <div className="flex flex-col items-center">
          {uploading.length > 0 && (
            <div className="flex flex-wrap gap-2 justify-center mt-4">
              {uploading.map(f => (
                <Badge key={f} variant="info" className="flex items-center gap-1 bg-cyan-900/30 text-cyan-400">
                  <Loader2 size={12} className="animate-spin" /> {f}
                </Badge>
              ))}
            </div>
          )}

          {skippedFiles.length > 0 && (
            <div className="mt-4 p-4 border border-yellow-500/30 bg-yellow-500/10 rounded text-yellow-300 text-sm flex flex-col items-center">
              <p className="font-semibold mb-2">Skipped {skippedFiles.length} duplicate file(s) that already exist:</p>
              <div className="flex flex-wrap gap-2 justify-center">
                {skippedFiles.map(f => (
                  <Badge key={f} variant="outline" className="border-yellow-500/50 text-yellow-300">
                    {f}
                  </Badge>
                ))}
              </div>
              <Button 
                variant="ghost" 
                size="sm" 
                className="mt-2 text-yellow-400 hover:text-yellow-200 hover:bg-yellow-500/20"
                onClick={() => setSkippedFiles([])}
              >
                Dismiss
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Documents table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-sm">{documents.length} Documents</CardTitle>
          <button onClick={() => refetch()} className="p-1.5 text-on-surface-variant hover:text-primary transition-colors">
            <RefreshCw size={14} />
          </button>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="h-32 flex items-center justify-center text-xs text-on-surface-variant">Loading...</div>
          ) : documents.length === 0 ? (
            <div className="h-32 flex items-center justify-center text-xs text-on-surface-variant">
              No documents yet. Upload your first file above.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead onClick={() => requestSort('filename')} className="cursor-pointer hover:text-primary">
                    Name {sortConfig?.key === 'filename' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                  </TableHead>
                  <TableHead onClick={() => requestSort('file_type')} className="cursor-pointer hover:text-primary">
                    Type {sortConfig?.key === 'file_type' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                  </TableHead>
                  <TableHead onClick={() => requestSort('status')} className="cursor-pointer hover:text-primary">
                    Status {sortConfig?.key === 'status' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                  </TableHead>
                  <TableHead onClick={() => requestSort('upload_time')} className="cursor-pointer hover:text-primary">
                    Uploaded {sortConfig?.key === 'upload_time' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
                  </TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedDocuments.map((doc: any) => (
                  <TableRow key={doc.id}>
                    <TableCell className="text-sm font-medium flex items-center gap-2">
                      <FileText size={13} className="text-on-surface-variant shrink-0" />
                      <span className="truncate max-w-[260px]">{doc.filename}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{doc.file_type}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={doc.status === 'completed' ? 'success' : doc.status === 'failed' ? 'danger' : 'warning'}
                      >
                        {doc.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-[11px] font-mono text-on-surface-variant">
                      {new Date(doc.upload_time).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
                        className="p-1 text-on-surface-variant hover:text-error transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={13} />
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
