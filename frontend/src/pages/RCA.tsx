import { useState } from 'react';
import { authenticatedFetch } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { GitBranch, Loader2, Play } from 'lucide-react';

export function RCA() {
  const [input, setInput] = useState('');
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runRCA = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await authenticatedFetch('/rca/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_description: input }),
      });
      const data = await res.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message || 'RCA analysis failed');
    }
    setLoading(false);
  };

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Root Cause Analysis</h2>

      {/* Input */}
      <Card>
        <CardContent className="p-4">
          <label className="block text-xs font-mono text-on-surface-variant uppercase tracking-wider mb-2">
            Incident Description
          </label>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Describe the incident, e.g. 'Main turbine C-17 tripped due to overspeed during startup sequence'"
            className="w-full h-24 bg-surface-container border border-outline-variant/50 rounded-lg p-3 text-sm text-on-surface resize-none focus:outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
          />
          <div className="flex justify-end mt-3">
            <button
              onClick={runRCA}
              disabled={!input.trim() || loading}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {loading ? 'Analyzing...' : 'Run Analysis'}
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-error/30 bg-error/5 p-4">
          <p className="text-sm text-error">{error}</p>
        </Card>
      )}

      {/* Results */}
      {report && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2">
              <GitBranch size={16} className="text-primary" />
              Analysis Report
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {/* Render fault tree if available */}
            {(() => {
              const faultTree = typeof report.fault_tree === 'string' ? JSON.parse(report.fault_tree) : report.fault_tree;
              if (!faultTree) return null;
              return (
                <div className="mb-4">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant mb-2">Fault Tree</p>
                  <FaultNode node={faultTree} depth={0} />
                </div>
              );
            })()}

            {/* Render why chain if available */}
            {(() => {
              let whyChain = report.why_chain;
              try {
                if (typeof whyChain === 'string') whyChain = JSON.parse(whyChain);
              } catch {
                whyChain = null;
              }
              if (!whyChain || !Array.isArray(whyChain) || whyChain.length === 0) return null;
              
              return (
                <div className="mb-4">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant mb-2">5-Whys Chain</p>
                  <div className="space-y-2">
                    {whyChain.map((why: any, i: number) => {
                      const text = typeof why === 'string' ? why : why.description || JSON.stringify(why);
                      const prefixMatch = text.match(/^why\s*\d*\s*[:-]?\s*(.*)/i);
                      const cleanText = prefixMatch ? prefixMatch[1] : text;
                      return (
                        <div key={i} className="flex items-start gap-3">
                          <div className="w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center shrink-0 text-[10px] font-bold text-primary">
                            {i + 1}
                          </div>
                          <p className="text-sm text-on-surface pt-0.5">{cleanText}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}

            {/* Raw output fallback */}
            {!report.fault_tree && !report.why_chain && (
              <pre className="text-xs font-mono text-on-surface-variant whitespace-pre-wrap overflow-auto max-h-[400px] bg-surface-container p-3 rounded-lg">
                {JSON.stringify(report, null, 2)}
              </pre>
            )}

            {/* Recommendations */}
            {(() => {
              let recs = report.recommendations;
              try {
                if (typeof recs === 'string') recs = JSON.parse(recs);
              } catch {
                recs = null;
              }
              if (!recs || !Array.isArray(recs) || recs.length === 0) return null;
              
              return (
                <div className="mt-4 pt-4 border-t border-outline-variant/30">
                  <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant mb-2">Recommendations</p>
                  <ul className="space-y-1.5">
                    {recs.map((rec: string, i: number) => (
                      <li key={i} className="text-sm text-on-surface flex items-start gap-2">
                        <span className="text-primary mt-0.5">•</span>
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })()}
          </CardContent>
        </Card>
      )}

      {/* Empty state when nothing yet */}
      {!report && !loading && !error && (
        <Card className="flex flex-col items-center justify-center py-12 text-center">
          <GitBranch size={32} className="text-primary/30 mb-3" />
          <p className="text-sm text-on-surface-variant">
            Describe an incident above to generate a root cause analysis using your knowledge graph.
          </p>
        </Card>
      )}
    </div>
  );
}

function FaultNode({ node, depth }: { node: any; depth: number }) {
  if (!node) return null;
  const label = node.event || node.description || node.name || JSON.stringify(node);
  const children = node.children || node.causes || [];

  return (
    <div className={`${depth > 0 ? 'ml-6 border-l border-outline-variant/30 pl-3' : ''}`}>
      <div className="py-1">
        <Badge variant={depth === 0 ? 'danger' : children.length === 0 ? 'info' : 'outline'} className="text-xs">
          {label}
        </Badge>
      </div>
      {children.map((child: any, i: number) => (
        <FaultNode key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}
