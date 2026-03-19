import React, { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Document, Page, pdfjs } from "react-pdf"; // <--- Imports do PDF
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
} from "lucide-react";
import { exportToXLSX } from "../services/api";

// --- CONFIGURAÇÃO OBRIGATÓRIA DO WORKER (PARA VITE) ---
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;

// --- INTERFACES ---
interface ItemOrcamento {
  id: number;
  code: string;
  description: string;
  unit: string;
  qty: number;
  unitPrice: number;
  selected?: boolean;
}

interface TableRow {
  [key: string]: string | number;
}

interface ExtractedTable {
  page: number;
  table_id: string;
  rows: TableRow[][];
}

export default function ValidacaoOrcamento() {
  const navigate = useNavigate();
  const location = useLocation(); // <--- Para pegar o arquivo enviado

  // States da Planilha
  const [items, setItems] = useState<ItemOrcamento[]>([]);
  const [totalGeral, setTotalGeral] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [selectAll, setSelectAll] = useState(false);

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

  const handleDelete = (id: number) => {
    if (window.confirm("Tem certeza que deseja remover este item?")) {
      setItems((prev) => prev.filter((item) => item.id !== id));
    }
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
    if (items.length === 0) {
      alert("⚠️ Adicione pelo menos um item antes de exportar");
      return;
    }

    setIsExporting(true);
    try {
      await exportToXLSX(items);
      alert("✅ Arquivo exportado com sucesso!");
    } catch (error: any) {
      console.error("❌ Erro ao exportar:", error);
      alert("❌ Erro ao exportar arquivo: " + error.message);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-white font-sans overflow-hidden">
      {/* HEADER */}
      <header className="h-16 border-b border-gray-200 px-6 flex items-center justify-between bg-white shrink-0 z-20 shadow-sm">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-gray-100 rounded-full text-gray-500 transition cursor-pointer"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="font-semibold text-gray-900 leading-tight">
              Orçamento Extraído
            </h1>
            <p className="text-xs text-gray-500 flex items-center gap-1">
              {isLoading
                ? "Carregando..."
                : `Validação • ${items.length} itens extraídos`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            disabled={isLoading || items.length === 0 || isExporting}
            className="bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition shadow-sm cursor-pointer"
            onClick={handleExport}
            title="Exportar planilha em XLSX"
          >
            <Download className="w-4 h-4" />
            {isExporting ? "Exportando..." : "Exportar"}
          </button>
          <button
            disabled={isLoading || selectedItemsCount === 0}
            className="bg-[#0F52BA] hover:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition shadow-sm cursor-pointer"
            onClick={() => {
              if (selectedItemsCount === 0) {
                alert("⚠️ Selecione pelo menos um item para analisar");
                return;
              }
              const selectedItems = items.filter(item => item.selected);
              const uploadId = location.state?.uploadId || "unknown";
              navigate(`/curva-abc/${uploadId}`, {
                state: {
                  items: selectedItems,
                  uploadId,
                },
              });
            }}
          >
            <Check className="w-4 h-4 " />
            Analisar ({selectedItemsCount})
          </button>
        </div>
      </header>

      {/* SPLIT VIEW */}
      <main className="flex flex-1 overflow-hidden h-[calc(100vh-64px)]">
        {/* --- ESQUERDA: PDF VIEWER REAL --- */}
        <div className="w-5/12 bg-slate-100 border-r border-gray-200 flex flex-col relative lg:flex">
          {/* Toolbar do PDF */}
          <div className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4 shrink-0 z-10">
            <span className="text-xs font-semibold text-gray-500 uppercase">
              PDF Original
            </span>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}
                className="p-1.5 hover:bg-gray-100 rounded text-gray-600 cursor-pointer"
                title="Diminuir Zoom"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-xs font-mono w-12 text-center text-gray-600">
                {(scale * 100).toFixed(0)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(2.0, s + 0.1))}
                className="p-1.5 hover:bg-gray-100 rounded text-gray-600 cursor-pointer"
                title="Aumentar Zoom"
              >
                <ZoomIn className="w-4 h-4 cursor-pointer" />
              </button>
              <div className="h-6 border-l border-gray-300"></div>
              <button
                onClick={() => setScale(0.8)}
                className="px-2 py-1.5 hover:bg-gray-100 rounded text-gray-600 text-xs font-medium cursor-pointer"
                title="Ajustar à Largura"
              >
                Ajustar
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
                disabled={pageNumber <= 1}
                className="p-1.5 hover:bg-gray-100 rounded text-gray-600 disabled:opacity-30"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs text-gray-600">
                Pág {pageNumber} de {numPages || "--"}
              </span>
              <button
                onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
                disabled={pageNumber >= numPages}
                className="p-1.5 hover:bg-gray-100 rounded text-gray-600 disabled:opacity-30"
              >
                <ChevronRight className="w-4 h-4" />
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
                    <div className="flex items-center gap-2 text-gray-500">
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
              <div className="text-center text-gray-400">
                <AlertCircle className="w-10 h-10 mx-auto mb-2 opacity-50" />
                <p>Nenhum arquivo carregado.</p>
              </div>
            )}
          </div>
        </div>

        {/* --- DIREITA: TABELA EDITÁVEL (Mantida Igual) --- */}
        <div className="w-full lg:w-7/12 bg-white flex flex-col h-full overflow-hidden">
          {/* Header Tabela */}
          <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-end bg-white shrink-0">
            <div className="flex items-center gap-4">
              <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
                Planilha Extraída
              </h2>
              <button
                onClick={handleAddItem}
                disabled={isLoading}
                className="px-3 py-1.5 bg-emerald-100 hover:bg-emerald-200 disabled:opacity-50 disabled:cursor-not-allowed text-emerald-700 rounded text-xs font-medium transition"
              >
                + Adicionar Item
              </button>
            </div>
            <div className="text-right">
              <span className="text-xs text-gray-500 font-medium uppercase">
                Total Geral
              </span>
              <p className="text-lg font-bold text-[#0F52BA] transition-all duration-300">
                R$ {formatMoney(totalGeral)}
              </p>
            </div>
          </div>

          {/* Estado: Carregando */}
          {isLoading && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-2" />
                <p className="text-gray-600">Processando dados extraídos...</p>
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
                  onClick={() => navigate(-1)}
                  className="mt-4 px-4 py-2 bg-slate-900 text-white rounded-lg text-sm hover:bg-slate-800"
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
                <div className="flex items-center justify-center h-full text-gray-400">
                  <div className="text-center">
                    <AlertCircle className="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p>Nenhum item foi extraído do PDF.</p>
                  </div>
                </div>
              ) : (
                <table className="w-full text-left border-collapse">
                  <thead className="bg-gray-50 sticky top-0 z-10 shadow-sm border-b border-gray-200">
                    <tr>
                      <th className="px-3 py-3 w-12">
                        <input
                          type="checkbox"
                          checked={selectAll}
                          onChange={handleSelectAll}
                          className="w-4 h-4 text-blue-600 rounded cursor-pointer"
                        />
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-24">
                        Código
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Descrição
                      </th>
                      <th className="px-2 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-center w-14">
                        Un.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right w-24">
                        Qtd.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right w-28">
                        Valor Unit.
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right w-28 bg-gray-100">
                        Total
                      </th>
                      <th className="px-2 py-3 w-8"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((item) => (
                      <tr
                        key={item.id}
                        className={`hover:bg-blue-50/30 transition group ${
                          item.selected ? 'bg-blue-50/40' : ''
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
                            className="w-full bg-transparent font-mono text-xs text-gray-600 focus:outline-none focus:text-blue-600 border-b border-transparent focus:border-blue-500"
                          />
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
                            className="w-full bg-transparent text-sm text-gray-800 focus:outline-none border-b border-transparent focus:border-blue-500"
                          />
                        </td>
                        <td className="px-2 py-3 text-center">
                          <input
                            type="text"
                            value={item.unit}
                            onChange={(e) =>
                              handleChange(item.id, "unit", e.target.value)
                            }
                            className="w-full text-center bg-gray-50 rounded text-xs font-medium text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 py-1"
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
                            className="w-full text-right bg-transparent text-sm font-medium text-gray-700 focus:outline-none border-b border-transparent focus:border-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-1 border-b border-transparent focus-within:border-blue-500 transition-colors">
                            <span className="text-xs text-gray-400">R$</span>
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
                              className="w-20 text-right bg-transparent text-sm font-medium text-gray-700 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none"
                            />
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right bg-gray-50/50">
                          <span className="text-sm font-bold text-gray-800">
                            {formatMoney(item.qty * item.unitPrice)}
                          </span>
                        </td>
                        <td className="px-2 py-3 text-center">
                          <button
                            onClick={() => handleDelete(item.id)}
                            className="text-gray-300 hover:text-red-500 transition p-1 rounded hover:bg-red-50"
                          >
                            <Trash2 className="w-4 h-4 cursor-pointer" />
                          </button>
                        </td>
                      </tr>
                    ))}
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
