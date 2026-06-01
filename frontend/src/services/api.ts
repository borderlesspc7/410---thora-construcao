import axios from "axios";
import {
  DEFAULT_OUTPUT_MODELS,
  type OutputModelsSelection,
} from "../features/orcamentos/outputModels";
import {
  saveOrcamento,
  getOrcamentoByUploadId,
  getAllOrcamentos,
  ensureAuthToken,
} from "./firebase";

// Detectar URL da API
// Prioridade:
// 1) Em produção no Vercel fullstack: mesma origem
// 2) VITE_API_URL (quando definido)
// 3) Em dev com app servido pelo backend em 8000: mesma origem
// 4) Em dev com Vite: proxy/local backend
// 5) Em produção: mesma origem
const getAPIBase = () => {
  const isLocalhost = ["localhost", "127.0.0.1"].includes(
    window.location.hostname,
  );
  const isVercelHost =
    window.location.hostname.endsWith(".vercel.app") ||
    window.location.hostname === "thora-construcao.vercel.app";
  const isRenderHost = window.location.hostname.endsWith(".onrender.com");

  // Em deploy fullstack, API e frontend ficam no mesmo domínio.
  if (!import.meta.env.DEV && (isVercelHost || isRenderHost)) {
    return window.location.origin;
  }

  if (isLocalhost) {
    return window.location.origin;
  }

  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  if (import.meta.env.DEV) {
    if (window.location.port === "8000") {
      return window.location.origin;
    }

    return "http://localhost:8000";
  } else {
    return window.location.origin;
  }
};

const API_BASE = getAPIBase();

console.info(`🌐 API Base: ${API_BASE}`);

const ANONYMOUS_USER_STORAGE_KEY = "thora_anonymous_user_id";

const getAnonymousUserId = () => {
  const existingUserId = window.localStorage.getItem(ANONYMOUS_USER_STORAGE_KEY);
  if (existingUserId) {
    return existingUserId;
  }

  const generatedUserId =
    "anon-" +
    (window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
  window.localStorage.setItem(ANONYMOUS_USER_STORAGE_KEY, generatedUserId);
  return generatedUserId;
};

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach Firebase ID token to protect backend endpoints.
apiClient.interceptors.request.use(async (config) => {
  config.headers = config.headers ?? {};
  (config.headers as any)["X-Anonymous-User"] = getAnonymousUserId();

  try {
    const token = await ensureAuthToken();
    if (token) {
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
  } catch (error) {
    console.warn("Falha ao obter token Firebase; usando fallback anônimo.", error);
  }

  return config;
});

// ==================== PDF OPERATIONS ====================

// Upload PDF
export const uploadPDF = async (file: File) => {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await apiClient.post("/api/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120000,
    });
    return response.data;
  } catch (error: any) {
    if (error?.code === "ECONNABORTED") {
      throw new Error("Timeout no upload. Verifique conexão/servidor e tente novamente.");
    }
    throw new Error(error.response?.data?.detail || "Erro ao enviar arquivo");
  }
};

// Extrair tabelas e salvar no Firestore
export const extractPDF = async (uploadId: string) => {
  try {
    const response = await apiClient.post("/api/extract", null, {
      params: { upload_id: uploadId },
      timeout: 600000,
    });

    // Dados já foram salvos no backend/Firestore
    return response.data;
  } catch (error: any) {
    if (error?.code === "ECONNABORTED") {
      throw new Error("Extração demorou demais. Tente novamente ou use um PDF menor.");
    }
    throw new Error(error.response?.data?.detail || "Erro ao extrair dados");
  }
};

