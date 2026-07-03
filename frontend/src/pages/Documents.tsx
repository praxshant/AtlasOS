import { useState, useRef, useCallback } from 'react';
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

  const { data: documentsRaw, isLoading, refetch } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });
  const documents = Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || [];

  const handleUpload = useCallback(
    async (files: FileList) => {
      const arr = Array.from(files);
      for (const file of arr) {
        setUploading((prev) => [...prev, file.name]);
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source', 'upload');
        try {
          await authenticatedFetch('/upload', { method: 'POST', body: formData });
        } catch {
          // upload error handled silently for now
        }
        setUploading((prev) => prev.filter((n) => n !== file.name));
      }
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['graph-data'] });
    },
    [queryClient]
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
      {uploading.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {uploading.map((name) => (
            <Badge key={name} variant="info" className="flex items-center gap-1.5">
              <Loader2 size={10} className="animate-spin" />
              {name}
            </Badge>
          ))}
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
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc: any) => (
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
