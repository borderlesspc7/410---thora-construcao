import { apiClient } from "./api";

export type AbcJobStatus =
  | "uploading"
  | "detecting"
  | "awaiting_selection"
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "not_found";

export type AbcAnalysisJob = {
  upload_id: string;
  user_id?: string;
  filename: string;
  status: AbcJobStatus;
  message?: string;
  queue_position?: number;
  tables_found?: number;
  items_found?: number;
  table_ids?: string[];
  pages_total?: number;
  pages_done?: number;
  error?: string;
  result?: Record<string, unknown>;
  created_at?: string;
  completed_at?: string | null;
  updated_at?: string;
};

const parseApiError = (error: unknown, fallback: string): string => {
  const err = error as { response?: { data?: { detail?: unknown } } };
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d?.msg).join("; ") || fallback;
  }
  return fallback;
};

async function registerAbcJobsIndividually(
  jobs: { uploadId: string; filename: string }[],
): Promise<AbcAnalysisJob[]> {
  const registered: AbcAnalysisJob[] = [];
  for (const job of jobs) {
    const response = await apiClient.patch(`/api/abc-analysis/${job.uploadId}`, {
      status: "uploading",
      message: "Arquivo recebido — aguardando detecção de tabelas…",
    });
    const saved = (response.data as { job?: AbcAnalysisJob }).job;
    registered.push(
      saved ?? {
        upload_id: job.uploadId,
        filename: job.filename,
        status: "uploading",
        message: "Arquivo recebido — aguardando detecção de tabelas…",
      },
    );
  }
  return registered;
}

export const registerAbcBatch = async (
  jobs: { uploadId: string; filename: string }[],
): Promise<AbcAnalysisJob[]> => {
  try {
    const response = await apiClient.post("/api/abc-analysis/batch-register", {
      jobs: jobs.map((j) => ({
        upload_id: j.uploadId,
        filename: j.filename,
      })),
    });
    return (response.data as { jobs?: AbcAnalysisJob[] }).jobs ?? [];
  } catch (error: unknown) {
    const status = (error as { response?: { status?: number } }).response?.status;
    if (status === 404 || status === 405) {
      try {
        return await registerAbcJobsIndividually(jobs);
      } catch {
        throw new Error(
          "Endpoints da Lista de análises indisponíveis. Reinicie o backend (porta 8001).",
        );
      }
    }
    throw new Error(parseApiError(error, "Erro ao registrar lote de análises"));
  }
};

export const updateAbcJob = async (
  uploadId: string,
  patch: {
    status?: AbcJobStatus;
    message?: string;
    tables_found?: number;
    error?: string;
  },
): Promise<AbcAnalysisJob> => {
  const response = await apiClient.patch(`/api/abc-analysis/${uploadId}`, patch);
  return (response.data as { job: AbcAnalysisJob }).job;
};

export const enqueueAbcProcess = async (
  uploadId: string,
  tableIds: string[],
): Promise<{ queue_position: number; message: string }> => {
  const response = await apiClient.post("/api/abc-analysis/process", {
    upload_id: uploadId,
    table_ids: tableIds,
  });
  return response.data as { queue_position: number; message: string };
};

export const listAbcJobs = async (): Promise<AbcAnalysisJob[]> => {
  const response = await apiClient.get("/api/abc-analysis/list");
  return (response.data as { jobs?: AbcAnalysisJob[] }).jobs ?? [];
};

export const getAbcBatchStatus = async (
  uploadIds: string[],
): Promise<AbcAnalysisJob[]> => {
  const response = await apiClient.post("/api/abc-analysis/batch-status", {
    upload_ids: uploadIds,
  });
  return (response.data as { jobs?: AbcAnalysisJob[] }).jobs ?? [];
};

export const fetchAbcJobsSafe = async (): Promise<AbcAnalysisJob[]> => {
  try {
    return await listAbcJobs();
  } catch (error: unknown) {
    throw new Error(parseApiError(error, "Erro ao carregar lista de análises"));
  }
};
