import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  accent?: "primary" | "success" | "destructive" | "muted";
}) {
  const accentClass = {
    primary: "text-primary",
    success: "text-success",
    destructive: "text-destructive",
    muted: "text-muted-foreground",
  }[accent ?? "primary"];

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className={cn("mt-1 text-2xl font-bold", accentClass)}>{value}</p>
        </div>
        {icon && <div className={cn("opacity-70", accentClass)}>{icon}</div>}
      </CardContent>
    </Card>
  );
}
