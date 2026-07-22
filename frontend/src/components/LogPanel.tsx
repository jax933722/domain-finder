import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { jobApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LogEntry } from "@/types";

const levelColor: Record<LogEntry["level"], string> = {
  DEBUG: "text-muted-foreground",
  INFO: "text-foreground",
  WARNING: "text-amber-500",
  ERROR: "text-destructive",
};

export function LogPanel({ jobId, live }: { jobId: string; live: boolean }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: logs = [] } = useQuery({
    queryKey: ["logs", jobId],
    queryFn: () => jobApi.logs(jobId),
    refetchInterval: live ? 1500 : false,
  });

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className={cn("h-2 w-2 rounded-full", live ? "animate-pulse bg-success" : "bg-muted-foreground")} />
          Live logs
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1">
        <div
          ref={scrollRef}
          className="scroll-thin h-72 overflow-y-auto rounded-lg bg-muted/40 p-3 font-mono text-xs leading-relaxed"
        >
          {logs.length === 0 ? (
            <p className="text-muted-foreground">Waiting for activity…</p>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex gap-2">
                <span className="shrink-0 text-muted-foreground">
                  {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ""}
                </span>
                <span className={cn("shrink-0 font-semibold", levelColor[log.level])}>
                  {log.level}
                </span>
                <span className="break-all">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
