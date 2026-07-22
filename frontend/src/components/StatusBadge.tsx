import { Badge } from "@/components/ui/badge";
import type { CompanyResult, JobStatus } from "@/types";

export function VerificationBadge({ status }: { status: CompanyResult["verification_status"] }) {
  if (status === "VERIFIED") return <Badge variant="success">Verified</Badge>;
  if (status === "ERROR") return <Badge variant="destructive">Error</Badge>;
  return <Badge variant="secondary">Not Found</Badge>;
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, { label: string; variant: "default" | "success" | "destructive" | "secondary" }> = {
    pending: { label: "Pending", variant: "secondary" },
    running: { label: "Running", variant: "default" },
    completed: { label: "Completed", variant: "success" },
    failed: { label: "Failed", variant: "destructive" },
    cancelled: { label: "Cancelled", variant: "secondary" },
  };
  const cfg = map[status];
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}