/** Lista tabelas candidatas após upload (curadoria antes da IA). */
export const detectOrcamentoTables = async (uploadId: string) => {
  const formData = new FormData();
  formData.append("upload_id", uploadId);
  try {
    const response = await apiClient.post("/api/orcamentos/detect-tables", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 180000,
    });
    return response.data as {
      status: string;
      upload_id: string;
      tables_found: number;
      options: {
        id: string;
        nome_tabela?: string;
        preview_texto?: string;
        num_pagina?: number;
        pagina?: number;
        coordenadas?: number[];
        imagem_base64?: string;
      }[];
      mock_fallback?: boolean;
      recommended_table_ids?: string[];
    };
  } catch (error: any) {
    const detail = error.response?.data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d?.msg).join("; ")
          : "Erro ao detectar tabelas";
    throw new Error(msg || "Erro ao detectar tabelas");
  }
};

export type AnaliticoFullPdfResult = {
  status: string;
  upload_id: string;
  document_id: string | null;
  filename: string;
  items_found: number;
  hierarchical_items: unknown[];
  structured_items?: unknown[];
  items: unknown[];
  resumo: Record<string, unknown>;
  ia_metadata?: Record<string, unknown>;
  message: string;
  cached?: boolean;
};

export type AnaliticoProgressUpdate = {
  status: "processing" | "completed" | "failed";
  upload_id: string;
  pages_total: number;
  pages_done: number;
  current_page?: number | null;
  message?: string;
  error?: string;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const parseApiError = (error: unknown, fallback: string): string => {
  const err = error as { response?: { data?: { detail?: unknown } } };
  const detail = err.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d?.msg).join("; ") || fallback;
  }
  return fallback;
};

/** Erros HTTP do axios; demais Error (ex.: falha do job) preservam a mensagem original. */
function rethrowAnaliticoProcessError(error: unknown, fallback: string): never {
  const err = error as { response?: unknown; message?: string };
  if (err.response) {
    throw new Error(parseApiError(error, fallback));
  }
  if (error instanceof Error && error.message.trim()) {
    throw error;
  }
  throw new Error(fallback);
}

/** Processa o PDF inteiro para Orçamento Analítico (assíncrono + polling de progresso). */
export const processAnaliticoFullPdf = async (
  uploadId: string,
  options?: {
    forceReprocess?: boolean;
    onProgress?: (update: AnaliticoProgressUpdate) => void;
    pollIntervalMs?: number;
  },
): Promise<AnaliticoFullPdfResult> => {
  const pollIntervalMs = options?.pollIntervalMs ?? 1500;

  try {
    const startResponse = await apiClient.post(
      "/api/orcamentos/process-analitico-full",
      {
        upload_id: uploadId,
        force_reprocess: Boolean(options?.forceReprocess),
      },
      { timeout: 120000 },
    );

    const startData = startResponse.data as AnaliticoFullPdfResult & {
      status: string;
      hierarchical_items?: unknown[];
    };

    if (startData.status === "success" && Array.isArray(startData.hierarchical_items)) {
      return startData;
    }

    if (startData.status !== "processing") {
      return startData as AnaliticoFullPdfResult;
    }

    const processingStart = startData as AnaliticoProgressUpdate;
    options?.onProgress?.({
      status: "processing",
      upload_id: uploadId,
      pages_total: processingStart.pages_total ?? 0,
      pages_done: processingStart.pages_done ?? 0,
      message: startData.message ?? "Iniciando análise…",
    });

    for (;;) {
      await sleep(pollIntervalMs);
      const statusResponse = await apiClient.get(
        `/api/orcamentos/process-analitico-full/status/${uploadId}`,
        { timeout: 30000 },
      );
      const statusData = statusResponse.data as AnaliticoProgressUpdate & {
        result?: AnaliticoFullPdfResult;
      };

      if (statusData.status === "processing") {
        options?.onProgress?.(statusData);
        continue;
      }

      if (statusData.status === "completed") {
        if (!statusData.result) {
          throw new Error(
            "Análise concluída sem dados. Tente reenviar o PDF ou use force_reprocess.",
          );
        }
        options?.onProgress?.({
          ...statusData,
          pages_done: statusData.pages_total || statusData.pages_done,
          message: statusData.message ?? "Análise concluída",
        });
        return statusData.result;
      }

      if (statusData.status === "failed") {
        const detail =
          statusData.error ||
          statusData.message ||
          "Erro ao processar PDF completo";
        console.error("[Orçamento Analítico] Job falhou:", detail, statusData);
        throw new Error(detail);
      }
    }
  } catch (error: unknown) {
    rethrowAnaliticoProcessError(error, "Erro ao processar PDF completo");
  }
};

