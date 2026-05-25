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
import {
  exportToXLSX,
  getOrcamento,
  getOrcamentoFromFirebase,
  getOrcamentoPdf,
} from "../services/api";
import { useAuth } from "../features/auth/AuthContext";
import { upsertOrcamento } from "../features/orcamentos/orcamentoRepository";
import ConfirmDialog from "../components/ConfirmDialog";
import { btnAccent, btnMuted, btnSuccess, iconButton } from "../components/ui/buttonClasses";
import {
  type OrcamentoItem,
  recalcularCurvaABC,
  calcularResumoAbc,
  parseEditableNumber,
  unitPriceSemBdiFromComBdi,
  resolveStructuredItemPricing,
  isExecutiveItem,
} from "../features/orcamentos/recalcularCurvaABC";
import type { NovoOrcamentoFlowState } from "../features/orcamentos/outputModels";
import { CURVA_ABC_ONLY } from "../features/orcamentos/outputModels";

// --- CONFIGURAÇÃO OBRIGATÓRIA DO WORKER (PARA VITE) ---
// `?url` faz o Vite emitir o arquivo estático com URL correta (evita CORS do CDN e 404 por path relativo a esta página).
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerSrc;

type ItemOrcamento = OrcamentoItem;

const EDITABLE_NUMERIC_CLASS =
  "w-full rounded-md border border-slate-200/90 bg-slate-50 px-1.5 py-1 text-right text-sm font-medium tabular-nums transition hover:border-slate-300 hover:bg-slate-100 focus:border-blue-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-300 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none";

interface TableRow {
  [key: string]: string | number;
}

interface ExtractedTable {
  page: number;
  table_id: string;
  rows: TableRow[][];
}

/** Recortes das tabelas escolhidas na tela anterior (mesmo payload do detect-tables). */
interface SelectedTablePreview {
  id: string;
  name: string;
  page: number;
  imagem_base64?: string;
}

interface StructuredBudgetItem {
  item?: string | number;
  tipo?: string;
  banco?: string;
  codigo?: string;
  Código?: string;
  bdi?: number | string;
  BDI?: number | string;
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

const toBdiPercent = (value: unknown): number => {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return 0;
  const compact = value.replace("%", "").replace(/\s/g, "");
  return toNumber(compact);
};

const mapStructuredItemsToValidation = (
  items: StructuredBudgetItem[],
): ItemOrcamento[] => {
  const mapped: ItemOrcamento[] = [];
  let id = 0;

  for (const item of items) {
    const tipo = String(item.tipo ?? "item").toLowerCase();
    const description = String(item.descricao ?? item.Descrição ?? "").trim();
    const code = String(item.codigo ?? item.Código ?? "").trim();
    if (tipo === "grupo" || description.toLowerCase().includes("total do grupo")) {
      continue;
    }

    const { qty, bdi, unitPrice } = resolveStructuredItemPricing(item);

    mapped.push({
      id: ++id,
      item: String(item.item ?? ""),
      tipo: String(item.tipo ?? "item"),
      banco: String(item.banco ?? ""),
      code: code || String(id).padStart(3, "0"),
      description,
      bdi,
      unit: String(item.unidade ?? item.Unidade ?? "un").trim() || "un",
      qty,
      unitPrice,
      lineTotal: 0,
      selected: false,
    });
  }

  return mapped;
};

const mapStoredItemsToValidation = (rawItems: unknown[]): ItemOrcamento[] => {
  const mapped: ItemOrcamento[] = [];
  let id = 0;

  for (const raw of rawItems) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as Record<string, unknown>;
    const tipo = String(item.tipo ?? "item").toLowerCase();
    const description = String(item.descricao ?? item.description ?? "").trim();
    if (tipo === "grupo" || description.toLowerCase().includes("total do grupo")) {
      continue;
    }

    const qty = toNumber(item.quantidade ?? item.quantity ?? item.qty);
    const bdi = toBdiPercent(item.bdi);
    const pricing = resolveStructuredItemPricing({
      quantidade: qty,
      valor_unitario: item.valor_unitario ?? item.unitValue,
      unitPrice: item.unitPrice,
      valor_total: item.valor_total ?? item.totalValue,
      totalValue: item.totalValue,
      bdi,
    });
    const unitFromStore =
      item.unitPrice !== undefined && Number(item.unitPrice) > 0
        ? toNumber(item.unitPrice)
        : pricing.unitPrice;

    mapped.push({
      id: ++id,
      item: String(item.item ?? ""),
      tipo: String(item.tipo ?? "item"),
      banco: String(item.banco ?? ""),
      code: String(item.codigo ?? item.code ?? id).trim() || String(id).padStart(3, "0"),
      description,
      bdi,
      unit: String(item.unidade ?? item.unit ?? "un").trim() || "un",
      qty: pricing.qty || qty,
      unitPrice: unitFromStore,
      lineTotal: 0,
      selected: false,
      classification: item.classification as "A" | "B" | "C" | undefined,
      individual_percentage:
        typeof item.individual_percentage === "number"
          ? item.individual_percentage
          : undefined,
      accumulated_percentage:
        typeof item.accumulated_percentage === "number"
          ? item.accumulated_percentage
          : undefined,
    });
  }

