import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Download,
  FileText,
  BarChart3,
  Clock,
  Trash2,
  Eye,
  Plus,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import jsPDF from "jspdf";
import { listOrcamentos, getCurvaABC } from "../services/api";

interface Report {
  id: string;
  name: string;
  type: "budget" | "curva-abc" | "comparison" | "financial";
  createdAt: string;
  orcamentoName: string;
  size: string;
  uploadId?: string;           // present for real uploads
  itemsFound?: number;
  hasReviewedItems?: boolean;
  hasAIAnalysis?: boolean;
}

const MOCK_REPORTS: Report[] = [];

const Reports: React.FC = () => {
  const navigate = useNavigate();
  const [reports, setReports] = useState<Report[]>(MOCK_REPORTS);
  const [filter, setFilter] = useState<string>("all");
  const [loadingReports, setLoadingReports] = useState(true);
  const [generatingId, setGeneratingId] = useState<string | null>(null);

  // ── Load real uploads from backend on mount ─────────────────────────────
  useEffect(() => {
    const fetchReports = async () => {
      try {
        const data = await listOrcamentos();
        const realReports: Report[] = (data.orcamentos || []).map(
          (o: any, i: number) => ({
            id: o.uploadId || String(i),
            name: o.filename || o.uploadId || `Orçamento ${i + 1}`,
            type: "budget" as const,
            createdAt: o.uploadedAt
              ? new Date(o.uploadedAt).toLocaleString("pt-BR")
              : "—",
            orcamentoName: o.filename || o.uploadId || "—",
            size: `${o.itemsFound ?? "?"} itens`,
            uploadId: o.uploadId,
            itemsFound: o.itemsFound,
            hasReviewedItems: o.hasReviewedItems,
            hasAIAnalysis: o.hasAIAnalysis,
          }),
        );
        setReports(realReports);
      } catch (err) {
        console.error("Erro ao carregar orçamentos:", err);
        setReports([]);
      } finally {
        setLoadingReports(false);
      }
    };
    fetchReports();
  }, []);

  const filteredReports = reports.filter((r) =>
    filter === "all" ? true : r.type === filter
  );

  // ── Generate PDF ─────────────────────────────────────────────────────────
  const handleGenerateReport = async (report: Report) => {
    setGeneratingId(report.id);
    try {
      const pdf = new jsPDF();
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 15;

      // Header bar
      pdf.setFillColor(31, 78, 120);
      pdf.rect(0, 0, pageWidth, 30, "F");
      pdf.setTextColor(255, 255, 255);
      pdf.setFontSize(20);
      pdf.text("Thora Construction", margin, 20);

      // Title
      pdf.setTextColor(0, 0, 0);
      pdf.setFontSize(14);
      pdf.text(report.name, margin, 45);

      pdf.setFontSize(10);
      pdf.text(`Arquivo: ${report.orcamentoName}`, margin, 56);
      pdf.text(`Gerado em: ${new Date().toLocaleString("pt-BR")}`, margin, 64);

      let yPos = 78;

      if (report.uploadId) {
        // ── Real report ────────────────────────────────────────────────────
        const curvaData = await getCurvaABC(report.uploadId);
        const items: any[] = curvaData?.items || [];

        const totalValue = items.reduce(
          (s: number, i: any) => s + Number(i.valor_total || 0),
          0,
        );
        const classA = items.filter((i) => i.classification === "A");
        const classB = items.filter((i) => i.classification === "B");
        const classC = items.filter((i) => i.classification === "C");

        // Summary section
        pdf.setFontSize(12);
        pdf.setFont(undefined as any, "bold");
        pdf.text("Resumo do Orçamento", margin, yPos);
        pdf.setFont(undefined as any, "normal");
        pdf.setFontSize(10);
        yPos += 10;

        const summaryLines = [
          `Total do Orçamento: R$ ${totalValue.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`,
          `Total de Itens: ${items.length}`,
          `Classe A: ${classA.length} itens (alto valor)`,
          `Classe B: ${classB.length} itens (médio valor)`,
          `Classe C: ${classC.length} itens (baixo valor)`,
          report.hasReviewedItems
            ? "✓ Itens com revisão manual aplicada"
            : "Itens extraídos automaticamente (sem revisão manual)",
        ];
        summaryLines.forEach((line) => {
          pdf.text(`• ${line}`, margin + 5, yPos);
          yPos += 8;
        });

        // Items table
        yPos += 8;
        pdf.setFontSize(12);
        pdf.setFont(undefined as any, "bold");
        pdf.text("Lista de Itens", margin, yPos);
        yPos += 8;

        // Table header
        pdf.setFontSize(8);
        pdf.setFillColor(240, 244, 248);
        pdf.rect(margin, yPos, pageWidth - 2 * margin, 7, "F");
        pdf.setFont(undefined as any, "bold");
        pdf.text("#", margin + 2, yPos + 5);
        pdf.text("Descrição", margin + 10, yPos + 5);
        pdf.text("Qtd", margin + 100, yPos + 5);
        pdf.text("Un", margin + 118, yPos + 5);
        pdf.text("V. Unit", margin + 130, yPos + 5);
        pdf.text("V. Total", margin + 153, yPos + 5);
        pdf.text("ABC", margin + 173, yPos + 5);
        yPos += 9;

        pdf.setFont(undefined as any, "normal");
        items.slice(0, 60).forEach((item: any, idx: number) => {
          if (yPos > pageHeight - 20) {
            pdf.addPage();
            yPos = margin;
          }
          if (idx % 2 === 0) {
            pdf.setFillColor(249, 250, 251);
            pdf.rect(margin, yPos - 1, pageWidth - 2 * margin, 6.5, "F");
          }
          const desc = String(item.descricao || "").substring(0, 45);
          const qty = Number(item.quantidade || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
          const unit = String(item.unidade || "un");
          const vUnit = Number(item.valor_unitario || 0).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
          });
          const vTotal = Number(item.valor_total || 0).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
          });
          pdf.setFontSize(7.5);
          pdf.text(String(idx + 1), margin + 2, yPos + 4);
          pdf.text(desc, margin + 10, yPos + 4);
          pdf.text(qty, margin + 100, yPos + 4);
          pdf.text(unit, margin + 118, yPos + 4);
          pdf.text(vUnit, margin + 130, yPos + 4);
          pdf.text(vTotal, margin + 153, yPos + 4);
          pdf.text(item.classification || "—", margin + 173, yPos + 4);
          yPos += 7;
        });

        if (items.length > 60) {
          pdf.setFontSize(8);
          pdf.setTextColor(120, 120, 120);
          pdf.text(
            `... e mais ${items.length - 60} itens (exporte XLSX para lista completa)`,
            margin,
            yPos + 5,
          );
          pdf.setTextColor(0, 0, 0);
        }
      } else {
        // ── Fallback: static report ────────────────────────────────────────
        pdf.setFontSize(12);
        pdf.setFont(undefined as any, "bold");
        pdf.text("Resumo Executivo", margin, yPos);
        pdf.setFontSize(10);
        pdf.setFont(undefined as any, "normal");
        yPos += 12;
        pdf.text("Nenhum dado real disponível para este relatório.", margin, yPos);
      }

      // Footer
      pdf.setFontSize(8);
      pdf.setTextColor(128, 128, 128);
      pdf.text(
        `Gerado em ${new Date().toLocaleString("pt-BR")} · Thora Construction`,
        margin,
        pageHeight - 10,
      );

      pdf.save(`${report.name.replace(/\s+/g, "_")}.pdf`);
    } catch (err: any) {
      alert(`Erro ao gerar PDF: ${err.message || err}`);
    } finally {
      setGeneratingId(null);
    }
  };

  const handleDeleteReport = (id: string) => {
    if (window.confirm("Tem certeza que deseja remover este relatório da lista?")) {
      setReports(reports.filter((r) => r.id !== id));
    }
  };

  return (
    <div className="flex flex-col min-h-full bg-slate-50 pb-16">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Relatórios</h1>
            <p className="text-slate-600 text-sm">
              PDFs gerados com os dados reais dos orçamentos enviados
            </p>
          </div>
          <button
            onClick={() => navigate("/orcamento")}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition font-medium"
          >
            <Plus className="w-5 h-5" />
            Novo Orçamento
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-8">
        {/* Filtros */}
        <div className="mb-8 flex gap-3 flex-wrap">
          {[
            { value: "all", label: "Todos" },
            { value: "budget", label: "Orçamentos" },
          ].map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-4 py-2 rounded-lg font-medium transition ${
                filter === f.value
                  ? "bg-blue-600 text-white"
                  : "bg-white text-slate-700 border border-slate-200 hover:border-blue-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Loading skeleton */}
        {loadingReports ? (
          <div className="flex items-center justify-center h-48 gap-3 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span>Carregando orçamentos…</span>
          </div>
        ) : filteredReports.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-96 text-center">
            <FileText className="w-16 h-16 text-slate-300 mb-4" />
            <p className="text-slate-600 text-lg font-medium">
              Nenhum orçamento encontrado
            </p>
            <p className="text-slate-500 text-sm mt-1">
              Envie um PDF na aba{" "}
              <button
                className="text-blue-600 underline"
                onClick={() => navigate("/orcamento")}
              >
                Novo Orçamento
              </button>{" "}
              para gerar relatórios reais.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {filteredReports.map((report) => {
              const isGenerating = generatingId === report.id;
              return (
                <div
                  key={report.id}
                  className="bg-white rounded-lg border border-slate-200 p-6 hover:shadow-lg transition"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <h3
                        className="text-base font-semibold text-slate-900 mb-1 truncate"
                        title={report.name}
                      >
                        {report.name}
                      </h3>
                      {/* Status badges */}
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          Orçamento
                        </span>
                        {report.hasReviewedItems && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            <CheckCircle2 className="w-3 h-3" />
                            Revisado
                          </span>
                        )}
                        {report.hasAIAnalysis && (
                          <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                            Análise IA
                          </span>
                        )}
                      </div>
                    </div>
                    <FileText className="w-8 h-8 text-slate-300 ml-3 flex-shrink-0" />
                  </div>

                  <div className="space-y-1.5 mb-5 text-sm text-slate-600">
                    <p className="flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 flex-shrink-0" />
                      <span className="truncate">{report.orcamentoName}</span>
                    </p>
                    <p className="flex items-center gap-2">
                      <Clock className="w-4 h-4 flex-shrink-0" />
                      {report.createdAt}
                    </p>
                    {report.itemsFound !== undefined && (
                      <p className="text-slate-400 text-xs pl-6">
                        {report.itemsFound} itens extraídos
                      </p>
                    )}
                  </div>

                  <div className="flex gap-2">
                    <button
                      disabled={isGenerating}
                      onClick={() => handleGenerateReport(report)}
                      className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white py-2 rounded-lg transition font-medium text-sm"
                    >
                      {isGenerating ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      {isGenerating ? "Gerando…" : "Baixar PDF"}
                    </button>
                    {report.uploadId && (
                      <button
                        onClick={() =>
                          navigate(`/analise-detalhada/${report.uploadId}`)
                        }
                        className="flex-1 flex items-center justify-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 py-2 rounded-lg transition font-medium text-sm"
                      >
                        <Eye className="w-4 h-4" />
                        Ver análise
                      </button>
                    )}
                    <button
                      onClick={() => handleDeleteReport(report.id)}
                      className="flex items-center justify-center gap-2 bg-red-50 hover:bg-red-100 text-red-600 px-3 py-2 rounded-lg transition"
                      title="Remover da lista"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
};

export default Reports;
