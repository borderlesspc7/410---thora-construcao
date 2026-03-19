import React, { useState, useMemo, useEffect } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  TrendingUp,
  Package,
  AlertCircle,
  CheckCircle2,
  Download,
  ChevronRight,
  Loader2,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { standardizeItemsWithAI, getCurvaABC, analyzeWithAI } from "../services/api";

interface Item {
  id: string;
  descricao: string;
  quantidade: number;
  unidade: string;
  valor_unitario: number;
  valor_total: number;
  status: "validado" | "pendente_validacao";
  classification?: "A" | "B" | "C";
  accumulated_percentage?: number;
}

type RawItem = Partial<Item> & {
  id?: string | number;
  description?: string;
  unit?: string;
  qty?: number;
  unitPrice?: number;
};

const CurvaABC: React.FC = () => {
  const { uploadId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedFilter, setSelectedFilter] = useState<"all" | "A" | "B" | "C">(
    "all",
  );
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<{
    provider?: string;
    totalItems?: number;
    valorTotal?: number;
    confianca?: number;
    warnings?: string[];
  } | null>(null);

  const toNumber = (value: unknown): number => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  };

  const normalizeItem = (raw: RawItem, index: number): Item => {
    const quantidade = toNumber(raw.quantidade ?? raw.qty);
    const valorUnitario = toNumber(raw.valor_unitario ?? raw.unitPrice);
    const valorTotal = toNumber(raw.valor_total ?? quantidade * valorUnitario);

    return {
      id: String(raw.id ?? index + 1),
      descricao: String(raw.descricao ?? raw.description ?? "").trim(),
      quantidade,
      unidade: String(raw.unidade ?? raw.unit ?? "un").trim() || "un",
      valor_unitario: valorUnitario,
      valor_total: valorTotal,
      status: (raw.status as Item["status"]) || "validado",
      classification: raw.classification,
      accumulated_percentage: toNumber(raw.accumulated_percentage),
    };
  };

  const classifyItemsABC = (baseItems: Item[]): Item[] => {
    const sortedItems = [...baseItems].sort((a, b) => b.valor_total - a.valor_total);
    const total = sortedItems.reduce((sum, item) => sum + item.valor_total, 0);
    let accumulated = 0;

    return sortedItems.map((item) => {
      accumulated += item.valor_total;
      const accumulated_percentage = total > 0 ? (accumulated / total) * 100 : 0;

      let classification: "A" | "B" | "C" = "C";
      if (accumulated_percentage <= 80) {
        classification = "A";
      } else if (accumulated_percentage <= 95) {
        classification = "B";
      }

      return {
        ...item,
        classification,
        accumulated_percentage: Math.round(accumulated_percentage * 10) / 10,
      };
    });
  };

  // Buscar dados reais da Curva ABC
  useEffect(() => {
    const fetchCurvaABC = async () => {
      if (!uploadId) {
        setError("Upload ID não fornecido");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);

        const editedItems = location.state?.editedItems as RawItem[] | undefined;
        
        // Verificar se há items selecionados passados via location.state
        const selectedItems = location.state?.items as RawItem[] | undefined;

        if (editedItems && editedItems.length > 0) {
          const normalizedEditedItems = editedItems.map((item, index) =>
            normalizeItem(item, index),
          );
          setItems(classifyItemsABC(normalizedEditedItems));
        } else if (selectedItems && selectedItems.length > 0) {
          // Usar apenas os items selecionados e calcular classificação ABC
          const normalizedSelectedItems = selectedItems.map((item, index) =>
            normalizeItem(item, index),
          );
          setItems(classifyItemsABC(normalizedSelectedItems));
        } else {
          // Buscar todos os items da API
          const response = await getCurvaABC(uploadId);
          const normalizedApiItems = ((response.items || []) as RawItem[]).map(
            (item, index) => normalizeItem(item, index),
          );
          setItems(classifyItemsABC(normalizedApiItems));
        }
      } catch (err: any) {
        console.error("Erro ao buscar Curva ABC:", err);
        setError(err.message || "Erro ao carregar dados da Curva ABC");
      } finally {
        setLoading(false);
      }
    };

    fetchCurvaABC();
  }, [uploadId, location.state]);

  // Calcula resumo
  const summary = useMemo(() => {
    const total = items.reduce((sum, item) => sum + item.valor_total, 0);
    const countA = items.filter((i) => i.classification === "A").length;
    const countB = items.filter((i) => i.classification === "B").length;
    const countC = items.filter((i) => i.classification === "C").length;
    const valueA = items.filter((i) => i.classification === "A").reduce(
      (sum, item) => sum + item.valor_total,
      0,
    );
    const valueB = items.filter((i) => i.classification === "B").reduce(
      (sum, item) => sum + item.valor_total,
      0,
    );
    const valueC = items.filter((i) => i.classification === "C").reduce(
      (sum, item) => sum + item.valor_total,
      0,
    );

    return {
      total,
      countA,
      countB,
      countC,
      valueA,
      valueB,
      valueC,
      percentA: total > 0 ? ((valueA / total) * 100).toFixed(1) : 0,
      percentB: total > 0 ? ((valueB / total) * 100).toFixed(1) : 0,
      percentC: total > 0 ? ((valueC / total) * 100).toFixed(1) : 0,
    };
  }, [items]);

  // Filtra itens
  const filteredItems = useMemo(() => {
    if (selectedFilter === "all") return items;
    return items.filter((item) => item.classification === selectedFilter);
  }, [items, selectedFilter]);

  const handleAiStandardize = async () => {
    setAiLoading(true);
    setAiError(null);
    try {
      if (!uploadId) {
        throw new Error("Upload ID não fornecido para análise de IA");
      }

      const response = await analyzeWithAI(uploadId, "all");
      const aiItems = Array.isArray(response?.analysis?.items)
        ? (response.analysis.items as RawItem[])
        : [];
      let nextItems: Item[] = [...items];

      if (aiItems.length > 0) {
        const normalized = aiItems.map((item, index) => normalizeItem(item, index));
        nextItems = classifyItemsABC(normalized);
        setItems(nextItems);
      } else {
        const standardized = await standardizeItemsWithAI(items);
        if (Array.isArray(standardized.items)) {
          const normalized = (standardized.items as RawItem[]).map((item, index) =>
            normalizeItem(item, index),
          );
          nextItems = classifyItemsABC(normalized);
          setItems(nextItems);
        }
      }

      setAiResult({
        provider: response?.provider,
        totalItems: Number(response?.analysis?.summary?.total_items || 0),
        valorTotal: Number(response?.analysis?.summary?.valor_total || 0),
        confianca: Number(response?.analysis?.summary?.confianca_analise || 0),
        warnings: Array.isArray(response?.warnings) ? response.warnings : [],
      });

      navigate(`/analise-detalhada/${uploadId}`, {
        state: {
          uploadId,
          analysisResponse: response,
          curvaItems: nextItems,
        },
      });
    } catch (error: any) {
      setAiError(error.message || "Erro ao padronizar itens com IA");
    } finally {
      setAiLoading(false);
    }
  };

  // Dados para o gráfico
  const chartData = [
    {
      name: "Classe A",
      itens: summary.countA,
      valor: summary.valueA,
      fill: "#1F4E78",
    },
    {
      name: "Classe B",
      itens: summary.countB,
      valor: summary.valueB,
      fill: "#2E7AD4",
    },
    {
      name: "Classe C",
      itens: summary.countC,
      valor: summary.valueC,
      fill: "#9FC2E8",
    },
  ];

  const getClassificationColor = (classification?: string) => {
    switch (classification) {
      case "A":
        return "bg-red-50 border-red-200 text-red-700";
      case "B":
        return "bg-amber-50 border-amber-200 text-amber-700";
      case "C":
        return "bg-green-50 border-green-200 text-green-700";
      default:
        return "bg-slate-50 border-slate-200 text-slate-700";
    }
  };

  const getClassificationBadge = (classification?: string) => {
    const badges = {
      A: {
        color: "bg-red-100 text-red-800",
        label: "Alto impacto",
        icon: "🔴",
      },
      B: {
        color: "bg-amber-100 text-amber-800",
        label: "Médio impacto",
        icon: "🟡",
      },
      C: {
        color: "bg-green-100 text-green-800",
        label: "Baixo impacto",
        icon: "🟢",
      },
    };
    const badge = badges[classification as keyof typeof badges];
    return badge || { color: "", label: "", icon: "" };
  };

  return (
    <div className="w-full min-h-full bg-slate-100 py-8 pb-16">
      <div className="max-w-7xl mx-auto px-4">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            onClick={() => navigate("/validacao")}
            className="p-2 hover:bg-slate-200 rounded-lg transition"
          >
            <ArrowLeft size={24} />
          </button>
          <div>
            <h1 className="text-3xl font-bold">Análise de Curva ABC</h1>
            <p className="text-slate-600">
              Classificação de itens por impacto no orçamento
            </p>
          </div>
        </div>

        {/* Aviso de Itens Selecionados */}
        {location.state?.items && !loading && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <CheckCircle2 size={20} className="text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-blue-900">Análise de Itens Selecionados</h3>
                <p className="text-sm text-blue-700 mt-1">
                  Analisando {items.length} {items.length === 1 ? 'item selecionado' : 'itens selecionados'} da página de validação.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-16">
            <Loader2 className="w-12 h-12 animate-spin text-blue-600 mb-4" />
            <p className="text-slate-600">Carregando dados da Curva ABC...</p>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 mb-8">
            <div className="flex gap-3">
              <AlertCircle size={20} className="text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-red-900">Erro ao carregar dados</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Dados carregados */}
        {!loading && !error && (
          <>
            {items.length === 0 ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 mb-8">
                <div className="flex gap-3">
                  <AlertCircle size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <h3 className="font-semibold text-amber-900">Nenhum item encontrado</h3>
                    <p className="text-sm text-amber-700 mt-1">
                      Não foi possível extrair itens do orçamento. Verifique se o PDF contém tabelas com dados válidos.
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg p-4 shadow-sm border border-slate-200">
            <p className="text-sm text-slate-600">Valor Total</p>
            <p className="text-2xl font-bold mt-2">
              R$ {(summary.total / 1000).toFixed(1)}k
            </p>
          </div>

          <div className="bg-red-50 rounded-lg p-4 shadow-sm border border-red-200">
            <p className="text-sm text-red-700 font-medium">
              Classe A (Alto impacto)
            </p>
            <p className="text-2xl font-bold text-red-800 mt-2">
              {summary.countA}
            </p>
            <p className="text-xs text-red-600 mt-1">
              {summary.percentA}% do valor
            </p>
          </div>

          <div className="bg-amber-50 rounded-lg p-4 shadow-sm border border-amber-200">
            <p className="text-sm text-amber-700 font-medium">
              Classe B (Médio impacto)
            </p>
            <p className="text-2xl font-bold text-amber-800 mt-2">
              {summary.countB}
            </p>
            <p className="text-xs text-amber-600 mt-1">
              {summary.percentB}% do valor
            </p>
          </div>

          <div className="bg-green-50 rounded-lg p-4 shadow-sm border border-green-200">
            <p className="text-sm text-green-700 font-medium">
              Classe C (Baixo impacto)
            </p>
            <p className="text-2xl font-bold text-green-800 mt-2">
              {summary.countC}
            </p>
            <p className="text-xs text-green-600 mt-1">
              {summary.percentC}% do valor
            </p>
          </div>
        </div>

        {/* Gráfico */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-lg font-semibold mb-6">
            Distribuição por Classe
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" />
              <YAxis
                yAxisId="left"
                label={{ value: "Itens", angle: -90, position: "insideLeft" }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                label={{
                  value: "Valor (R$)",
                  angle: 90,
                  position: "insideRight",
                }}
              />
              <Tooltip
                formatter={(value) => {
                  if (typeof value === "number" && value > 100) {
                    return `R$ ${(value / 1000).toFixed(1)}k`;
                  }
                  return value;
                }}
              />
              <Legend />
              <Bar
                yAxisId="left"
                dataKey="itens"
                fill="#2E7AD4"
                name="Quantidade de itens"
              />
              <Bar
                yAxisId="right"
                dataKey="valor"
                fill="#1F4E78"
                name="Valor total"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Filtros */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">
            Itens por Classificação
          </h2>
          <div className="flex gap-2 mb-6 flex-wrap">
            {[
              { value: "all", label: "Todos" },
              { value: "A", label: "Classe A (Alto impacto)" },
              { value: "B", label: "Classe B (Médio impacto)" },
              { value: "C", label: "Classe C (Baixo impacto)" },
            ].map((filter) => (
              <button
                key={filter.value}
                onClick={() => setSelectedFilter(filter.value as any)}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  selectedFilter === filter.value
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {/* Tabela de Itens */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="px-6 py-3 text-left text-sm font-semibold">
                    Classificação
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">
                    Descrição
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">
                    Quantidade
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">
                    Valor Total
                  </th>
                  <th className="px-6 py-3 text-left text-sm font-semibold">
                    % Acumulado
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item) => {
                  const badge = getClassificationBadge(item.classification);
                  return (
                    <tr
                      key={item.id}
                      className="border-b hover:bg-slate-50 transition"
                    >
                      <td className="px-6 py-3">
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-semibold ${badge.color}`}
                        >
                          {badge.icon} Classe {item.classification}
                        </span>
                      </td>
                      <td className="px-6 py-3 font-medium text-slate-900">
                        {item.descricao}
                      </td>
                      <td className="px-6 py-3 text-slate-700">
                        {item.quantidade} {item.unidade}
                      </td>
                      <td className="px-6 py-3 font-semibold text-slate-900">
                        R${" "}
                        {Number(item.valor_total || 0).toLocaleString("pt-BR", {
                          minimumFractionDigits: 2,
                        })}
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-24 bg-slate-200 rounded-full h-2">
                            <div
                              className="bg-blue-600 h-2 rounded-full"
                              style={{
                                width: `${Number(item.accumulated_percentage || 0)}%`,
                              }}
                            />
                          </div>
                          <span className="text-sm text-slate-600">
                            {Number(item.accumulated_percentage || 0)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Info Box */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-8">
          <div className="flex gap-3">
            <AlertCircle
              size={20}
              className="text-blue-600 flex-shrink-0 mt-0.5"
            />
            <div>
              <h3 className="font-semibold text-blue-900">
                Dica: Curva ABC (Pareto)
              </h3>
              <ul className="text-sm text-blue-800 mt-2 space-y-1">
                <li>
                  • <strong>Classe A (20% dos itens):</strong> Responsáveis por
                  ~80% do valor. Requerem atenção prioritária.
                </li>
                <li>
                  • <strong>Classe B (30% dos itens):</strong> Responsáveis por
                  ~15% do valor. Controle regular.
                </li>
                <li>
                  • <strong>Classe C (50% dos itens):</strong> Responsáveis por
                  ~5% do valor. Controle simplificado.
                </li>
              </ul>
            </div>
          </div>
        </div>

        {aiError && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mb-6">
            {aiError}
          </div>
        )}

        {aiResult && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg p-4 mb-6">
            <p className="font-semibold">Análise de IA concluída</p>
            <p className="text-sm mt-1">
              Itens analisados: {aiResult.totalItems || 0} • Valor total: R$ {Number(aiResult.valorTotal || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })} • Confiança: {(Number(aiResult.confianca || 0) * 100).toFixed(0)}%
            </p>
          </div>
        )}

        {/* Botões de Ação */}
        <div className="flex gap-4 justify-between">
          <button
            onClick={() => navigate("/validacao")}
            className="px-6 py-2 bg-slate-200 text-slate-800 rounded-lg hover:bg-slate-300 transition font-medium"
          >
            ← Voltar
          </button>
          <button
            onClick={handleAiStandardize}
            disabled={aiLoading}
            className={`px-6 py-2 rounded-lg transition font-medium flex items-center gap-2 ${
              aiLoading
                ? "bg-blue-400 text-white cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }`}
          >
            {aiLoading ? "Processando IA..." : "Próximo: IA"} <ChevronRight size={18} />
          </button>
        </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default CurvaABC;
