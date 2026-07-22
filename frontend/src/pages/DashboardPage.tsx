import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Database, RotateCcw, Search, XCircle } from "lucide-react";
import { jobApi } from "@/lib/api";
import { FileUpload } from "@/components/FileUpload";
import { LogPanel } from "@/components/LogPanel";
import { ResultsTable } from "@/components/ResultsTable";
import { StatCard } from "@/components/StatCard";
import { JobStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export function DashboardPage() {
  const [jobId, setJobId] = useState<string | null>(null);

  const { data: progress } = useQuery({
    queryKey: ["progress", jobId],
    queryFn: () => jobApi.progress(jobId as string),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1200;
    },
  });

  const live = useMemo(
    () => !!progress && progress.status !== "completed" && progress.status !== "failed",
    [progress],
  );

  if (!jobId) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Company Domain Enrichment</h1>
          <p className="mt-2 text-muted-foreground">
            Upload a spreadsheet, and we&apos;ll clean each company name and find its verified
            official domain from trusted sources. Domains are never guessed — unverifiable
            companies are reported as <span className="font-medium">NOT FOUND</span>.
          </p>
        </div>
        <FileUpload onStarted={setJobId} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Processing</h1>
          {progress && <JobStatusBadge status={progress.status} />}
        </div>
        <Button variant="outline" onClick={() => setJobId(null)}>
          <RotateCcw className="h-4 w-4" /> New file
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {progress?.status === "completed"
              ? "Completed"
              : progress?.status === "failed"
                ? "Failed"
                : "Processing rows…"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Progress
            value={progress?.percent ?? 0}
            indicatorClassName={
              progress?.status === "failed"
                ? "bg-destructive"
                : progress?.status === "completed"
                  ? "bg-success"
                  : undefined
            }
          />
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {progress?.processed_rows ?? 0} / {progress?.total_rows ?? 0} rows
            </span>
            <span className="tabular-nums">{(progress?.percent ?? 0).toFixed(1)}%</span>
          </div>
          {progress?.error && (
            <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{progress.error}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Verified"
          value={progress?.found_count ?? 0}
          accent="success"
          icon={<CheckCircle2 className="h-6 w-6" />}
        />
        <StatCard
          label="Not Found"
          value={progress?.not_found_count ?? 0}
          accent="muted"
          icon={<XCircle className="h-6 w-6" />}
        />
        <StatCard
          label="Cache Hits"
          value={progress?.cache_hits ?? 0}
          accent="primary"
          icon={<Database className="h-6 w-6" />}
        />
        <StatCard
          label="Total Rows"
          value={progress?.total_rows ?? 0}
          accent="primary"
          icon={<Search className="h-6 w-6" />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ResultsTable jobId={jobId} live={live} />
        </div>
        <div>
          <LogPanel jobId={jobId} live={live} />
        </div>
      </div>
    </div>
  );
}
