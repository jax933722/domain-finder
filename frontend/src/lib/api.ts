import axios, { AxiosError } from "axios";
import type {
  AdminStats,
  AuthToken,
  Job,
  LogEntry,
  Progress,
  ResultsPage,
  UploadResult,
  User,
} from "@/types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const TOKEN_KEY = "df_access_token";
const REFRESH_KEY = "df_refresh_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(TOKEN_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Transparent refresh on 401, retried once.
let refreshing: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;
  try {
    const { data } = await axios.post<AuthToken>(`${BASE_URL}/auth/refresh`, {
      refresh_token: refresh,
    });
    tokenStore.set(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    tokenStore.clear();
    return null;
  }
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as typeof error.config & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshing = refreshing || refreshAccessToken();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

/** Extract a human-readable message from an API error. */
export function apiError(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    return err.message;
  }
  return err instanceof Error ? err.message : "Unexpected error";
}

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
export const authApi = {
  async signup(email: string, password: string, full_name?: string) {
    const { data } = await api.post<AuthToken>("/auth/signup", {
      email,
      password,
      full_name,
    });
    return data;
  },
  async login(email: string, password: string) {
    // OAuth2 password flow expects form-encoded username/password.
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const { data } = await api.post<AuthToken>("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },
  async me() {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },
  async forgotPassword(email: string) {
    const { data } = await api.post<{ message: string; reset_token: string | null }>(
      "/auth/forgot-password",
      { email },
    );
    return data;
  },
  async resetPassword(token: string, new_password: string) {
    const { data } = await api.post<User>("/auth/reset-password", {
      token,
      new_password,
    });
    return data;
  },
};

// --------------------------------------------------------------------------- //
// Uploads & jobs
// --------------------------------------------------------------------------- //
export const jobApi = {
  async upload(file: File, onProgress?: (pct: number) => void) {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<UploadResult>("/uploads", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return data;
  },
  async process(upload_id: string, company_column: string) {
    const { data } = await api.post<Job>("/jobs/process", {
      upload_id,
      company_column,
    });
    return data;
  },
  async progress(jobId: string) {
    const { data } = await api.get<Progress>(`/jobs/${jobId}/progress`);
    return data;
  },
  async results(jobId: string, offset = 0, limit = 50) {
    const { data } = await api.get<ResultsPage>(`/jobs/${jobId}/results`, {
      params: { offset, limit },
    });
    return data;
  },
  async logs(jobId: string, offset = 0) {
    const { data } = await api.get<LogEntry[]>(`/jobs/${jobId}/logs`, {
      params: { offset },
    });
    return data;
  },
  async list() {
    const { data } = await api.get<Job[]>("/jobs");
    return data;
  },
  downloadUrl(jobId: string, fmt: "xlsx" | "csv") {
    return `${BASE_URL}/jobs/${jobId}/download?fmt=${fmt}`;
  },
  async download(jobId: string, fmt: "xlsx" | "csv") {
    const { data } = await api.get(`/jobs/${jobId}/download`, {
      params: { fmt },
      responseType: "blob",
    });
    return data as Blob;
  },
};

// --------------------------------------------------------------------------- //
// Admin
// --------------------------------------------------------------------------- //
export const adminApi = {
  async stats() {
    const { data } = await api.get<AdminStats>("/admin/stats");
    return data;
  },
  async jobs() {
    const { data } = await api.get<Job[]>("/admin/jobs");
    return data;
  },
  async users() {
    const { data } = await api.get<User[]>("/admin/users");
    return data;
  },
  async toggleUser(userId: string) {
    const { data } = await api.patch<User>(`/admin/users/${userId}/toggle-active`);
    return data;
  },
};
