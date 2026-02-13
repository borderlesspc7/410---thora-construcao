import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Download,
  FileText,
  BarChart3,
  TrendingUp,
  Clock,
  Trash2,
  Eye,
  Plus,
} from "lucide-react";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";

interface Report {
  id: string;
  name: string;
  type: "budget" | "curva-abc" | "comparison" | "financial";
  createdAt: string;
  orcamentoName: string;
  size: string;
}

const MOCK_REPORTS: Report[] = [
  {
    id: "1",
    name: "Orçamento Residencial Vila Nova",
    type: "budget",
    createdAt: "2024-01-24 14:30",
    orcamentoName: "Residencial Vila Nova – Bloco A",
    size: "2.4 MB",
  },
  {
    id: "2",
    name: "Análise ABC - Escola Municipal",
    type: "curva-abc",
    createdAt: "2024-01-23 10:15",
    orcamentoName: "Escola Municipal Centro",
    size: "1.8 MB",
  },
  {
    id: "3",
    name: "Comparativo Orçado vs Executado",
    type: "comparison",
    createdAt: "2024-01-22 16:45",
    orcamentoName: "Reforma Comercial – Shopping",
    size: "3.1 MB",
  },
  {
    id: "4",
    name: "Análise Financeira - Fluxo de Caixa",
    type: "financial",
    createdAt: "2024-01-20 09:00",
    orcamentoName: "Residencial Vila Nova – Bloco A",
    size: "2.7 MB",
  },
];

const typeLabels = {
  budget: { label: "Orçamento", color: "bg-blue-100 text-blue-800" },
  "curva-abc": { label: "Curva ABC", color: "bg-purple-100 text-purple-800" },
  comparison: {
    label: "Comparativo",
    color: "bg-green-100 text-green-800",
  },
  financial: { label: "Financeiro", color: "bg-orange-100 text-orange-800" },
};

