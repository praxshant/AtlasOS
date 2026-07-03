import { useQuery } from '@tanstack/react-query';
import { getJson } from '../api/client';
import { Card, CardContent } from '../components/ui/Card';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { Skeleton } from '../components/ui/Skeleton';
import { Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

export function Risk() {
  const { data: gapsData, isLoading } = useQuery({
    queryKey: ['gaps'],
    queryFn: () => getJson<any>('/knowledge/gaps'),
  });

  const gaps = gapsData?.gaps || [];
  const totalEquipment = gapsData?.total_equipment || 0;

  if (isLoading) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold tracking-tight">Risk Analytics</h2>
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (totalEquipment === 0) {
    return (
      <div className="space-y-5">
        <h2 className="text-xl font-semibold tracking-tight">Risk Analytics</h2>
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <Upload size={24} className="text-primary" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No risk data available</h3>
          <p className="text-sm text-on-surface-variant max-w-md mb-6">
            Risk scores are computed from your knowledge graph. Upload industrial documents to populate the graph.
          </p>
          <Link to="/documents" className="px-4 py-2 bg-primary text-on-primary rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors">
            Upload Documents
          </Link>
        </Card>
      </div>
    );
  }

  const critical = gaps.filter((g: any) => g.risk_level === 'Critical');
  const high = gaps.filter((g: any) => g.risk_level === 'High');
  const medium = gaps.filter((g: any) => g.risk_level === 'Medium');
  const avgRisk = totalEquipment > 0
    ? (gaps.reduce((sum: number, g: any) => sum + (g.risk_score || 0), 0) / totalEquipment).toFixed(2)
    : '0';

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-semibold tracking-tight">Risk Analytics</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPISmall label="Avg Risk Score" value={avgRisk} />
        <KPISmall label="Critical" value={critical.length} color="danger" />
        <KPISmall label="High" value={high.length} color="warning" />
        <KPISmall label="Medium" value={medium.length} />
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asset</TableHead>
                <TableHead>Risk Level</TableHead>
                <TableHead>Risk Score</TableHead>
                <TableHead>Risk Factors</TableHead>
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
                    <div className="flex flex-wrap gap-1">
                      {(gap.risk_factors || []).slice(0, 3).map((rf: string, ri: number) => (
                        <Badge key={ri} variant="outline" className="text-[10px]">{rf}</Badge>
                      ))}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function KPISmall({ label, value, color }: { label: string; value: string | number; color?: 'danger' | 'warning' }) {
  const textColor = color === 'danger' ? 'text-error' : color === 'warning' ? 'text-warning' : 'text-on-surface';
  return (
    <Card className="p-3">
      <p className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/70 mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${textColor}`}>{value}</p>
    </Card>
  );
}
