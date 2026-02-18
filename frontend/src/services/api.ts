import axios from "axios";
import {
  saveOrcamento,
  getOrcamentoByUploadId,
  getAllOrcamentos,
} from "./firebase";

// Detectar URL da API
// Em desenvolvimento: usar porta do Vite se houver, senão localhost:8000
// Em produção: usar a mesma origem
const getAPIBase = () => {
  if (import.meta.env.DEV) {
    // Desenvolvimento: tentar usar localhost:8000
    return "http://localhost:8000";
  } else {
    // Produção: usar a mesma origem (útil se frontend e backend estão na mesma porta)
    return window.location.origin;
  }
};

const API_BASE = getAPIBase();

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

// ==================== PDF OPERATIONS ====================

// Upload PDF
export const uploadPDF = async (file: File) => {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await apiClient.post("/api/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data;
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || "Erro ao enviar arquivo");
  }
};

// Extrair tabelas e salvar no Firestore
export const extractPDF = async (uploadId: string) => {
  try {
    const response = await apiClient.post("/api/extract", null, {
      params: { upload_id: uploadId },
    });

    // Dados já foram salvos no backend/Firestore
    return response.data;
  } catch (error: any) {
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
