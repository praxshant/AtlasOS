import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Network, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Skeleton } from '../components/ui/Skeleton';

export function KnowledgeGraph() {
  const { data, isLoading } = useQuery({
    queryKey: ['graph-data'],
    queryFn: () => getJson<any>('/graph/data'),
  });

  const nodes = data?.nodes || [];
  const edges = data?.edges || [];
  const isEmpty = nodes.length === 0;

  if (isLoading) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold tracking-tight">Knowledge Graph</h2>
        <Skeleton className="h-[calc(100vh-10rem)] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-5 flex flex-col h-[calc(100vh-6rem)]">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Knowledge Graph</h2>
          <p className="text-zinc-400">Interactive visualization of industrial knowledge</p>
        </div>
        {!isEmpty && (
          <div className="flex gap-2">
            <Badge variant="outline">{nodes.length} nodes</Badge>
            <Badge variant="outline">{edges.length} edges</Badge>
          </div>
        )}
      </div>

      {isEmpty ? (
        <Card className="flex-1 flex flex-col items-center justify-center text-center py-16">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <Network size={24} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No graph data yet</h3>
          <p className="text-sm text-on-surface-variant max-w-md mb-6">
            Upload and process industrial documents to automatically build a knowledge graph of assets, procedures, personnel, and incidents.
          </p>
          <Link
            to="/documents"
            className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors flex items-center gap-2"
          >
            <Upload size={14} /> Upload Documents
          </Link>
        </Card>
      ) : (
        <Card className="flex-1 flex flex-col overflow-hidden">
          <CardContent className="flex-1 p-0 overflow-auto">
            {/* Node list grouped by label */}
            <div className="p-4 space-y-4">
              {Object.entries(groupByLabel(nodes)).map(([label, group]) => (
                <div key={label}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${labelColor(label)}`} />
                    <span className="text-xs font-mono uppercase tracking-wider text-on-surface-variant">
                      {label} ({(group as any[]).length})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {(group as any[]).map((node: any) => (
                      <Badge key={node.id} variant="outline" className="text-xs cursor-pointer hover:bg-surface-variant/30">
                        {node.name}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}

              {edges.length > 0 && (
                <div className="pt-4 border-t border-outline-variant/30">
                  <span className="text-xs font-mono uppercase tracking-wider text-on-surface-variant">
                    Relationships ({edges.length})
                  </span>
                  <div className="mt-2 space-y-1 max-h-[300px] overflow-y-auto">
                    {edges.slice(0, 50).map((e: any, i: number) => (
                      <div key={i} className="text-xs text-on-surface-variant flex items-center gap-1.5 py-0.5">
                        <span className="text-on-surface font-medium">{e.source}</span>
                        <span className="text-primary font-mono">→ {e.type} →</span>
                        <span className="text-on-surface font-medium">{e.target}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function groupByLabel(nodes: any[]) {
  return nodes.reduce((acc: Record<string, any[]>, node) => {
    const label = node.label || 'Entity';
    if (!acc[label]) acc[label] = [];
    acc[label].push(node);
    return acc;
  }, {});
}

function labelColor(label: string): string {
  const map: Record<string, string> = {
    Asset: 'bg-primary',
    Equipment: 'bg-primary',
    Person: 'bg-success',
    Incident: 'bg-error',
    Procedure: 'bg-warning',
    Regulation: 'bg-secondary',
  };
  return map[label] || 'bg-outline';
}