/** Processa as tabelas escolhidas (GPT-4o quando configurado no backend). */
export const processOrcamentoConfirmed = async (uploadId: string, tableIds: string | string[]) => {
  try {
    const payload = Array.isArray(tableIds) 
      ? { upload_id: uploadId, table_ids: tableIds }
      : { upload_id: uploadId, table_id: tableIds, table_ids: [tableIds] };
      
    const response = await apiClient.post(
      "/api/orcamentos/process-confirmed",
      payload,
      { timeout: 600000 },
    );
    return response.data as {
      status: string;
      upload_id: string;
      document_id: string | null;
      filename: string;
      tables_found: number;
      items_found: number;
      tables: any[];
      items: any[];
      structured_items?: any[];
      resumo: Record<string, unknown>;
      ia_metadata?: Record<string, unknown>;
      message: string;
    };
  } catch (error: any) {
    const detail = error.response?.data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d?.msg).join("; ")
          : "Erro ao processar tabela";
    throw new Error(msg || "Erro ao processar tabela");
  }
};

// ==================== FIRESTORE OPERATIONS ====================

// Salvar orçamento no Firebase
export const saveOrcamentoToFirebase = async (data: any) => {
  try {
    const docId = await saveOrcamento({
      uploadId: data.uploadId,
      filename: data.filename,
      uploadedAt: new Date(),
      items: data.items || [],
      tablesFound: data.tablesFound || 0,
      status: "completed",
    });
    return { success: true, documentId: docId };
  } catch (error: any) {
    console.error("Erro ao salvar no Firebase:", error);
    throw error;
  }
};

// Recuperar orçamento do Firebase
export const getOrcamentoFromFirebase = async (uploadId: string) => {
  try {
    const orcamento = await getOrcamentoByUploadId(uploadId);
    return orcamento;
  } catch (error: any) {
    console.error("Erro ao recuperar orçamento:", error);
    throw error;
  }
};

// Listar todos os orçamentos
export const getAllOrcamentosFromFirebase = async () => {
  try {
    const orcamentos = await getAllOrcamentos();
    return orcamentos;
  } catch (error: any) {
    console.error("Erro ao listar orçamentos:", error);
    throw error;
  }
};

// ==================== BACKEND OPERATIONS ====================

// Listar orçamentos via backend
export const listOrcamentos = async () => {
  try {
    const response = await apiClient.get("/api/orcamentos");
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao listar orçamentos",
    );
  }
};

// Recuperar orçamento via backend
export const getOrcamento = async (uploadId: string) => {
  try {
    const response = await apiClient.get(`/api/orcamentos/${uploadId}`);
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao recuperar orçamento",
    );
  }
};

// ==================== CURVA ABC OPERATIONS ====================

// Buscar dados da Curva ABC
export const getCurvaABC = async (uploadId: string) => {
  try {
    const response = await apiClient.get(`/api/curva-abc/${uploadId}`);
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao buscar dados da Curva ABC",
    );
  }
};

// ==================== EXPORT OPERATIONS ====================

export type ExportXlsxPayload = {
  items: unknown[];
  modelos_selecionados: OutputModelsSelection;
  nome_projeto?: string;
};

