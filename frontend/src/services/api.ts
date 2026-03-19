import axios from "axios";
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

  // No deploy fullstack do Vercel, API e frontend ficam no mesmo domínio.
  if (!import.meta.env.DEV && isVercelHost) {
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

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach Firebase ID token to protect backend endpoints.
apiClient.interceptors.request.use(async (config) => {
  try {
    const token = await ensureAuthToken();
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  } catch (e) {
    // Local dev can rely on backend's dev fallback auth.
    if (!import.meta.env.DEV) throw e;
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

// Exportar planilha para XLSX
export const exportToXLSX = async (items: any[]) => {
  try {
    const response = await apiClient.post("/api/export-xlsx", items, {
      responseType: "blob",
    });

    // Criar URL temporária e fazer download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute(
      "download",
      `orcamento_${new Date().toISOString().split("T")[0]}.xlsx`
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
