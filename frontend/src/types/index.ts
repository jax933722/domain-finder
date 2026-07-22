export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: "user" | "admin";
  is_active: boolean;
  created_at: string;
}

export interface AuthToken {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface UploadResult {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  row_count: number;
  columns: string[];
  preview: Record<string, string>[];
  created_at: string;
}

export type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  upload_id: string;
  company_column: string;
  status: JobStatus;
  total_rows: number;
  processed_rows: number;
  found_count: number;
  not_found_count: number;
  cache_hits: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Progress {
  job_id: string;
  status: JobStatus;
  total_rows: number;
  processed_rows: number;
  found_count: number;
  not_found_count: number;
  cache_hits: number;
  percent: number;
  error?: string | null;
}

export interface CompanyResult {
  row_index: number;
  original_company: string;
  clean_company: string;
  official_domain: string | null;
  verification_status: "VERIFIED" | "NOT FOUND" | "ERROR";
  confidence: number;
  source_used: string | null;
  search_url: string | null;
  search_query: string | null;
  reason: string | null;
  processing_time_ms: number;
  from_cache: boolean;
}

export interface ResultsPage {
  job: Job;
  total: number;
  offset: number;
  limit: number;
  items: CompanyResult[];
}

export interface LogEntry {
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  message: string;
  context: Record<string, unknown>;
  timestamp: string | null;
}

export interface AdminStats {
  total_users: number;
  total_jobs: number;
  total_uploads: number;
  total_companies_processed: number;
  total_found: number;
  total_not_found: number;
  average_processing_time_ms: number;
  cache: {
    cached_domains: number;
    keyspace_hits: number;
    keyspace_misses: number;
    hit_rate: number;
  };
  top_companies: { company: string; count: number }[];
  failed_lookups: { company: string; reason: string | null }[];
}
