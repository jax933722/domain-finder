import { useCallback, useRef, useState, type DragEvent } from "react";
import { FileSpreadsheet, Loader2, UploadCloud, X } from "lucide-react";
import { jobApi, apiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { UploadResult } from "@/types";

interface FileUploadProps {
  onStarted: (jobId: string) => void;
}

export function FileUpload({ onStarted }: FileUploadProps) {
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [column, setColumn] = useState<string>("");
  const [starting, setStarting] = useState(false);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      const valid = /\.(csv|xlsx|xlsm|xls)$/i.test(file.name);
      if (!valid) {
        toast("Please upload a .csv or .xlsx file.", "error");
        return;
      }
      setUploading(true);
      setUploadPct(0);
      try {
        const result = await jobApi.upload(file, setUploadPct);
        setUpload(result);
        // Heuristic default: pick the first column that looks company-related.
        const guess =
          result.columns.find((c) => /company|organi[sz]ation|employer|name/i.test(c)) ??
          result.columns[0];
        setColumn(guess ?? "");
        toast(`Loaded ${result.row_count} rows`, "success");
      } catch (err) {
        toast(apiError(err), "error");
      } finally {
        setUploading(false);
      }
    },
    [toast],
  );

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    void handleFiles(e.dataTransfer.files);
  };

  const start = async () => {
    if (!upload || !column) return;
    setStarting(true);
    try {
      const job = await jobApi.process(upload.id, column);
      onStarted(job.id);
      toast("Processing started", "success");
    } catch (err) {
      toast(apiError(err), "error");
    } finally {
      setStarting(false);
    }
  };

  const reset = () => {
    setUpload(null);
    setColumn("");
    setUploadPct(0);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>1 · Upload your file</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {!upload ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors",
              dragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,.xls"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
            {uploading ? (
              <>
                <Loader2 className="mb-3 h-10 w-10 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">Uploading… {uploadPct}%</p>
              </>
            ) : (
              <>
                <UploadCloud className="mb-3 h-10 w-10 text-muted-foreground" />
                <p className="font-medium">Drag &amp; drop your Excel or CSV file</p>
                <p className="mt-1 text-sm text-muted-foreground">or click to browse (.xlsx, .csv)</p>
              </>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between rounded-lg border bg-muted/40 p-3">
              <div className="flex items-center gap-3">
                <FileSpreadsheet className="h-6 w-6 text-primary" />
                <div>
                  <p className="font-medium">{upload.filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {upload.row_count.toLocaleString()} rows · {upload.columns.length} columns
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={reset} aria-label="Remove file">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-2">
              <Label htmlFor="column">2 · Which column holds the company?</Label>
              <Select id="column" value={column} onChange={(e) => setColumn(e.target.value)}>
                {upload.columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <Label className="mb-2 block">Preview</Label>
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {upload.columns.map((c) => (
                        <TableHead key={c} className={cn(c === column && "text-primary")}>
                          {c}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {upload.preview.slice(0, 8).map((row, i) => (
                      <TableRow key={i}>
                        {upload.columns.map((c) => (
                          <TableCell
                            key={c}
                            className={cn(
                              "max-w-[220px] truncate",
                              c === column && "font-medium text-primary",
                            )}
                          >
                            {row[c] ?? ""}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <Button onClick={start} disabled={!column || starting} size="lg" className="w-full">
              {starting && <Loader2 className="h-4 w-4 animate-spin" />}
              3 · Start Processing
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
