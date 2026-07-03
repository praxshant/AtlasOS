import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Skeleton } from '../components/ui/Skeleton';
import { FileText, ArrowUpRight, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: () => getJson<any>('/stats'),
  });

  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => getJson<any>('/system/health'),
  });

  const { data: activity } = useQuery({
    queryKey: ['activity'],
    queryFn: () => getJson<any[]>('/dashboard/activity'),
  });

  const { data: documentsRaw } = useQuery({
    queryKey: ['documents'],
    queryFn: () => getJson<any>('/documents'),
  });

  const documents = Array.isArray(documentsRaw) ? documentsRaw : documentsRaw?.documents || [];
  const loading = statsLoading || healthLoading;

  if (loading) return <DashboardSkeleton />;

  const hasData = (stats?.total_documents || 0) > 0;

  return (
    <div className="space-y-5">
      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        <KPI label="Documents" value={stats?.total_documents ?? 0} />
        <KPI label="Chunks" value={stats?.total_chunks ?? 0} />
        <KPI label="Assets" value={stats?.total_assets ?? 0} />
        <KPI label="Coverage" value={`${stats?.knowledge_coverage_avg ?? 0}%`} color="primary" />
        <KPI label="Graph Nodes" value={stats?.graph_nodes ?? 0} />
        <KPI label="Graph Edges" value={stats?.graph_edges ?? 0} />
        <KPI label="Critical Gaps" value={stats?.critical_gaps ?? 0} color="danger" />
        <KPI label="Engineers at Risk" value={stats?.engineers_at_risk ?? 0} color="warning" />
      </div>

      {/* Main content */}
      {!hasData ? (
        <EmptyDashboard />
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Recent documents */}
            <Card className="lg:col-span-2">
              <CardHeader className="flex flex-row items-center justify-between pb-3">
                <CardTitle className="text-sm">Recent Documents</CardTitle>
                <Link to="/documents" className="text-xs text-primary hover:underline flex items-center gap-1">
                  View all <ArrowUpRight size={12} />
                </Link>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.slice(0, 6).map((doc: any) => (
                      <TableRow key={doc.id}>
                        <TableCell className="font-medium text-sm flex items-center gap-2">
                          <FileText size={13} className="text-on-surface-variant shrink-0" />
                          <span className="truncate max-w-[200px]">{doc.filename}</span>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{doc.file_type}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              doc.status === 'completed' ? 'success' : doc.status === 'failed' ? 'danger' : 'warning'
                            }
                          >
                            {doc.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Activity + Health */}
            <div className="space-y-5">
              {/* System health */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">System Health</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 pt-0">
                  <HealthRow
                    label="PostgreSQL"
                    status={health?.postgresql?.status}
                    detail={`${health?.postgresql?.documents ?? 0} docs`}
                  />
                  <HealthRow
                    label="Neo4j"
                    status={health?.neo4j?.status}
                    detail={`${health?.neo4j?.nodes ?? 0} nodes · ${health?.neo4j?.edges ?? 0} edges`}
                  />
                  <HealthRow
                    label="Qdrant"
                    status={health?.qdrant?.status}
                    detail={`${health?.qdrant?.vectors ?? 0} vectors`}
                  />
                  <HealthRow label="Redis" status={health?.redis?.status} detail="queue" />
                </CardContent>
              </Card>

              {/* Activity feed */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">Activity</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 pt-0 max-h-[220px] overflow-y-auto">
                  {activity && activity.length > 0 ? (
                    activity.slice(0, 8).map((evt: any) => (
                      <div
                        key={evt.id}
                        className="flex items-start gap-2 py-1.5 border-b border-outline-variant/20 last:border-0"
                      >
                        <div
                          className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${evt.severity === 'warning' ? 'bg-warning' : 'bg-primary'}`}
                        />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-on-surface truncate">{evt.title}</p>
                          <p className="text-[10px] text-on-surface-variant truncate">{evt.detail}</p>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-on-surface-variant text-center py-4">No activity yet.</p>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function EmptyDashboard() {
  return (
    <Card className="flex flex-col items-center justify-center py-16 px-8 text-center">
      <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
        <Upload size={24} className="text-primary" />
      </div>
      <h3 className="text-lg font-semibold mb-2">Upload your first document</h3>
      <p className="text-sm text-on-surface-variant max-w-md mb-6">
        AtlasOS transforms industrial documents into an intelligent knowledge graph. Upload an SOP, maintenance manual,
        or inspection report to get started.
      </p>
      <Link
        to="/documents"
        className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        Go to Documents
      </Link>
    </Card>
  );
}

function KPI({ label, value, color }: { label: string; value: string | number; color?: 'primary' | 'danger' | 'warning' }) {
  const textColor = color === 'primary' ? 'text-primary' : color === 'danger' ? 'text-error' : color === 'warning' ? 'text-warning' : 'text-on-surface';
  return (
    <div className="p-3 rounded-lg border border-outline-variant/30 bg-surface-container-low">
      <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/70 mb-1">{label}</p>
      <p className={`text-xl font-semibold tracking-tight ${textColor}`}>{value}</p>
    </div>
  );
}

function HealthRow({ label, status, detail }: { label: string; status?: string; detail: string }) {
  const ok = status === 'ok';
  return (
    <div className="flex items-center justify-between py-1 border-b border-outline-variant/20 last:border-0">
      <div className="flex items-center gap-2">
        <div className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-success' : 'bg-error'}`} />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <span className="text-[10px] font-mono text-on-surface-variant">{detail}</span>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        {[...Array(8)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Skeleton className="h-[300px] lg:col-span-2 w-full" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    </div>
  );
}
