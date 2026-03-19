import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  AlertCircle,
  Loader2,
  Brain,
  CheckCircle2,
  ClipboardList,
  BadgeDollarSign,
  Download,
} from "lucide-react";
import { getAIAnalysis, saveReviewedItems, exportReviewedXLSX } from "../services/api";

interface AnalysisItem {
  id?: string;
  descricao?: string;
  quantidade?: number;
  unidade?: string;
  valor_unitario?: number;
  valor_total?: number;
  validado?: boolean;
  notas?: string;
  classification?: "A" | "B" | "C";
  accumulated_percentage?: number;
}

const AnaliseDetalhada: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { uploadId } = useParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysisData, setAnalysisData] = useState<any>(location.state?.analysisResponse || null);
  const [reviewItems, setReviewItems] = useState<AnalysisItem[]>([]);
  const [draftItems, setDraftItems] = useState<AnalysisItem[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  useEffect(() => {
    const loadAnalysis = async () => {
      if (!uploadId) {
        setError("Upload ID não informado");
        setLoading(false);
        return;
      }

      if (analysisData) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await getAIAnalysis(uploadId);
        setAnalysisData(response);
      } catch (err: any) {
        setError(err.message || "Erro ao carregar análise detalhada");
      } finally {
        setLoading(false);
      }
    };

    loadAnalysis();
  }, [uploadId, analysisData]);

  const summary = analysisData?.analysis?.summary || {};
  const structure = analysisData?.analysis?.structure || {};

  useEffect(() => {
    if (!analysisData) return;

    const curvaItemsFromState =
      (location.state?.curvaItems as AnalysisItem[] | undefined) || [];
    const analysisItems = (analysisData?.analysis?.items as AnalysisItem[]) || [];
    const sourceItems = curvaItemsFromState.length > 0 ? curvaItemsFromState : analysisItems;

    const normalizedItems = sourceItems.map((item, index) => {
      const quantidade = Number(item.quantidade || 0);
      const valorUnitario = Number(item.valor_unitario || 0);
      const valorTotal = Number(item.valor_total || quantidade * valorUnitario);

      return {
        id: item.id || String(index + 1),
        descricao: String(item.descricao || "").trim(),
        quantidade,
        unidade: String(item.unidade || "un"),
        valor_unitario: valorUnitario,
        valor_total: valorTotal,
        validado: item.validado !== false,
        notas: item.notas || "",
        classification: item.classification,
        accumulated_percentage: Number(item.accumulated_percentage || 0),
      } as AnalysisItem;
    });

    setReviewItems(normalizedItems);
    setDraftItems(normalizedItems);
  }, [analysisData, location.state]);

  const totalValidado = useMemo(() => {
    return reviewItems.filter((item) => item.validado !== false).length;
  }, [reviewItems]);

  const totalPendente = useMemo(() => {
    return Math.max(reviewItems.length - totalValidado, 0);
  }, [reviewItems, totalValidado]);

  const totalItens = reviewItems.length;
  const valorTotalRevisado = useMemo(() => {
    return reviewItems.reduce(
      (acc, item) => acc + Number(item.valor_total || 0),
      0,
    );
  }, [reviewItems]);

  const confianca = Number(summary.confianca_analise || 0);
  const percentualConfianca = Math.max(0, Math.min(100, Math.round(confianca * 100)));

  const formatCurrency = (value: number) => {
    return Number(value || 0).toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const handleEditValue = (
    index: number,
    field: "descricao" | "quantidade" | "unidade" | "valor_unitario" | "validado",
    value: string | number | boolean,
  ) => {
    setDraftItems((prev) =>
      prev.map((item, itemIndex) => {
        if (itemIndex !== index) return item;

        const updatedItem: AnalysisItem = {
          ...item,
          [field]: value,
        };

        const quantidade = Number(updatedItem.quantidade || 0);
        const valorUnitario = Number(updatedItem.valor_unitario || 0);
        updatedItem.valor_total = quantidade * valorUnitario;

        return updatedItem;
      }),
    );
  };

  const handleSaveEdits = () => {
    setReviewItems(draftItems);
    setIsEditing(false);
  };

  const handleCancelEdits = () => {
    setDraftItems(reviewItems);
    setIsEditing(false);
  };

  const handleApplyToCurvaABC = async () => {
    if (!uploadId) return;

    setApplyError(null);
    setIsApplying(true);

    const itemsToApply = isEditing ? draftItems : reviewItems;

    try {
      if (isEditing) {
        setReviewItems(draftItems);
        setIsEditing(false);
      }

      await saveReviewedItems(uploadId, itemsToApply);

      navigate(`/curva-abc/${uploadId}`, {
        state: {
          uploadId,
          editedItems: itemsToApply,
          fromDetailedAnalysis: true,
        },
      });
    } catch (err: any) {
      setApplyError(err.message || "Erro ao aplicar alterações na Curva ABC");
    } finally {
      setIsApplying(false);
    }
  };

  const handleExportReviewed = async () => {
    if (!uploadId) return;

    setApplyError(null);
    setIsExporting(true);

    try {
      const itemsToPersist = isEditing ? draftItems : reviewItems;
      await saveReviewedItems(uploadId, itemsToPersist);
      if (isEditing) {
        setReviewItems(draftItems);
        setIsEditing(false);
      }

      await exportReviewedXLSX(uploadId);
    } catch (err: any) {
      setApplyError(err.message || "Erro ao exportar revisão");
    } finally {
      setIsExporting(false);
    }
  };

  const visibleItems = isEditing ? draftItems : reviewItems;

  return (
    <div className="w-full min-h-full bg-slate-100 py-8 pb-16">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-slate-200 rounded-lg transition"
          >
            <ArrowLeft size={24} />
          </button>
          <div>
            <h1 className="text-3xl font-bold">Análise Detalhada da IA</h1>
            <p className="text-slate-600">
              Resultado consolidado da leitura do PDF e classificação Curva ABC
            </p>
          </div>
        </div>

        {!loading && !error && (
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            <button
              onClick={handleApplyToCurvaABC}
              disabled={isApplying}
              className="px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium transition shadow-sm"
            >
              {isApplying ? "Aplicando..." : "Aplicar na Curva ABC"}
            </button>
            <button
              onClick={() => navigate(`/curva-abc/${uploadId}`)}
              className="px-4 py-2.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium transition border border-slate-200"
            >
              Voltar sem aplicar
            </button>
            <button
              onClick={handleExportReviewed}
              disabled={isExporting}
              className="px-4 py-2.5 rounded-lg bg-slate-700 hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium transition border border-slate-700 inline-flex items-center justify-center gap-2"
            >
              <Download className="w-4 h-4" />
              {isExporting ? "Exportando revisão..." : "Exportar revisão (XLSX)"}
            </button>
          </div>
        )}

        {applyError && !loading && !error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-red-700 text-sm shadow-sm">
            {applyError}
          </div>
        )}

        {loading && (
          <div className="bg-white rounded-xl border border-slate-200 p-12 flex items-center justify-center gap-3 shadow-sm">
            <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
            <span className="text-slate-700">Carregando análise detalhada...</span>
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-6 text-red-700 flex gap-3 shadow-sm">
            <AlertCircle className="w-5 h-5 mt-0.5" />
            <div>{error}</div>
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6 shadow-sm">
              <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div>
                  <p className="text-sm text-slate-600">Confiança da análise</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{percentualConfianca}%</p>
                </div>
                <div className="w-full lg:w-2/3">
                  <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full bg-blue-600 rounded-full transition-all"
                      style={{ width: `${percentualConfianca}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-slate-600">Itens Analisados</p>
                  <ClipboardList className="w-4 h-4 text-slate-500" />
                </div>
                <p className="text-xl font-semibold text-slate-900">
                  {summary.total_items || totalItens}
                </p>
              </div>

              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-slate-600">Valor Total</p>
                  <BadgeDollarSign className="w-4 h-4 text-slate-500" />
                </div>
                <p className="text-xl font-semibold text-slate-900">
                  R$ {formatCurrency(valorTotalRevisado || Number(summary.valor_total || 0))}
                </p>
              </div>

              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-slate-600">Itens Validados</p>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                </div>
                <p className="text-xl font-semibold text-emerald-700">{totalValidado}</p>
              </div>

              <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-slate-600">Itens Pendentes</p>
                  <AlertCircle className="w-4 h-4 text-amber-600" />
                </div>
                <p className="text-xl font-semibold text-amber-700">{totalPendente}</p>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-slate-200 mb-6 shadow-sm">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Brain className="w-5 h-5 text-blue-600" />
                Estrutura Detectada
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3 text-sm">
                <div className="bg-slate-50 rounded-lg p-3">Descrição: coluna {structure.coluna_descricao ?? "-"}</div>
                <div className="bg-slate-50 rounded-lg p-3">Quantidade: coluna {structure.coluna_quantidade ?? "-"}</div>
                <div className="bg-slate-50 rounded-lg p-3">Unidade: coluna {structure.coluna_unidade ?? "-"}</div>
                <div className="bg-slate-50 rounded-lg p-3">Valor unitário: coluna {structure.coluna_valor_unitario ?? "-"}</div>
                <div className="bg-slate-50 rounded-lg p-3">Validados: {totalValidado}/{totalItens}</div>
              </div>
            </div>

            <div className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
                <div>
                  <h2 className="text-lg font-semibold">Itens detalhados</h2>
                  <p className="text-sm text-slate-500">
                    Base carregada da Curva ABC para revisão manual.
                  </p>
                </div>
                {!isEditing ? (
                  <button
                    onClick={() => {
                      setDraftItems(reviewItems);
                      setIsEditing(true);
                    }}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition"
                  >
                    Editar itens
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={handleCancelEdits}
                      className="px-4 py-2 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-800 text-sm font-medium transition"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleSaveEdits}
                      className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition"
                    >
                      Salvar alterações
                    </button>
                  </div>
                )}
              </div>

              {visibleItems.length === 0 ? (
                <div className="bg-slate-50 border border-slate-200 rounded-lg p-8 text-center text-slate-600">
                  Nenhum item disponível para exibição.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b sticky top-0 z-10">
                      <tr>
                        <th className="px-4 py-3 text-left font-semibold text-slate-700">Descrição</th>
                        <th className="px-4 py-3 text-right font-semibold text-slate-700">Qtd</th>
                        <th className="px-4 py-3 text-left font-semibold text-slate-700">Un</th>
                        <th className="px-4 py-3 text-right font-semibold text-slate-700">V. Unitário</th>
                        <th className="px-4 py-3 text-right font-semibold text-slate-700">V. Total</th>
                        <th className="px-4 py-3 text-left font-semibold text-slate-700">Classe</th>
                        <th className="px-4 py-3 text-left font-semibold text-slate-700">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleItems.map((item, idx) => (
                        <tr key={item.id || idx} className="border-b odd:bg-white even:bg-slate-50/40 hover:bg-blue-50/30 transition">
                          <td className="px-4 py-3 text-slate-900 min-w-[260px]">
                            {isEditing ? (
                              <input
                                value={String(item.descricao || "")}
                                onChange={(e) => handleEditValue(idx, "descricao", e.target.value)}
                                className="w-full px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                              />
                            ) : (
                              item.descricao || "-"
                            )}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-700">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={Number(item.quantidade || 0)}
                                onChange={(e) =>
                                  handleEditValue(idx, "quantidade", Number(e.target.value || 0))
                                }
                                className="w-24 ml-auto px-2 py-1 border border-slate-300 rounded-md text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
                              />
                            ) : (
                              Number(item.quantidade || 0).toLocaleString("pt-BR")
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            {isEditing ? (
                              <input
                                value={String(item.unidade || "")}
                                onChange={(e) => handleEditValue(idx, "unidade", e.target.value)}
                                className="w-20 px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                              />
                            ) : (
                              item.unidade || "-"
                            )}
                          </td>
                          <td className="px-4 py-3 text-right text-slate-700">
                            {isEditing ? (
                              <input
                                type="number"
                                step="0.01"
                                value={Number(item.valor_unitario || 0)}
                                onChange={(e) =>
                                  handleEditValue(idx, "valor_unitario", Number(e.target.value || 0))
                                }
                                className="w-28 ml-auto px-2 py-1 border border-slate-300 rounded-md text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
                              />
                            ) : (
                              <>R$ {formatCurrency(Number(item.valor_unitario || 0))}</>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right font-semibold text-slate-900">
                            R$ {formatCurrency(Number(item.valor_total || 0))}
                          </td>
                          <td className="px-4 py-3 text-slate-700">{item.classification || "-"}</td>
                          <td className="px-4 py-3">
                            {isEditing ? (
                              <select
                                value={item.validado === false ? "pendente" : "validado"}
                                onChange={(e) =>
                                  handleEditValue(idx, "validado", e.target.value === "validado")
                                }
                                className="px-2 py-1 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                              >
                                <option value="validado">Validado</option>
                                <option value="pendente">Pendente</option>
                              </select>
                            ) : (
                              <>
                                {item.validado === false ? (
                                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                                    Pendente
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                                    Validado
                                  </span>
                                )}
                              </>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AnaliseDetalhada;