// Exportar planilha para XLSX (abas conforme modelos selecionados)
export const exportToXLSX = async (
  items: unknown[],
  options?: {
    modelosSelecionados?: OutputModelsSelection;
    nomeProjeto?: string;
  },
) => {
  try {
    const payload: ExportXlsxPayload = {
      items,
      modelos_selecionados: options?.modelosSelecionados ?? DEFAULT_OUTPUT_MODELS,
      nome_projeto: options?.nomeProjeto,
    };

    const response = await apiClient.post("/api/export-xlsx", payload, {
      responseType: "blob",
    });

    const safeName = (options?.nomeProjeto || "orcamento")
      .replace(/[^\w\s-áàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ]/g, "")
      .trim()
      .replace(/\s+/g, "_")
      .slice(0, 40) || "orcamento";

    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute(
      "download",
      `${safeName}_${new Date().toISOString().split("T")[0]}.xlsx`,
    );
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    window.URL.revokeObjectURL(url);

    return { success: true, message: "✅ Arquivo exportado com sucesso!" };
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || "Erro ao exportar arquivo");
  }
};

// ==================== AI OPERATIONS ====================

export const standardizeItemsWithAI = async (items: any[]) => {
  try {
    const response = await apiClient.post("/api/ai/standardize", { items });
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao padronizar itens com IA",
    );
  }
};

export const analyzeWithAI = async (
  uploadId: string,
  focus: "budget" | "items" | "structure" | "all" = "all",
) => {
  try {
    const response = await apiClient.post("/api/analyze-with-ai", {
      upload_id: uploadId,
      focus,
    });
    return response.data;
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || "Erro ao analisar com IA");
  }
};

export const getAIAnalysis = async (uploadId: string) => {
  try {
    const response = await apiClient.get(`/api/ai-analysis/${uploadId}`);
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao carregar análise detalhada",
    );
  }
};

export const getOrcamentoPdf = async (uploadId: string): Promise<Blob | null> => {
  try {
    const response = await apiClient.get(`/api/orcamentos/${uploadId}/pdf`, {
      responseType: "blob",
    });
    return response.data as Blob;
  } catch {
    return null;
  }
};

export type AiReportChartPoint = { name: string; value: number };

export type AiReportChart = {
  title: string;
  /** API estruturada: bar | pie */
  type?: "bar" | "pie";
  chart_type: "bar" | "pie" | "line" | "horizontal_bar";
  value_label?: "quantidade" | "valor" | "percentual" | string;
  data: AiReportChartPoint[];
};

export type ReportChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type AiReportTable = {
  title: string;
  headers: string[];
  rows: (string | number)[][];
};

export type AiReportAttachment = {
  filename: string;
  mime_type: string;
  content_base64: string;
};

export type AiReportChatResponse = {
  reply: string;
  response_type: string;
  chart?: AiReportChart | null;
  table?: AiReportTable | null;
  attachments?: AiReportAttachment[];
};

/** Normaliza resposta da API (formato novo ou legado só com explanation/title). */
export function normalizeAiReportResponse(raw: Record<string, unknown>): AiReportChatResponse {
  const reply =
    typeof raw.reply === "string" && raw.reply.trim()
      ? raw.reply
      : typeof raw.explanation === "string" && raw.explanation.trim()
        ? raw.explanation
        : typeof raw.title === "string" && raw.title.trim()
          ? raw.title
          : "Análise concluída. Confira gráfico, tabela ou anexos abaixo.";

  let chart: AiReportChatResponse["chart"] = null;
  const rawChart = raw.chart;
  if (rawChart && typeof rawChart === "object") {
    const c = rawChart as Record<string, unknown>;
    if (Array.isArray(c.data) && c.data.length > 0) {
      const rawType = String(c.type ?? c.chart_type ?? "bar").toLowerCase();
      const chartType: AiReportChart["chart_type"] =
        rawType === "pie"
          ? "pie"
          : rawType === "horizontal_bar" || rawType === "bar"
            ? "horizontal_bar"
            : rawType === "line"
              ? "line"
              : "horizontal_bar";
      chart = {
        title: String(c.title ?? raw.title ?? "Gráfico"),
        type: rawType === "pie" ? "pie" : "bar",
        chart_type: chartType,
        value_label: String(c.value_label ?? "valor"),
        data: c.data as AiReportChart["data"],
      };
    }
  } else if (Array.isArray(raw.data) && raw.data.length > 0) {
    chart = {
      title: String(raw.title ?? "Gráfico"),
      chart_type: (raw.chart_type as AiReportChart["chart_type"]) ?? "bar",
      value_label: "valor",
      data: raw.data as AiReportChart["data"],
    };
  }

  let table: AiReportChatResponse["table"] = null;
  const rawTable = raw.table;
  if (rawTable && typeof rawTable === "object") {
    const t = rawTable as Record<string, unknown>;
    if (Array.isArray(t.rows) && t.rows.length > 0) {
      table = {
        title: String(t.title ?? "Tabela"),
        headers: Array.isArray(t.headers) ? (t.headers as string[]) : [],
        rows: t.rows as AiReportTable["rows"],
      };
    }
  }

  const attachments = Array.isArray(raw.attachments)
    ? (raw.attachments as AiReportAttachment[])
    : [];

  return {
    reply,
    response_type: String(raw.response_type ?? "text"),
    chart,
    table,
    attachments,
  };
}