  return mapped;
};

export default function ValidacaoOrcamento() {
  const navigate = useNavigate();
  const location = useLocation();
  const flowState = location.state as NovoOrcamentoFlowState | null;
  const { uploadId: uploadIdFromRoute } = useParams<{ uploadId: string }>();
  const { user } = useAuth();

  const resolvedUploadId =
    (flowState?.uploadId as string | undefined) ?? uploadIdFromRoute;

  // States da Planilha
  const [items, setItems] = useState<ItemOrcamento[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteItemId, setDeleteItemId] = useState<number | null>(null);
  const [selectAll, setSelectAll] = useState(false);

  const abcResumo = useMemo(() => calcularResumoAbc(items), [items]);

  const applyAbcToItems = (raw: ItemOrcamento[]) => recalcularCurvaABC(raw);

  // States do PDF Viewer
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0); // Zoom

  const selectedTablePreviews = useMemo(() => {
    const raw = flowState?.selectedTablePreviews as SelectedTablePreview[] | undefined;
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (p) =>
        p &&
        typeof p.imagem_base64 === "string" &&
        p.imagem_base64.trim().length > 0,
    );
  }, [flowState]);

  const showSelectedTableImages = selectedTablePreviews.length > 0;

  useEffect(() => {
    if (!uploadIdFromRoute && !flowState?.structuredData && !flowState?.extractedData) {
      navigate("/validacao", { replace: true });
      return;
    }

    const load = async () => {
      setIsLoading(true);
      setLoadError("");

      if (flowState?.file) {
        setPdfFile(flowState.file);
      }

      const structuredItems = flowState?.structuredData?.items as
        | StructuredBudgetItem[]
        | undefined;

      if (Array.isArray(structuredItems) && structuredItems.length > 0) {
        setItems(applyAbcToItems(mapStructuredItemsToValidation(structuredItems)));
        setIsLoading(false);
        return;
      }

      if (flowState?.extractedData) {
        try {
          const parsedItems = parseExtractedTables(
            flowState.extractedData as ExtractedTable[],
          );
          setItems(applyAbcToItems(parsedItems));
        } catch {
          setLoadError("Erro ao processar dados extraídos do PDF");
        }
        setIsLoading(false);
        return;
      }

      const uploadId = resolvedUploadId;
      if (!uploadId) {
        setLoadError("Orçamento não identificado.");
        setIsLoading(false);
        return;
      }

      try {
        const [firebaseDoc, backendDoc, pdfBlob] = await Promise.all([
          getOrcamentoFromFirebase(uploadId).catch(() => null),
          getOrcamento(uploadId).catch(() => null),
          getOrcamentoPdf(uploadId).catch(() => null),
        ]);

        const rawItems =
          (firebaseDoc?.items as unknown[]) ??
          (backendDoc?.orcamento?.items as unknown[]) ??
          (backendDoc?.items as unknown[]) ??
          [];

        if (!Array.isArray(rawItems) || rawItems.length === 0) {
          setLoadError(
            "Nenhum item salvo para este orçamento. Processe o PDF em Novo Orçamento.",
          );
          setIsLoading(false);
          return;
        }

        setItems(applyAbcToItems(mapStoredItemsToValidation(rawItems)));

        if (pdfBlob) {
          setPdfFile(
            new File([pdfBlob], firebaseDoc?.filename ?? `${uploadId}.pdf`, {
              type: "application/pdf",
            }),
          );
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Erro ao carregar orçamento";
        setLoadError(msg);
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, [flowState, uploadIdFromRoute, resolvedUploadId, navigate]);

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
        bdiCol = -1,
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
              cellText === "bdi" ||
              cellText.includes("bdi") ||
              cellText.includes("b.d.i")
            ) {
              bdiCol = colIdx;
              if (idx === 0)
                console.log(`✓ Coluna BDI encontrada: índice ${colIdx}`);
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
          const colDesc = descCol >= 0 ? descCol : 3;
          const colBdi = bdiCol >= 0 ? bdiCol : -1;
          const colUn = unCol >= 0 ? unCol : 4;
          const colQtd = qtdCol >= 0 ? qtdCol : 5;
          const colVu = vuCol >= 0 ? vuCol : 6;

          const description = String(row[colDesc] || "").trim();
          const bdi = colBdi >= 0 ? toBdiPercent(row[colBdi]) : 0;
          const unit = String(row[colUn] || "un").trim();
          const qty = parseNumber(row[colQtd]);
          const unitComBdi = parseNumber(row[colVu]);
          const unitPrice = unitPriceSemBdiFromComBdi(unitComBdi, bdi);

          // Validação: descrição não pode ser numérica simples (como "1.1", "2.1")
          const isNumeric =
            /^\d+(\.\d+)?$/.test(description) || description === "";
          if (description && !isNumeric) {
            items.push({
              id: id++,
              code: `${id.toString().padStart(3, "0")}`,
              description,
              bdi,
              unit,
              qty,
              unitPrice,
              lineTotal: 0,
            });
          }
        }
      });
    });

    return items;
  };

  const handleCellEdit = (
    id: number,
    field: "qty" | "unitPrice" | "bdi",
    rawValue: string,
  ) => {
    const numericValue = parseEditableNumber(rawValue);
    setItems((prev) => {
      const updated = prev.map((item) =>
        item.id === id ? { ...item, [field]: numericValue } : item,
      );
      return recalcularCurvaABC(updated);
    });
  };

  const handleChange = (
    id: number,
    field: keyof ItemOrcamento,
    value: string | number,
  ) => {
    setItems((prev) => {
      const updated = prev.map((item) =>
        item.id === id ? { ...item, [field]: value } : item,
      );
      if (field === "tipo") {
        return recalcularCurvaABC(updated);
      }
      return updated;
    });
  };

  const confirmRemoveItem = () => {
    if (deleteItemId == null) return;
    setItems((prev) => recalcularCurvaABC(prev.filter((item) => item.id !== deleteItemId)));
    setDeleteItemId(null);
    toast.success("Item removido");
  };

  const handleAddItem = () => {
    const newItem: ItemOrcamento = {
      id: (items.length ? Math.max(...items.map((i) => i.id)) : 0) + 1,
      code: `${(items.length + 1).toString().padStart(3, "0")}`,
      description: "",
      bdi: 0,
      unit: "un",
      qty: 0,
      unitPrice: 0,
      lineTotal: 0,
      selected: false,
    };
    setItems((prev) => recalcularCurvaABC([...prev, newItem]));
  };

  const handleSelectAll = () => {
    const newSelectAll = !selectAll;
    setSelectAll(newSelectAll);
    setItems((prev) => prev.map((item) => ({ ...item, selected: newSelectAll })));
  };

  const handleSelectItem = (id: number) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, selected: !item.selected } : item,
      ),
    );
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
    if (items.length === 0) {
      toast.warning("Nada para exportar", {
        description: "Adicione pelo menos um item à planilha.",
      });
      return;
    }

    setIsExporting(true);
    try {
      await exportToXLSX(items, {
        modelosSelecionados: CURVA_ABC_ONLY,
      });
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
        (flowState?.file as File | undefined)?.name ||
        (pdfFile?.name ?? `orcamento-${uploadId}.pdf`);

      const extractedData = (flowState?.extractedData as ExtractedTable[] | undefined) || [];

      const normalizedItems = items.map((item) => ({
        id: String(item.id),
        item: item.item,
        tipo: item.tipo,
        banco: item.banco,
        code: item.code,
        description: item.description,
        bdi: item.bdi,
        unit: item.unit,
        quantity: item.qty,
        unitValue: item.unitPrice,
        totalValue:
          item.lineTotal > 0
            ? item.lineTotal
            : Number(item.qty || 0) * Number(item.unitPrice || 0),
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
            onClick={() => navigate("/validacao")}
            className={iconButton}
            aria-label="Voltar à lista de validação"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold leading-tight text-slate-900">
              Validação do orçamento
            </h1>
            <p className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
              {isLoading
                ? "Carregando…"
                : `Ajuste dos valores · ${items.length} itens · Curva ABC`}
              {pdfFile?.name ? (
                <span className="hidden truncate sm:inline" title={pdfFile.name}>
                  · {pdfFile.name}
                </span>
              ) : null}
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
          <div className="h-12 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0 z-10 gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase shrink-0">
              {showSelectedTableImages ? "Tabelas analisadas" : "PDF Original"}
            </span>

            <div className="flex items-center gap-2 min-w-0 justify-center flex-1">
              <button
                type="button"
                onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
                className="cursor-pointer rounded p-1.5 text-slate-600 hover:bg-slate-100"
                title="Diminuir zoom"
                aria-label={showSelectedTableImages ? "Diminuir zoom das imagens" : "Diminuir zoom do PDF"}
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
                aria-label={showSelectedTableImages ? "Aumentar zoom das imagens" : "Aumentar zoom do PDF"}
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <div className="h-6 border-l border-slate-300 shrink-0" />
              <button
                type="button"
                onClick={() => setScale(showSelectedTableImages ? 1 : 0.8)}
                className="cursor-pointer rounded px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 shrink-0"
                title={showSelectedTableImages ? "Redefinir zoom (100%)" : "Ajustar à largura"}
              >
                {showSelectedTableImages ? "100%" : "Ajustar"}
              </button>
            </div>

            <div className="flex items-center gap-2 shrink-0 justify-end">
              {showSelectedTableImages ? (
                <span className="text-xs text-slate-600 whitespace-nowrap">
                  {selectedTablePreviews.length}{" "}
                  {selectedTablePreviews.length === 1 ? "tabela" : "tabelas"}
                </span>
              ) : (
                <>
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
                </>
              )}
            </div>
          </div>

          {/* PDF completo ou apenas recortes das tabelas escolhidas */}
          <div className="flex-1 overflow-auto p-4 bg-slate-200/50">
            {showSelectedTableImages ? (
              <div className="mx-auto flex max-w-full flex-col gap-6">
                {selectedTablePreviews.map((tbl) => (
                  <figure
                    key={tbl.id}
                    className="overflow-hidden rounded-lg border border-slate-200 bg-white p-3 shadow-md"
                  >
                    <figcaption className="mb-2 text-xs font-medium text-slate-600">
                      {tbl.name}
                      <span className="font-normal text-slate-400">
                        {" "}
                        · Pág. {tbl.page}
                      </span>
                    </figcaption>
                    <div className="overflow-x-auto rounded border border-slate-100 bg-slate-50">
                      <img
                        src={`data:image/png;base64,${tbl.imagem_base64}`}
                        alt={`Recorte da tabela: ${tbl.name}`}
                        className="mx-auto block h-auto max-w-none"
                        style={{ width: `${Math.round(scale * 100)}%` }}
                        draggable={false}
                      />
                    </div>
                  </figure>
                ))}
              </div>
            ) : pdfFile ? (
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
          </div>

          {/* Mini dashboard Curva ABC */}
          {!isLoading && !loadError && items.length > 0 && (
            <div className="shrink-0 border-b border-slate-100 bg-slate-50/50 px-6 py-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                <div className="rounded-xl border border-blue-200 bg-white p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Total geral (c/ BDI)
                  </p>
                  <p className="mt-2 text-xl font-bold tabular-nums text-blue-700 transition-all duration-300">
                    R$ {formatMoney(abcResumo.totalGeral)}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {items.filter(isExecutiveItem).length} itens executivos
                  </p>
                </div>
                <div className="rounded-xl border border-red-200 bg-red-50/40 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-red-800">
                    Classe A
                  </p>
                  <p className="mt-2 text-lg font-bold tabular-nums text-red-900 transition-all duration-300">
                    {abcResumo.classeA.count} itens
                  </p>
                  <p className="mt-1 text-sm font-medium tabular-nums text-red-700">
                    R$ {formatMoney(abcResumo.classeA.valor)}
                  </p>
                </div>
                <div className="rounded-xl border border-yellow-200 bg-yellow-50/50 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-yellow-900">
                    Classe B
                  </p>
                  <p className="mt-2 text-lg font-bold tabular-nums text-yellow-900 transition-all duration-300">
                    {abcResumo.classeB.count} itens
                  </p>
                  <p className="mt-1 text-sm font-medium tabular-nums text-yellow-800">
                    R$ {formatMoney(abcResumo.classeB.valor)}
                  </p>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                    Classe C
                  </p>
                  <p className="mt-2 text-lg font-bold tabular-nums text-emerald-900 transition-all duration-300">
                    {abcResumo.classeC.count} itens
                  </p>
                  <p className="mt-1 text-sm font-medium tabular-nums text-emerald-700">
                    R$ {formatMoney(abcResumo.classeC.valor)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-xs text-slate-500">
                Edite Quantidade, Valor Unitário (s/ BDI) ou BDI (%) na tabela — a Curva ABC
                e os totais atualizam em tempo real.
              </p>
            </div>
          )}

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
                      <th className="px-3 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-20">
                        BDI (%)
                      </th>
                      <th className="px-2 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-center w-14">
                        Un.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-24">
                        Qtd.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-28">
                        V. Unit. s/ BDI
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right w-28 bg-slate-100">
                        Total c/ BDI
                      </th>
                      <th className="px-2 py-3 w-8"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {items.map((item) => {
                      const editable = isExecutiveItem(item);
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
                              title={`${item.individual_percentage?.toFixed(2) ?? "0"}% do total · Acumulado: ${item.accumulated_percentage?.toFixed(2) ?? "0"}%`}
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
                        <td className="px-3 py-3">
                          {editable ? (
                            <input
                              type="number"
                              step="0.01"
                              min={0}
                              inputMode="decimal"
                              value={item.bdi}
                              onChange={(e) =>
                                handleCellEdit(item.id, "bdi", e.target.value)
                              }
                              className={EDITABLE_NUMERIC_CLASS}
                              placeholder="0,00"
                              aria-label={`BDI percentual do item ${item.code}`}
                            />
                          ) : (
                            <span className="block text-right text-sm text-slate-400">—</span>
                          )}
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
                          {editable ? (
                            <input
                              type="number"
                              step="any"
                              min={0}
                              inputMode="decimal"
                              value={item.qty}
                              onChange={(e) =>
                                handleCellEdit(item.id, "qty", e.target.value)
                              }
                              placeholder="0"
                              className={EDITABLE_NUMERIC_CLASS}
                              aria-label={`Quantidade do item ${item.code}`}
                            />
                          ) : (
                            <span className="block text-right text-sm text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {editable ? (
                            <div className="flex items-center justify-end gap-1">
                              <span className="text-xs text-slate-400">R$</span>
                              <input
                                type="number"
                                step="0.01"
                                min={0}
                                inputMode="decimal"
                                value={item.unitPrice}
                                onChange={(e) =>
                                  handleCellEdit(item.id, "unitPrice", e.target.value)
                                }
                                className={`${EDITABLE_NUMERIC_CLASS} w-24`}
                                aria-label={`Valor unitário s/ BDI do item ${item.code}`}
                              />
                            </div>
                          ) : (
                            <span className="block text-right text-sm text-slate-400">—</span>
                          )}
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
                            {formatMoney(item.lineTotal)}
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
