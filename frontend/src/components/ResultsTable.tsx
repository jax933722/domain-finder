import { useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight, Download, ExternalLink, Search } from "lucide-react";
import { jobApi, apiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { VerificationBadge } from "@/components/StatusBadge";
import type { CompanyResult } from "@/types";

const PAGE_SIZE = 25;
const columnHelper = createColumnHelper<CompanyResult>();

export function ResultsTable({ jobId, live }: { jobId: string; live: boolean }) {
  const { toast } = useToast();
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["results", jobId, page],
    queryFn: () => jobApi.results(jobId, page * PAGE_SIZE, PAGE_SIZE),
    refetchInterval: live ? 2500 : false,
    placeholderData: keepPreviousData,
  });

  const rows = useMemo(() => {
    const items = data?.items ?? [];
    if (!filter.trim()) return items;
    const q = filter.toLowerCase();
    return items.filter(
      (r) =>
        r.original_company.toLowerCase().includes(q) ||
        r.clean_company.toLowerCase().includes(q) ||
        (r.official_domain ?? "").toLowerCase().includes(q),
    );
  }, [data, filter]);

  const columns = useMemo(
    () => [
      columnHelper.accessor("original_company", {
        header: "Original",
        cell: (info) => <span className="max-w-[200px] truncate">{info.getValue()}</span>,
      }),
      columnHelper.accessor("clean_company", {
        header: "Clean Name",
        cell: (info) => <span className="font-medium">{info.getValue() || "—"}</span>,
      }),
      columnHelper.accessor("official_domain", {
        header: "Official Domain",
        cell: (info) => {
          const domain = info.getValue();
          if (!domain) return <span className="text-muted-foreground">NOT FOUND</span>;
          return (
            <a
              href={`https://${domain}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
            >
              {domain}
              <ExternalLink className="h-3 w-3" />
            </a>
          );
        },
      }),
      columnHelper.accessor("verification_status", {
        header: "Status",
        cell: (info) => <VerificationBadge status={info.getValue()} />,
      }),
      columnHelper.accessor("confidence", {
        header: "Confidence",
        cell: (info) => {
          const v = info.getValue();
          return (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${Math.round(v * 100)}%` }}
                />
              </div>
              <span className="text-xs tabular-nums">{(v * 100).toFixed(0)}%</span>
            </div>
          );
        },
      }),
      columnHelper.accessor("source_used", {
        header: "Source",
        cell: (info) => <span className="text-xs text-muted-foreground">{info.getValue() || "—"}</span>,
      }),
      columnHelper.accessor("processing_time_ms", {
        header: "Time",
        cell: (info) => <span className="text-xs tabular-nums">{info.getValue()} ms</span>,
      }),
      columnHelper.display({
        id: "details",
        header: "Details",
        cell: (info) => {
          const r = info.row.original;
          const detail = r.reason ?? r.search_query ?? "";
          return (
            <span className="block max-w-[240px] truncate text-xs text-muted-foreground" title={detail}>
              {r.from_cache ? "⚡ cached · " : ""}
              {detail}
            </span>
          );
        },
      }),
    ],
    [],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleDownload = async (fmt: "xlsx" | "csv") => {
    try {
      const blob = await jobApi.download(jobId, fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `enriched_${jobId}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast(apiError(err), "error");
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle>Results {total > 0 && <span className="text-muted-foreground">({total.toLocaleString()})</span>}</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Filter this page…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-9 w-48 pl-8"
            />
          </div>
          <Button variant="outline" size="sm" onClick={() => handleDownload("csv")} disabled={live}>
            <Download className="h-4 w-4" /> CSV
          </Button>
          <Button size="sm" onClick={() => handleDownload("xlsx")} disabled={live}>
            <Download className="h-4 w-4" /> Excel
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((header) => (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={columns.length} className="py-10 text-center text-muted-foreground">
                    Loading…
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columns.length} className="py-10 text-center text-muted-foreground">
                    No results yet.
                  </TableCell>
                </TableRow>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="h-4 w-4" /> Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
