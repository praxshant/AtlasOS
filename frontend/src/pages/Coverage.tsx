import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Coverage() {
  const { data: gapsData, isLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => getJson<any>('/knowledge/gaps'),
  });

  const gaps = gapsData?.gaps || [];
  const totalEquipment = gapsData?.total_equipment || 0;

  if (isLoading) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold tracking-tight">Knowledge Coverage</h2>
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  const covered = gaps.filter((g: any) => g.coverage_score >= 50).length;
  const critical = gaps.filter((g: any) => g.risk_level === 'Critical').length;

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Knowledge Coverage</h2>

      {totalEquipment === 0 ? (
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <Upload size={24} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No assets found</h3>
          <p className="text-sm text-on-surface-variant max-w-md mb-6">
            Upload industrial documents to extract assets and compute knowledge coverage scores.
          </p>
          <Link to="/documents" className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors">
            Upload Documents
          </Link>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3">
            <KPISmall label="Total Assets" value={totalEquipment} />
            <KPISmall label="Covered" value={covered} color="success" />
            <KPISmall label="Critical Risk" value={critical} color="danger" />
          </div>

          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Asset</TableHead>
                    <TableHead>Risk Level</TableHead>
                    <TableHead>Risk Score</TableHead>
                    <TableHead>Coverage</TableHead>
                    <TableHead>SOP</TableHead>
                    <TableHead>Maintenance</TableHead>
                    <TableHead>Expert</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {gaps.map((gap: any, i: number) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium text-sm">{gap.asset || gap.equipment}</TableCell>
                      <TableCell>
                        <Badge variant={gap.risk_level === 'Critical' ? 'danger' : gap.risk_level === 'High' ? 'warning' : 'default'}>
                          {gap.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">{(gap.risk_score || 0).toFixed(2)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-surface-variant rounded-full h-1">
                            <div className="bg-primary h-1 rounded-full" style={{ width: `${gap.coverage_score || 0}%` }} />
                          </div>
                          <span className="text-[10px] font-mono text-on-surface-variant">{gap.coverage_score || 0}%</span>
                        </div>
                      </TableCell>
                      <TableCell><StatusDot ok={gap.has_sop} /></TableCell>
                      <TableCell><StatusDot ok={gap.has_maintenance} /></TableCell>
                      <TableCell><StatusDot ok={gap.has_expert} /></TableCell>
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

function StatusDot({ ok }: { ok: boolean }) {
  return <div className={`w-2 h-2 rounded-full mx-auto ${ok ? 'bg-success' : 'bg-error/50'}`} />;
}

function KPISmall({ label, value, color }: { label: string; value: number; color?: 'success' | 'danger' }) {
  const textColor = color === 'success' ? 'text-success' : color === 'danger' ? 'text-error' : 'text-on-surface';
  return (
    <Card className="p-3">
      <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/70 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${textColor}`}>{value}</p>
    </Card>
  );
}