const Reports: React.FC = () => {
  const navigate = useNavigate();
  const [reports, setReports] = useState<Report[]>(MOCK_REPORTS);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const filteredReports = reports.filter((r) =>
    filter === "all" ? true : r.type === filter
  );

  // Gerar PDF simulado
  const handleGenerateReport = (report: Report) => {
    const pdf = new jsPDF();
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 15;

    // Cabeçalho
    pdf.setFillColor(31, 78, 120);
    pdf.rect(0, 0, pageWidth, 30, "F");
    pdf.setTextColor(255, 255, 255);
    pdf.setFontSize(20);
    pdf.text("Thora Construction", margin, 20);

    // Título do relatório
    pdf.setTextColor(0, 0, 0);
    pdf.setFontSize(16);
    pdf.text(report.name, margin, 50);

    // Informações
    pdf.setFontSize(10);
    pdf.text(`Tipo: ${typeLabels[report.type as keyof typeof typeLabels].label}`, margin, 65);
    pdf.text(`Projeto: ${report.orcamentoName}`, margin, 75);
    pdf.text(`Data: ${report.createdAt}`, margin, 85);

    // Conteúdo simulado baseado no tipo
    let yPos = 100;
    pdf.setFontSize(12);
    pdf.setFont(undefined, "bold");
    pdf.text("Resumo Executivo", margin, yPos);

    pdf.setFontSize(10);
    pdf.setFont(undefined, "normal");

    if (report.type === "budget") {
      const content = [
        "Total do Orçamento: R$ 2.450.000,00",
        "Número de Itens: 245",
        "Item Mais Caro: Concreto Estrutural - R$ 67.500,00",
        "Item Mais Barato: Parafusos - R$ 2.500,00",
        "Margem Sugerida: 15-20%",
      ];
      yPos += 15;
      content.forEach((line) => {
        pdf.text(`• ${line}`, margin + 5, yPos);
        yPos += 8;
      });
    } else if (report.type === "curva-abc") {
      const content = [
        "Classe A: 9 itens (77% do valor)",
        "Classe B: 15 itens (18% do valor)",
        "Classe C: 221 itens (5% do valor)",
        "Itens críticos identificados: 24",
        "Recomendação: Focar controle em Classe A e B",
      ];
      yPos += 15;
      content.forEach((line) => {
        pdf.text(`• ${line}`, margin + 5, yPos);
        yPos += 8;
      });
    } else if (report.type === "comparison") {
      const content = [
        "Orçado: R$ 2.450.000,00",
        "Executado: R$ 2.380.000,00",
        "Diferença: -R$ 70.000,00 (-2.9%)",
        "Itens dentro do orçado: 236 de 245",
        "Variação média: 1.2%",
      ];
      yPos += 15;
      content.forEach((line) => {
        pdf.text(`• ${line}`, margin + 5, yPos);
        yPos += 8;
      });
    } else if (report.type === "financial") {
      const content = [
        "Desembolso Estimado: R$ 2.450.000,00",
        "Fluxo Mensal (6 meses): ~R$ 408.333,33",
        "Pico de Gastos: Mês 3 (Estrutura)",
        "Reserva Recomendada: 10-15% (R$ 245.000-367.500)",
        "Índice de Rentabilidade: 18%",
      ];
      yPos += 15;
      content.forEach((line) => {
        pdf.text(`• ${line}`, margin + 5, yPos);
        yPos += 8;
      });
    }

    // Rodapé
    pdf.setFontSize(8);
    pdf.setTextColor(128, 128, 128);
    pdf.text(
      `Gerado em ${new Date().toLocaleString("pt-BR")}`,
      margin,
      pageHeight - 10
    );

    // Salvar PDF
    pdf.save(`${report.name.replace(/\s+/g, "_")}.pdf`);
  };

  const handleDeleteReport = (id: string) => {
    if (window.confirm("Tem certeza que deseja deletar este relatório?")) {
      setReports(reports.filter((r) => r.id !== id));
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Relatórios</h1>
            <p className="text-slate-600 text-sm">
              Gerencie e baixe relatórios em PDF
            </p>
          </div>
          <button
            onClick={() => navigate("/orcamento")}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition font-medium"
          >
            <Plus className="w-5 h-5" />
            Novo Relatório
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
            { value: "curva-abc", label: "Curva ABC" },
            { value: "comparison", label: "Comparativos" },
            { value: "financial", label: "Financeiros" },
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

        {/* Relatórios Grid */}
        {filteredReports.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-96 text-center">
            <FileText className="w-16 h-16 text-slate-300 mb-4" />
            <p className="text-slate-600 text-lg font-medium">
              Nenhum relatório encontrado
            </p>
            <p className="text-slate-500 text-sm mt-1">
              Crie um novo relatório para começar
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {filteredReports.map((report) => (
              <div
                key={report.id}
                className="bg-white rounded-lg border border-slate-200 p-6 hover:shadow-lg transition"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-2">
                      {report.name}
                    </h3>
                    <span
                      className={`inline-block px-3 py-1 rounded-full text-xs font-medium ${
                        typeLabels[report.type as keyof typeof typeLabels]
                          .color
                      }`}
                    >
                      {
                        typeLabels[report.type as keyof typeof typeLabels]
                          .label
                      }
                    </span>
                  </div>
                  <FileText className="w-8 h-8 text-slate-400" />
                </div>

                <div className="space-y-2 mb-6 text-sm text-slate-600">
                  <p className="flex items-center gap-2">
                    <BarChart3 className="w-4 h-4" />
                    {report.orcamentoName}
                  </p>
                  <p className="flex items-center gap-2">
                    <Clock className="w-4 h-4" />
                    {report.createdAt}
                  </p>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={() => handleGenerateReport(report)}
                    className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg transition font-medium"
                  >
                    <Download className="w-4 h-4" />
                    Baixar PDF
                  </button>
                  <button
                    onClick={() => setSelectedReport(report)}
                    className="flex-1 flex items-center justify-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 py-2 rounded-lg transition font-medium"
                  >
                    <Eye className="w-4 h-4" />
                    Visualizar
                  </button>
                  <button
                    onClick={() => handleDeleteReport(report.id)}
                    className="flex items-center justify-center gap-2 bg-red-100 hover:bg-red-200 text-red-700 px-4 py-2 rounded-lg transition font-medium"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
};

export default Reports;
