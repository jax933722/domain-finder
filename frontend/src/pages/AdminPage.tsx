import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Database,
  Search,
  Users as UsersIcon,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { adminApi, apiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate } from "@/lib/utils";

export function AdminPage() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data: stats } = useQuery({ queryKey: ["admin-stats"], queryFn: adminApi.stats });
  const { data: users = [] } = useQuery({ queryKey: ["admin-users"], queryFn: adminApi.users });
  const { data: jobs = [] } = useQuery({ queryKey: ["admin-jobs"], queryFn: adminApi.jobs });

  const toggle = useMutation({
    mutationFn: (userId: string) => adminApi.toggleUser(userId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast("User updated", "success");
    },
    onError: (err) => toast(apiError(err), "error"),
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin Dashboard</h1>
        <p className="mt-1 text-muted-foreground">Platform-wide statistics and management.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Users" value={stats?.total_users ?? 0} icon={<UsersIcon className="h-6 w-6" />} />
        <StatCard label="Jobs" value={stats?.total_jobs ?? 0} icon={<Activity className="h-6 w-6" />} />
        <StatCard
          label="Rows Processed"
          value={(stats?.total_companies_processed ?? 0).toLocaleString()}
          icon={<Search className="h-6 w-6" />}
        />
        <StatCard
          label="Avg Time"
          value={`${Math.round(stats?.average_processing_time_ms ?? 0)} ms`}
          accent="muted"
          icon={<Activity className="h-6 w-6" />}
        />
        <StatCard
          label="Verified"
          value={(stats?.total_found ?? 0).toLocaleString()}
          accent="success"
          icon={<CheckCircle2 className="h-6 w-6" />}
        />
        <StatCard
          label="Not Found"
          value={(stats?.total_not_found ?? 0).toLocaleString()}
          accent="muted"
          icon={<XCircle className="h-6 w-6" />}
        />
        <StatCard
          label="Cached Domains"
          value={(stats?.cache.cached_domains ?? 0).toLocaleString()}
          accent="primary"
          icon={<Database className="h-6 w-6" />}
        />
        <StatCard
          label="Cache Hit Rate"
          value={`${Math.round((stats?.cache.hit_rate ?? 0) * 100)}%`}
          accent="primary"
          icon={<Database className="h-6 w-6" />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top searched companies</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.top_companies.length ? (
              <ul className="space-y-2">
                {stats.top_companies.map((c) => (
                  <li key={c.company} className="flex items-center justify-between text-sm">
                    <span className="truncate">{c.company || "(empty)"}</span>
                    <Badge variant="secondary">{c.count}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent failed lookups</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.failed_lookups.length ? (
              <ul className="space-y-2">
                {stats.failed_lookups.map((f, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium">{f.company || "(empty)"}</span>
                    <span className="block truncate text-xs text-muted-foreground">{f.reason}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No failed lookups.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Users</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Joined</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">{u.email}</TableCell>
                    <TableCell>
                      <Badge variant={u.role === "admin" ? "default" : "secondary"}>{u.role}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.is_active ? "success" : "destructive"}>
                        {u.is_active ? "Active" : "Disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(u.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggle.mutate(u.id)}
                        disabled={toggle.isPending}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All jobs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Found</TableHead>
                  <TableHead>Not Found</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell className="font-mono text-xs">{j.id.slice(0, 8)}</TableCell>
                    <TableCell>{j.status}</TableCell>
                    <TableCell>{j.total_rows}</TableCell>
                    <TableCell className="text-success">{j.found_count}</TableCell>
                    <TableCell className="text-muted-foreground">{j.not_found_count}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(j.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
