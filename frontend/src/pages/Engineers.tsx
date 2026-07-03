import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Card, CardContent } from '../components/ui/Card';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { Users, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Engineers() {
  const { data, isLoading } = useQuery({
    queryKey: ['engineers'],
    queryFn: () => getJson<any>('/engineers'),
  });

  const engineers = data?.engineers || [];
  const summary = data?.summary || {};

  if (isLoading) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold tracking-tight">Engineers</h2>
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Engineers</h2>

      {engineers.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <Users size={24} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No engineers found</h3>
          <p className="text-sm text-on-surface-variant max-w-md mb-6">
            Engineer data is extracted from uploaded documents. Upload inspection reports or maintenance logs that mention personnel.
          </p>
          <Link to="/documents" className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors flex items-center gap-2">
            <Upload size={14} /> Upload Documents
          </Link>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPISmall label="Mapped" value={summary.total_engineers || 0} />
            <KPISmall label="High Risk" value={summary.high_risk_count || 0} color="danger" />
            <KPISmall label="Avg Expertise" value={summary.avg_expertise_score || 0} />
            <KPISmall label="Unprotected Assets" value={summary.critical_assets_unprotected || 0} color="warning" />
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Expertise</TableHead>
                    <TableHead>Centrality</TableHead>
                    <TableHead>Succession Risk</TableHead>
                    <TableHead>Assets</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {engineers.map((eng: any, i: number) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium text-sm flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-surface-variant flex items-center justify-center text-[10px] font-bold text-on-surface-variant uppercase border border-outline-variant/30 shrink-0">
                          {(eng.name || '??').substring(0, 2)}
                        </div>
                        {eng.name}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{(eng.expertise_score || 0).toFixed(1)}</TableCell>
                      <TableCell className="font-mono text-xs">{(eng.centrality || 0).toFixed(3)}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            eng.succession_risk === 'Critical' ? 'danger'
                              : eng.succession_risk === 'High' ? 'warning'
                              : 'default'
                          }
                        >
                          {eng.succession_risk || 'Low'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {(eng.assets || []).slice(0, 3).map((a: string, ai: number) => (
                            <Badge key={ai} variant="outline" className="text-[10px]">{a}</Badge>
                          ))}
                          {(eng.assets || []).length > 3 && (
                            <span className="text-[10px] text-on-surface-variant">+{eng.assets.length - 3}</span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function KPISmall({ label, value, color }: { label: string; value: number; color?: 'danger' | 'warning' }) {
  const textColor = color === 'danger' ? 'text-error' : color === 'warning' ? 'text-warning' : 'text-on-surface';
  return (
    <Card className="p-3">
      <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/70 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${textColor}`}>{value}</p>
    </Card>
  );
}
