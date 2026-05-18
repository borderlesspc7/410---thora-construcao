import React, { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation, useParams } from "react-router-dom";
import { Document, Page, pdfjs } from "react-pdf"; // <--- Imports do PDF
import pdfWorkerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import {
  ArrowLeft,
  AlertCircle,
  Check,
  Trash2,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Loader2,
  Download,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import { exportToXLSX } from "../services/api";
import { useAuth } from "../features/auth/AuthContext";
import { upsertOrcamento } from "../features/orcamentos/orcamentoRepository";
import ConfirmDialog from "../components/ConfirmDialog";
import { btnAccent, btnMuted, btnSuccess, iconButton } from "../components/ui/buttonClasses";

// --- CONFIGURAÇÃO OBRIGATÓRIA DO WORKER (PARA VITE) ---
// `?url` faz o Vite emitir o arquivo estático com URL correta (evita CORS do CDN e 404 por path relativo a esta página).
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerSrc;

// --- INTERFACES ---
interface ItemOrcamento {
  id: number;
  item?: string;
  tipo?: string;
  banco?: string;
  code: string;
  description: string;
  unit: string;
  qty: number;
  unitPrice: number;
  selected?: boolean;
  classification?: "A" | "B" | "C";
  accumulated_percentage?: number;
}

interface TableRow {
  [key: string]: string | number;
}

interface ExtractedTable {
  page: number;
  table_id: string;
  rows: TableRow[][];
}

interface StructuredBudgetItem {
  item?: string | number;
  tipo?: string;
  banco?: string;
  codigo?: string;
  Código?: string;
  descricao?: string;
  Descrição?: string;
  unidade?: string;
  Unidade?: string;
  quantidade?: number | string;
  Quantidade?: number | string;
  valor_unitario?: number | string;
  "Valor Unitário"?: number | string;
  valor_total?: number | string;
  Total?: number | string;
}

const toNumber = (value: unknown): number => {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return 0;
  const compact = value.replace("R$", "").replace(/\s/g, "");
  const normalized =
    compact.includes(",") && compact.includes(".")
      ? compact.replace(/\./g, "").replace(",", ".")
      : compact.includes(",")
        ? compact.replace(",", ".")
        : compact;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
};

const mapStructuredItemsToValidation = (
  items: StructuredBudgetItem[],
): ItemOrcamento[] => {
  return items.map((item, index) => {
    const quantity = toNumber(item.quantidade ?? item.Quantidade);
    const unitPrice = toNumber(item.valor_unitario ?? item["Valor Unitário"]);

    return {
      id: index + 1,
      item: String(item.item ?? ""),
      tipo: String(item.tipo ?? ""),
      banco: String(item.banco ?? ""),
      code: String(item.codigo ?? item.Código ?? item.item ?? index + 1).padStart(3, "0"),
      description: String(item.descricao ?? item.Descrição ?? "").trim(),
      unit: String(item.unidade ?? item.Unidade ?? "un").trim() || "un",
      qty: quantity,
      unitPrice,
      selected: false,
    };
  });
};

export default function ValidacaoOrcamento() {
  const navigate = useNavigate();
  const location = useLocation(); // <--- Para pegar o arquivo enviado
  const { uploadId: uploadIdFromRoute } = useParams<{ uploadId: string }>();
  const { user } = useAuth();

  const resolvedUploadId =
    (location.state?.uploadId as string | undefined) ?? uploadIdFromRoute;

  // States da Planilha
  const [items, setItems] = useState<ItemOrcamento[]>([]);
  const [totalGeral, setTotalGeral] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteItemId, setDeleteItemId] = useState<number | null>(null);
  const [selectAll, setSelectAll] = useState(false);

  // --- LÓGICA DA CURVA ABC ---
  const classifiedItems = useMemo(() => {
    // Filtramos apenas os itens (ignorando grupos) para o cálculo da Curva ABC
    const itemsToClassify = items.filter(item => item.tipo !== "grupo");
    
    // Ordenamos por valor total decrescente
    const sortedItems = [...itemsToClassify].sort((a, b) => {
      const totalA = a.qty * a.unitPrice;
      const totalB = b.qty * b.unitPrice;
      const diff = totalB - totalA;
      if (diff !== 0) return diff;
      return String(a.id).localeCompare(String(b.id), "pt-BR");
    });

    const totalValue = sortedItems.reduce((acc, item) => acc + (item.qty * item.unitPrice), 0);

    let accumulatedValue = 0;
    const classifiedMap = new Map<number, { classification: "A" | "B" | "C", accumulated_percentage: number }>();

    sortedItems.forEach((item) => {
      const itemTotal = item.qty * item.unitPrice;
      const prevPercentage = totalValue > 0 ? (accumulatedValue / totalValue) * 100 : 0;
      accumulatedValue += itemTotal;
      const currentPercentage = totalValue > 0 ? (accumulatedValue / totalValue) * 100 : 0;

      let classification: "A" | "B" | "C" = "C";
      if (prevPercentage < 80) {
        classification = "A";
      } else if (prevPercentage < 95) {
        classification = "B";
      }

      classifiedMap.set(item.id, {
        classification,
        accumulated_percentage: currentPercentage,
      });
    });

    // Construir a lista final ordenada: grupos primeiro (opcional, mas comum) ou apenas itens ordenados
    // Como a instrução foi "deve ficar em ordem do mais caro ao mais barato", vamos retornar os itens ordenados
    // e adicionar os grupos no final (ou ignorá-los na ordenação principal).
    // Vamos separar grupos e itens classificados.
    const finalItems: ItemOrcamento[] = [];

    // Adiciona os itens ordenados e classificados
    sortedItems.forEach(item => {
      const abcData = classifiedMap.get(item.id);
      finalItems.push({ ...item, ...abcData });
    });

    // Adiciona os grupos no final
    const groups = items.filter(item => item.tipo === "grupo");
    finalItems.push(...groups);

    return finalItems;
  }, [items]);

  // States do PDF Viewer
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0); // Zoom

  // 1. Recuperar o arquivo e dados extraídos ao carregar a tela
  useEffect(() => {
    // Se veio arquivo da navegação, usamos ele
    if (location.state?.file) {
      setPdfFile(location.state.file);
    } else {
      // Em produção, evitar warning ruidoso ao abrir rota diretamente.
      if (import.meta.env.DEV) {
        console.warn("Nenhum arquivo encontrado no estado da rota");
      }
    }

    // Carregar dados extraídos da API
    const structuredItems = location.state?.structuredData?.items as
      | StructuredBudgetItem[]
      | undefined;

    if (Array.isArray(structuredItems) && structuredItems.length > 0) {
      setItems(mapStructuredItemsToValidation(structuredItems));
      setIsLoading(false);
      return;
    }

    if (location.state?.extractedData) {
      const extractedData: ExtractedTable[] = location.state.extractedData;

      try {
        const parsedItems = parseExtractedTables(extractedData);
        setItems(parsedItems);
        setIsLoading(false);
      } catch (error) {
        console.error("Erro ao processar dados extraídos:", error);
        setLoadError("Erro ao processar dados extraídos do PDF");
        setIsLoading(false);
      }
    } else {
      setLoadError("Nenhum dado foi extraído do PDF");
      setIsLoading(false);
    }
  }, [location, navigate]);

  // Função para normalizar números (converte vírgula em ponto)
  const parseNumber = (value: any): number => {
    if (value === null || value === undefined || value === "") return 0;

    let numStr = String(value).trim();

    // Se contém vírgula como separador decimal (formato português)
    if (numStr.includes(",")) {
      // Remove espaços e pontos (usados como mil separator)
      numStr = numStr.replace(/\s/g, "").replace(/\./g, "");
      // Converte vírgula em ponto
      numStr = numStr.replace(",", ".");
    }

    const result = parseFloat(numStr);
    console.log(`📊 Convertendo: "${value}" → ${result}`);
    return isNaN(result) ? 0 : result;
  };

  // Função para detectar se uma linha é cabeçalho
  const isHeaderRow = (row: TableRow[]): boolean => {
    const headerKeywords = [
      "descrição",
      "description",
      "unidade",
      "unit",
      "quantidade",
      "quantity",
      "valor",
      "preço",
      "price",
      "unitário",
      "tipo",
      "type",
      "quant",
      "un.",
      "und",
      "item",
      "código",
      "code",
      "banco",
      "bank",
    ];

    // Verifica se a maioria das células contém palavras-chave de cabeçalho
    const headerCells = row.filter((cell) => {
      const cellText = String(cell || "")
        .toLowerCase()
        .trim();
      return (
        headerKeywords.some((keyword) => cellText.includes(keyword)) ||
        cellText === "" // Células vazias no cabeçalho também contam
      );
    });

    return headerCells.length >= row.length * 0.6; // Se 60%+ parecem ser cabeçalho
  };

  // Função para parsear as tabelas extraídas
  const parseExtractedTables = (tables: ExtractedTable[]): ItemOrcamento[] => {
    const items: ItemOrcamento[] = [];
    let id = 0;

    tables.forEach((table) => {
      let descCol = -1,
        unCol = -1,
        qtdCol = -1,
        vuCol = -1;

      table.rows.forEach((row, idx) => {
        // PRIMEIRA LINHA OU CABEÇALHO: Identificar índices das colunas
        if (idx === 0 || isHeaderRow(row)) {
          row.forEach((cell, colIdx) => {
            const cellText = String(cell || "")
              .toLowerCase()
              .trim();

            // Procura por palavras-chave em cada coluna
            if (
              cellText.includes("descrição") ||
              cellText.includes("description") ||
              cellText.includes("descr")
            ) {
              descCol = colIdx;
              if (idx === 0)
                console.log(`✓ Coluna Descrição encontrada: índice ${colIdx}`);
            } else if (
              cellText.includes("unidade") ||
              cellText.includes("un.") ||
              cellText.includes("un") ||
              cellText.includes("unit")
            ) {
              unCol = colIdx;
              if (idx === 0)
                console.log(`✓ Coluna Unidade encontrada: índice ${colIdx}`);
            } else if (
              cellText.includes("qtd") ||
              cellText.includes("quant") ||
              cellText.includes("quantity") ||
              cellText.includes("quantidade")
            ) {
              qtdCol = colIdx;
              if (idx === 0)
                console.log(`✓ Coluna Quantidade encontrada: índice ${colIdx}`);
            } else if (
              cellText.includes("valor") ||
              cellText.includes("preço") ||
              cellText.includes("price") ||
              cellText.includes("unitário") ||
              cellText.includes("unit.")
            ) {
              vuCol = colIdx;
              if (idx === 0)
                console.log(
                  `✓ Coluna Valor Unit. encontrada: índice ${colIdx}`,
                );
            }
          });
          return; // Pula o cabeçalho
        }

        // PRÓXIMAS LINHAS: Extrair dados usando os índices identificados
        if (row && row.length >= 1) {
          // Se os índices foram encontrados, usa-os; senão tenta ordem padrão
          const colDesc = descCol >= 0 ? descCol : 3; // Padrão: coluna 3 (depois de Item, Código, Banco)
          const colUn = unCol >= 0 ? unCol : 4;
          const colQtd = qtdCol >= 0 ? qtdCol : 5;
          const colVu = vuCol >= 0 ? vuCol : 6;

          const description = String(row[colDesc] || "").trim();
          const unit = String(row[colUn] || "un").trim();
          const qty = parseNumber(row[colQtd]);
          const unitPrice = parseNumber(row[colVu]);

          // Validação: descrição não pode ser numérica simples (como "1.1", "2.1")
          const isNumeric =
            /^\d+(\.\d+)?$/.test(description) || description === "";
          if (description && !isNumeric) {
            items.push({
              id: id++,
              code: `${id.toString().padStart(3, "0")}`,
              description,
              unit,
              qty,
              unitPrice,
            });
          }
        }
      });
    });

    return items;
  };

  // Recalcula total
  useEffect(() => {
    const total = items.reduce(
      (acc, item) => acc + item.qty * item.unitPrice,
      0,
    );
    setTotalGeral(total);
  }, [items]);

  // Handlers da Tabela
  const handleChange = (
    id: number,
    field: keyof ItemOrcamento,
    value: string | number,
  ) => {
    setItems((prevItems) =>
      prevItems.map((item) => {
        if (item.id === id) return { ...item, [field]: value };
        return item;
      }),
    );
  };

  const confirmRemoveItem = () => {
    if (deleteItemId == null) return;
    setItems((prev) => prev.filter((item) => item.id !== deleteItemId));
    setDeleteItemId(null);
    toast.success("Item removido");
  };

  const handleAddItem = () => {
    const newItem: ItemOrcamento = {
      id: Math.max(...items.map((i) => i.id), 0) + 1,
      code: `${(items.length + 1).toString().padStart(3, "0")}`,
      description: "",
      unit: "un",
      qty: 0,
      unitPrice: 0,
      selected: false,
    };
    setItems((prev) => [...prev, newItem]);
  };

  const handleSelectAll = () => {
    const newSelectAll = !selectAll;
    setSelectAll(newSelectAll);
    setItems(items.map(item => ({ ...item, selected: newSelectAll })));
  };

  const handleSelectItem = (id: number) => {
    setItems(items.map(item => 
      item.id === id ? { ...item, selected: !item.selected } : item
    ));
  };

  const selectedItemsCount = items.filter(item => item.selected).length;

  const formatMoney = (value: number) => {
    return value.toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  // Handlers do PDF
  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
  };

  // Handler de Exportação XLSX
  const handleExport = async () => {
    if (classifiedItems.length === 0) {
      toast.warning("Nada para exportar", {
        description: "Adicione pelo menos um item à planilha.",
      });
      return;
    }

    setIsExporting(true);
    try {
      await exportToXLSX(classifiedItems);
      toast.success("Planilha exportada", {
        description: "O download do XLSX deve iniciar em instantes.",
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro desconhecido";
      console.error("Erro ao exportar:", error);
      toast.error("Falha ao exportar", { description: msg });
    } finally {
      setIsExporting(false);
    }
  };

  const handleFinalizar = async () => {
    const uploadId = resolvedUploadId;
    if (!user?.uid) {
      toast.error("Sessão necessária", { description: "Faça login para finalizar." });
      return;
    }
    if (!uploadId) {
      toast.error("Upload inválido", {
        description: "Reenvie o PDF para gerar um novo orçamento.",
      });
      return;
    }
    if (items.length === 0) {
      toast.warning("Planilha vazia", {
        description: "Adicione pelo menos um item antes de finalizar.",
      });
      return;
    }

    setIsSaving(true);
    try {
      const filename =
        (location.state?.file as File | undefined)?.name ||
        (pdfFile?.name ?? `orcamento-${uploadId}.pdf`);

      const extractedData = (location.state?.extractedData as ExtractedTable[] | undefined) || [];

      const normalizedItems = classifiedItems.map((item) => ({
        id: String(item.id),
        item: item.item,
        tipo: item.tipo,
        banco: item.banco,
        code: item.code,
        description: item.description,
        unit: item.unit,
        quantity: item.qty,
        unitValue: item.unitPrice,
        totalValue: Number(item.qty || 0) * Number(item.unitPrice || 0),
        selected: Boolean(item.selected),
        classification: item.classification,
        accumulated_percentage: item.accumulated_percentage,
      }));

      await upsertOrcamento(uploadId, {
        userId: user.uid,
        uploadId,
        filename,
        uploadedAt: new Date(),
        extractedAt: new Date(),
        updatedAt: new Date(),
        items: normalizedItems,
        itemsFound: normalizedItems.length,
        tablesFound: extractedData.length,
        status: "completed",
        errorMessage: null,
      });

      toast.success("Orçamento salvo", {
        description: "Redirecionando para o painel…",
      });
      navigate("/", { replace: true });
    } catch (err: unknown) {
      console.error("Erro ao finalizar orçamento:", err);
      const msg =
        err instanceof Error ? err.message : "Erro ao salvar no Firebase.";
      toast.error("Não foi possível salvar", { description: msg });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-100 font-sans">
      <ConfirmDialog
        open={deleteItemId !== null}
        title="Remover item?"
        description="Esta linha será excluída da planilha de validação."
        confirmLabel="Remover"
        cancelLabel="Cancelar"
        variant="danger"
        onConfirm={confirmRemoveItem}
        onCancel={() => setDeleteItemId(null)}
      />

      <header className="z-20 flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 shadow-sm sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={iconButton}
            aria-label="Voltar"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <h1 className="font-semibold leading-tight text-slate-900">
              Orçamento extraído
            </h1>
            <p className="flex items-center gap-1 text-xs text-slate-500">
              {isLoading
                ? "Carregando…"
                : `Validação · ${items.length} itens`}
            </p>
          </div>
        </div>
        <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
          <button
            type="button"
            disabled={isLoading || items.length === 0 || isExporting}
            className={`${btnMuted} shrink-0`}
            onClick={handleExport}
            title="Exportar planilha em XLSX"
          >
            <Download className="h-4 w-4" />
            {isExporting ? "Exportando…" : "Exportar"}
          </button>
          <button
            type="button"
            disabled={isLoading || items.length === 0 || isSaving}
            className={`${btnSuccess} shrink-0`}
            onClick={handleFinalizar}
            title="Salvar orçamento no Firebase"
          >
            <CheckCircle2 className="h-4 w-4" />
            {isSaving ? "Salvando…" : "Finalizar"}
          </button>
          <button
            type="button"
            disabled={isLoading || selectedItemsCount === 0}
            className={`${btnAccent} shrink-0`}
            onClick={() => {
              if (selectedItemsCount === 0) {
                toast.warning("Selecione itens", {
                  description: "Marque ao menos um item para analisar na Curva ABC.",
                });
                return;
              }
              const selectedItems = items.filter((item) => item.selected);
              const uploadId = resolvedUploadId || "unknown";
              navigate(`/curva-abc/${uploadId}`, {
                state: {
                  items: selectedItems,
                  uploadId,
                },
              });
            }}
          >
            <Check className="h-4 w-4" />
            Analisar ({selectedItemsCount})
          </button>
        </div>
      </header>

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
        <div className="flex max-h-[42vh] min-h-0 w-full flex-col border-b border-slate-200 bg-slate-100 lg:max-h-none lg:w-5/12 lg:border-b-0 lg:border-r">
          {/* Toolbar do PDF */}
          <div className="h-12 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0 z-10">
            <span className="text-xs font-semibold text-slate-500 uppercase">
              PDF Original
            </span>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
                className="cursor-pointer rounded p-1.5 text-slate-600 hover:bg-slate-100"
                title="Diminuir zoom"
                aria-label="Diminuir zoom do PDF"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <span className="text-xs font-mono w-12 text-center text-slate-600">
                {(scale * 100).toFixed(0)}%
              </span>
              <button
                type="button"
                onClick={() => setScale((s) => Math.min(2.0, s + 0.1))}
                className="cursor-pointer rounded p-1.5 text-slate-600 hover:bg-slate-100"
                title="Aumentar zoom"
                aria-label="Aumentar zoom do PDF"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <div className="h-6 border-l border-slate-300"></div>
              <button
                type="button"
                onClick={() => setScale(0.8)}
                className="cursor-pointer rounded px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
                title="Ajustar à largura"
              >
                Ajustar
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
                disabled={pageNumber <= 1}
                className="rounded p-1.5 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
                aria-label="Página anterior"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-xs text-slate-600">
                Pág {pageNumber} de {numPages || "--"}
              </span>
              <button
                type="button"
                onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
                disabled={pageNumber >= numPages}
                className="rounded p-1.5 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
                aria-label="Próxima página"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Área de Renderização do PDF */}
          <div className="flex-1 overflow-auto p-4 bg-slate-200/50">
            {pdfFile ? (
              <div className="flex items-start justify-start">
                <Document
                  file={pdfFile}
                  onLoadSuccess={onDocumentLoadSuccess}
                  loading={
                    <div className="flex items-center gap-2 text-slate-500">
                      <Loader2 className="animate-spin w-5 h-5" /> Carregando
                      PDF...
                    </div>
                  }
                  error={
                    <div className="text-red-500 text-sm">
                      Erro ao carregar PDF. Tente enviar novamente.
                    </div>
                  }
                  className="shadow-lg"
                >
                  <Page
                    pageNumber={pageNumber}
                    scale={scale}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    className="bg-white"
                  />
                </Document>
              </div>
            ) : (
              <div className="text-center text-slate-400">
                <AlertCircle className="w-10 h-10 mx-auto mb-2 opacity-50" />
                <p>Nenhum arquivo carregado.</p>
              </div>
            )}
          </div>
        </div>

        {/* --- DIREITA: TABELA EDITÁVEL (Mantida Igual) --- */}
        <div className="flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-white lg:min-w-0">
          {/* Header Tabela */}
          <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-end bg-white shrink-0">
            <div className="flex items-center gap-4">
              <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
                Planilha Extraída
              </h2>
              <button
                type="button"
                onClick={handleAddItem}
                disabled={isLoading}
                className="rounded px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-50 bg-emerald-100"
              >
                + Adicionar Item
              </button>
            </div>
            <div className="text-right">
              <span className="text-xs text-slate-500 font-medium uppercase">
                Total Geral
              </span>
              <p className="text-lg font-bold text-blue-700 tabular-nums transition-all duration-300">
                R$ {formatMoney(totalGeral)}
              </p>
            </div>
          </div>

          {/* Estado: Carregando */}
          {isLoading && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-2" />
                <p className="text-slate-600">Processando dados extraídos...</p>
              </div>
            </div>
          )}

          {/* Estado: Erro */}
          {!isLoading && loadError && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center px-6">
                <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-2" />
                <p className="text-red-600 font-medium">{loadError}</p>
                <button
                  type="button"
                  onClick={() => navigate(-1)}
                  className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800"
                >
                  Voltar
                </button>
              </div>
            </div>
          )}

          {/* Corpo Tabela com Scroll Independente */}
          {!isLoading && !loadError && (
            <div className="flex-1 overflow-y-auto pb-20">
              {items.length === 0 ? (
                <div className="flex items-center justify-center h-full text-slate-400">
                  <div className="text-center">
                    <AlertCircle className="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p>Nenhum item foi extraído do PDF.</p>
                  </div>
                </div>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead className="bg-slate-50 sticky top-0 z-10 shadow-sm border-b border-slate-200">
                    <tr>
                      <th className="px-3 py-3 w-12">
                        <input
                          type="checkbox"
                          checked={selectAll}
                          onChange={handleSelectAll}
                          className="w-4 h-4 text-blue-600 rounded cursor-pointer"
                        />
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-20">
                        Item
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-24">
                        Código
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-20">
                        Banco
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-20">
                        Tipo
                      </th>
                      <th className="px-2 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider w-12 text-center">
                        ABC
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                        Descrição
                      </th>
                      <th className="px-2 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-center w-14">
                        Un.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-24">
                        Qtd.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-28">
                        Valor Unit.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-28 bg-slate-100">
                        Total
                      </th>
                      <th className="px-2 py-3 w-8"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {classifiedItems.map((item) => {
                      // Determinar a cor de fundo com base na classificação ABC
                      let rowBgClass = "hover:bg-blue-50/30";
                      if (item.classification === "A") {
                        rowBgClass = "bg-red-50/30 hover:bg-red-50/50";
                      } else if (item.classification === "B") {
                        rowBgClass = "bg-yellow-50/30 hover:bg-yellow-50/50";
                      } else if (item.classification === "C") {
                        rowBgClass = "bg-emerald-50/30 hover:bg-emerald-50/50";
                      }

                      return (
                      <tr
                        key={item.id}
                        className={`transition group ${
                          item.selected ? 'bg-blue-50/40' : rowBgClass
                        }`}
                      >
                        <td className="px-3 py-3">
                          <input
                            type="checkbox"
                            checked={item.selected || false}
                            onChange={() => handleSelectItem(item.id)}
                            className="w-4 h-4 text-blue-600 rounded cursor-pointer"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="text"
                            value={item.item || ""}
                            onChange={(e) =>
                              handleChange(item.id, "item", e.target.value)
                            }
                            className={`w-full bg-transparent font-mono text-xs focus:outline-none border-b border-transparent focus:border-blue-500 ${
                              item.classification === "A"
                                ? "text-red-700"
                                : item.classification === "B"
                                  ? "text-yellow-700"
                                  : item.classification === "C"
                                    ? "text-emerald-700"
                                    : "text-slate-600"
                            }`}
                            placeholder="1.1"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="text"
                            value={item.code}
                            onChange={(e) =>
                              handleChange(item.id, "code", e.target.value)
                            }
                            className={`w-full bg-transparent font-mono text-xs focus:outline-none border-b border-transparent focus:border-blue-500 ${
                              item.classification === "A"
                                ? "text-red-700"
                                : item.classification === "B"
                                  ? "text-yellow-700"
                                  : item.classification === "C"
                                    ? "text-emerald-700"
                                    : "text-slate-600"
                            }`}
                            placeholder="Código"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="text"
                            value={item.banco || ""}
                            onChange={(e) =>
                              handleChange(item.id, "banco", e.target.value)
                            }
                            className={`w-full bg-transparent font-mono text-xs focus:outline-none border-b border-transparent focus:border-blue-500 ${
                              item.classification === "A"
                                ? "text-red-700"
                                : item.classification === "B"
                                  ? "text-yellow-700"
                                  : item.classification === "C"
                                    ? "text-emerald-700"
                                    : "text-slate-600"
                            }`}
                            placeholder="SINAPI"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <select
                            value={item.tipo || "item"}
                            onChange={(e) =>
                              handleChange(item.id, "tipo", e.target.value)
                            }
                            className={`w-full bg-transparent text-xs focus:outline-none border-b border-transparent focus:border-blue-500 ${
                              item.classification === "A"
                                ? "text-red-700"
                                : item.classification === "B"
                                  ? "text-yellow-700"
                                  : item.classification === "C"
                                    ? "text-emerald-700"
                                    : "text-slate-600"
                            }`}
                          >
                            <option value="item">Item</option>
                            <option value="grupo">Grupo</option>
                          </select>
                        </td>
                        <td className="px-2 py-3 text-center">
                          {item.classification ? (
                            <span
                              className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-bold ${
                                item.classification === "A"
                                  ? "bg-red-100 text-red-700"
                                  : item.classification === "B"
                                    ? "bg-yellow-100 text-yellow-700"
                                    : "bg-emerald-100 text-emerald-700"
                              }`}
                              title={`Acumulado: ${item.accumulated_percentage?.toFixed(2)}%`}
                            >
                              {item.classification}
                            </span>
                          ) : (
                            <span className="text-slate-300">-</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="text"
                            value={item.description}
                            onChange={(e) =>
                              handleChange(
                                item.id,
                                "description",
                                e.target.value,
                              )
                            }
                            className={`w-full bg-transparent text-sm focus:outline-none border-b border-transparent focus:border-blue-500 ${
                              item.classification === "A"
                                ? "text-red-900"
                                : item.classification === "B"
                                  ? "text-yellow-900"
                                  : item.classification === "C"
                                    ? "text-emerald-900"
                                    : "text-slate-800"
                            }`}
                          />
                        </td>
                        <td className="px-2 py-3 text-center">
                          <input
                            type="text"
                            value={item.unit}
                            onChange={(e) =>
                              handleChange(item.id, "unit", e.target.value)
                            }
                            className={`w-full text-center rounded text-xs font-medium focus:outline-none focus:ring-1 focus:ring-blue-500 py-1 ${
                              item.classification === "A"
                                ? "bg-red-100 text-red-800"
                                : item.classification === "B"
                                  ? "bg-yellow-100 text-yellow-800"
                                  : item.classification === "C"
                                    ? "bg-emerald-100 text-emerald-800"
                                    : "bg-slate-50 text-slate-600"
                            }`}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <input
                            type="number"
                            step="any"
                            inputMode="decimal"
                            value={item.qty}
                            onChange={(e) =>
                              handleChange(
                                item.id,
                                "qty",
                                parseFloat(e.target.value) || 0,
                              )
                            }
                            placeholder="0,00"
                            className={`w-full text-right bg-transparent text-sm font-medium focus:outline-none border-b border-transparent focus:border-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none ${
                              item.classification === "A"
                                ? "text-red-900"
                                : item.classification === "B"
                                  ? "text-yellow-900"
                                  : item.classification === "C"
                                    ? "text-emerald-900"
                                    : "text-slate-700"
                            }`}
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1 border-b border-transparent focus-within:border-blue-500 transition-colors">
                            <span className={`text-xs ${
                              item.classification === "A"
                                ? "text-red-400"
                                : item.classification === "B"
                                  ? "text-yellow-500"
                                  : item.classification === "C"
                                    ? "text-emerald-500"
                                    : "text-slate-400"
                            }`}>R$</span>
                            <input
                              type="number"
                              step="0.01"
                              value={item.unitPrice}
                              onChange={(e) =>
                                handleChange(
                                  item.id,
                                  "unitPrice",
                                  parseFloat(e.target.value) || 0,
                                )
                              }
                              className={`w-20 text-right bg-transparent text-sm font-medium focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none ${
                                item.classification === "A"
                                  ? "text-red-900"
                                  : item.classification === "B"
                                    ? "text-yellow-900"
                                    : item.classification === "C"
                                      ? "text-emerald-900"
                                      : "text-slate-700"
                              }`}
                            />
                          </div>
                        </td>
                        <td className={`px-4 py-3 text-right ${
                          item.classification === "A"
                            ? "bg-red-100/50"
                            : item.classification === "B"
                              ? "bg-yellow-100/50"
                              : item.classification === "C"
                                ? "bg-emerald-100/50"
                                : "bg-slate-50/50"
                        }`}>
                          <span className={`text-sm font-bold ${
                            item.classification === "A"
                              ? "text-red-900"
                              : item.classification === "B"
                                ? "text-yellow-900"
                                : item.classification === "C"
                                  ? "text-emerald-900"
                                  : "text-slate-800"
                          }`}>
                            {formatMoney(item.qty * item.unitPrice)}
                          </span>
                        </td>
                        <td className="px-2 py-3 text-center">
                          <button
                            type="button"
                            onClick={() => setDeleteItemId(item.id)}
                            className="rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
                            aria-label={`Remover item ${item.code}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