export const aiReportChat = async (
  messages: ReportChatMessage[],
  items: unknown[],
  meta?: { filename?: string; uploadId?: string },
): Promise<AiReportChatResponse> => {
  try {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    const response = await apiClient.post(
      "/api/ai-report-chat",
      {
        messages,
        message: lastUser?.content ?? "",
        items,
        filename: meta?.filename ?? "orcamento",
        upload_id: meta?.uploadId ?? "",
      },
      { timeout: 120000 },
    );
    const data = response.data;
    if (data && typeof data === "object") {
      return normalizeAiReportResponse(data as Record<string, unknown>);
    }
    return {
      reply: "Resposta vazia do servidor.",
      response_type: "text",
      chart: null,
      table: null,
      attachments: [],
    };
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao gerar relatório com IA",
    );
  }
};

function sanitizeAttachmentFilename(filename: string, mimeType: string): string {
  const base = filename
    .replace(/\.(pdf|md|csv|txt|xlsx)+$/gi, "")
    .replace(/\.+/g, "_")
    .replace(/_+$/g, "")
    .trim() || "analise";

  if (mimeType.includes("pdf")) {
    return base.endsWith(".pdf") ? base : `${base}.pdf`;
  }
  if (mimeType.includes("csv")) {
    return base.endsWith(".csv") ? base : `${base}.csv`;
  }
  if (mimeType.includes("markdown")) {
    return base.endsWith(".md") ? base : `${base}.md`;
  }
  return filename;
}

export function downloadAiAttachment(att: AiReportAttachment): void {
  const binary = atob(att.content_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: att.mime_type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = sanitizeAttachmentFilename(att.filename, att.mime_type);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export const saveReviewedItems = async (uploadId: string, items: any[]) => {
  try {
    const response = await apiClient.post(
      `/api/orcamentos/${uploadId}/review-items`,
      { items },
    );
    return response.data;
  } catch (error: any) {
    throw new Error(
      error.response?.data?.detail || "Erro ao salvar itens revisados",
    );
  }
};

export const exportReviewedXLSX = async (uploadId: string) => {
  try {
    const curvaResponse = await getCurvaABC(uploadId);
    const items = (curvaResponse?.items || []).map((item: any, index: number) => ({
      id: index + 1,
      code: String(item.id || index + 1).padStart(3, "0"),
      description: item.descricao || "",
      unit: item.unidade || "un",
      qty: Number(item.quantidade || 0),
      unitPrice: Number(item.valor_unitario || 0),
    }));

    if (!items.length) {
      throw new Error("Nenhum item disponível para exportação");
    }

    return await exportToXLSX(items);
  } catch (error: any) {
    throw new Error(
      error.message || error.response?.data?.detail || "Erro ao exportar revisão",
    );
  }
};
