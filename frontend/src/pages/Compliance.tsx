import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJson, authenticatedFetch } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { ShieldCheck, Play, Loader2, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Compliance() {
  const { data: documentsRaw } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });
  const documents = (Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || []).filter(
    (d: any) => d.status === 'completed'
  );

  const [results, setResults] = useState<any[]>([]);
  const [running, setRunning] = useState<number | null>(null);

  const runAudit = async (docId: number) => {
    setRunning(docId);
    try {
      const res = await authenticatedFetch('/compliance/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: docId }),
      });
      const data = await res.json();
      setResults((prev) => [...prev.filter((r) => r.document_id !== docId), { document_id: docId, ...data }]);
    } catch {
      // audit error
    }
    setRunning(null);
  };

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Compliance</h2>

      {documents.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <ShieldCheck size={24} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No documents to audit</h3>
          <p className="text-sm text-on-surface-variant max-w-md mb-6">
            Upload and process documents first. Compliance checks run against processed documents.
          </p>
          <Link to="/documents" className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors flex items-center gap-2">
            <Upload size={14} /> Upload Documents
          </Link>
        </Card>
      ) : (
        <>
          {/* Documents available for audit */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Select a document to audit</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Document</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="w-24">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc: any) => (
                    <TableRow key={doc.id}>
                      <TableCell className="text-sm font-medium">{doc.filename}</TableCell>
                      <TableCell><Badge variant="outline">{doc.file_type}</Badge></TableCell>
                      <TableCell>
                        <button
                          onClick={() => runAudit(doc.id)}
                          disabled={running === doc.id}
                          className="flex items-center gap-1.5 text-xs text-primary hover:underline disabled:opacity-50"
                        >
                          {running === doc.id ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                          {running === doc.id ? 'Running...' : 'Run Audit'}
                        </button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Audit results */}
          {results.length > 0 && (
            <div className="space-y-4">
              {results.map((r, i) => {
                const docName = documents.find((d: any) => d.id === r.document_id)?.filename || `Doc ID ${r.document_id}`;
                
                return (
                  <Card key={i} className="border border-outline-variant/50 shadow-md">
                    <CardHeader className="border-b border-outline-variant/20 pb-4">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                          <CardTitle className="text-base font-semibold">{docName}</CardTitle>
                          <p className="text-xs text-on-surface-variant/75 mt-0.5 font-mono">
                            Compliance Audit Report
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-on-surface-variant/70 uppercase tracking-wider">Overall Risk:</span>
                          <Badge
                            variant={
                              r.overall_risk === 'High' || r.overall_risk === 'Critical' ? 'danger'
                                : r.overall_risk === 'Medium' ? 'warning'
                                : 'success'
                            }
                          >
                            {r.overall_risk || 'Low'}
                          </Badge>
                        </div>
                      </div>
                    </CardHeader>
                    
                    <CardContent className="pt-5 space-y-5">
                      {/* Summary Metrics Row */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div className="p-3.5 rounded-lg bg-surface-container border border-outline-variant/20">
                          <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/60 mb-1">Compliance Score</p>
                          <div className="flex items-center gap-3">
                            <span className="text-2xl font-bold font-mono text-primary">{r.compliance_score ?? 100}%</span>
                            <div className="flex-1 h-2 rounded-full bg-surface-container-highest overflow-hidden">
                              <div 
                                className="h-full bg-primary rounded-full transition-all duration-500" 
                                style={{ width: `${r.compliance_score ?? 100}%` }}
                              />
                            </div>
                          </div>
                        </div>
                        
                        <div className="p-3.5 rounded-lg bg-surface-container border border-outline-variant/20">
                          <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/60 mb-1">Compliant Items</p>
                          <span className="text-2xl font-bold font-mono text-[#1de9b6]">{r.compliant_count ?? 0}</span>
                        </div>
                        
                        <div className="p-3.5 rounded-lg bg-surface-container border border-outline-variant/20">
                          <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/60 mb-1">Gaps Detected</p>
                          <span className="text-2xl font-bold font-mono text-error">{r.gap_count ?? 0}</span>
                        </div>
                      </div>

                      {/* Gaps Checklist */}
                      <div>
                        <h4 className="text-sm font-semibold tracking-tight text-on-surface mb-3 flex items-center gap-2">
                          <span>Audit Checklist Details</span>
                          <span className="text-xs font-normal font-mono text-on-surface-variant">({(r.gaps || []).length} items)</span>
                        </h4>
                        
                        {(!r.gaps || r.gaps.length === 0) ? (
                          <div className="flex items-center gap-3 p-4 bg-[#004d40]/10 border border-[#004d40]/30 rounded-lg text-sm text-[#1de9b6]">
                            <div className="w-5.5 h-5.5 rounded-full bg-[#004d40]/40 flex items-center justify-center shrink-0">✓</div>
                            <div>
                              <p className="font-semibold">Perfect Compliance</p>
                              <p className="text-xs text-on-surface-variant/80 mt-0.5">All checked clauses meet current industrial standards and regulations.</p>
                            </div>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {r.gaps.map((gap: any, gi: number) => {
                              const borderCol = 
                                gap.risk_level === 'High' || gap.risk_level === 'Critical' ? 'border-l-error' 
                                  : gap.risk_level === 'Medium' ? 'border-l-warning' 
                                  : 'border-l-on-surface-variant/50';
                                  
                              return (
                                <div 
                                  key={gi} 
                                  className={`p-4 bg-surface-container border border-outline-variant/20 border-l-4 ${borderCol} rounded-r-lg space-y-2`}
                                >
                                  <div className="flex items-center justify-between gap-4">
                                    <span className="text-xs font-bold text-primary font-mono uppercase tracking-wider">{gap.regulation}</span>
                                    <Badge 
                                      variant={
                                        gap.risk_level === 'High' || gap.risk_level === 'Critical' ? 'danger' 
                                          : gap.risk_level === 'Medium' ? 'warning' 
                                          : 'default'
                                      }
                                      className="text-[9px] px-1.5"
                                    >
                                      {gap.risk_level}
                                    </Badge>
                                  </div>
                                  
                                  <div>
                                    <p className="text-xs font-semibold text-on-surface font-mono uppercase tracking-wider text-on-surface-variant/70">Requirement</p>
                                    <p className="text-xs text-on-surface mt-0.5 leading-relaxed">{gap.requirement}</p>
                                  </div>
                                  
                                  <div className="pt-1.5 border-t border-outline-variant/10">
                                    <p className="text-xs font-semibold text-error font-mono uppercase tracking-wider">Finding</p>
                                    <p className="text-xs text-on-surface-variant mt-0.5 leading-relaxed">{gap.finding}</p>
                                  </div>
                                  
                                  {gap.recommendation && (
                                    <div className="p-2 bg-primary/5 rounded border border-primary/10 mt-1">
                                      <p className="text-[10px] font-semibold text-primary font-mono uppercase tracking-wider">Recommendation</p>
                                      <p className="text-xs text-on-surface-variant mt-0.5 leading-relaxed">{gap.recommendation}</p>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
