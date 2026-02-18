import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp,
  DollarSign,
  BarChart3,
  PieChart,
  Calendar,
  Filter,
  Download,
  RefreshCw,
} from "lucide-react";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface KPI {
  label: string;
  value: string;
  change: number;
  icon: React.ReactNode;
  color: string;
}

const Analytics: React.FC = () => {
  const navigate = useNavigate();
  const [dateRange, setDateRange] = useState("30days");
  const [selectedMetric, setSelectedMetric] = useState("all");

  // Dados simulados de gastos mensais
  const monthlyDataItems = [
    { month: "Jan", value: 245000, planned: 250000 },
    { month: "Fev", value: 380000, planned: 380000 },
    { month: "Mar", value: 520000, planned: 500000 },
    { month: "Abr", value: 410000, planned: 420000 },
    { month: "Mai", value: 350000, planned: 370000 },
    { month: "Jun", value: 280000, planned: 300000 },
  ];

  // Dados de distribuição por categoria
  const categoryData = [
    { name: "Estrutura", value: 890000, percentage: 36 },
    { name: "Alvenaria", value: 480000, percentage: 20 },
    { name: "Instalações", value: 420000, percentage: 17 },
    { name: "Acabamento", value: 380000, percentage: 15 },
    { name: "Outros", value: 280000, percentage: 12 },
  ];

  // Dados de fornecedores top
  const topSuppliers = [
    {
      name: "Fornecedor A",
      spent: 680000,
      percentage: 28,
      items: 87,
    },
    {
      name: "Fornecedor B",
      spent: 520000,
      percentage: 21,
      items: 64,
    },
    {
      name: "Fornecedor C",
      spent: 450000,
      percentage: 18,
      items: 52,
    },
    {
      name: "Fornecedor D",
      spent: 380000,
      percentage: 15,
      items: 45,
    },
    {
      name: "Outros",
      spent: 370000,
      percentage: 18,
      items: 152,
    },
  ];

  // Dados de variação de preços
  const priceVariationData = [
    { item: "Cimento", budgeted: 35.50, actual: 36.20, variance: 1.97 },
    { item: "Aço", budgeted: 3500, actual: 3480, variance: -0.57 },
    { item: "Blocos", budgeted: 15, actual: 15.80, variance: 5.33 },
    { item: "Areia", budgeted: 120, actual: 118, variance: -1.67 },
    { item: "Telha", budgeted: 850, actual: 870, variance: 2.35 },
  ];

  const COLORS = ["#1F4E78", "#2E7AD4", "#5B9BD5", "#9FC2E8", "#BFDBF7"];

  // KPIs
  const kpis: KPI[] = [
    {
      label: "Orçamento Total",
      value: "R$ 2.450.000",
      change: 0,
      icon: <DollarSign className="w-6 h-6" />,
      color: "bg-blue-500",
    },
    {
      label: "Gasto Realizado",
      value: "R$ 2.280.000",
      change: -7.1,
      icon: <TrendingUp className="w-6 h-6" />,
      color: "bg-green-500",
    },
    {
      label: "Saldo Disponível",
      value: "R$ 170.000",
      change: 6.9,
      icon: <BarChart3 className="w-6 h-6" />,
      color: "bg-purple-500",
    },
    {
      label: "Taxa de Utilização",
      value: "93.1%",
      change: 0,
      icon: <PieChart className="w-6 h-6" />,
      color: "bg-orange-500",
    },
  ];

  return (
    <div className="flex flex-col min-h-full bg-slate-50 pb-16">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-8 py-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">BI & Analytics</h1>
            <p className="text-slate-600 text-sm">
              Análise detalhada de custos e desempenho
            </p>
          </div>
          <button className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition font-medium">
            <Download className="w-5 h-5" />
            Exportar Dashboard
          </button>
        </div>

        {/* Filtros */}
        <div className="flex gap-3 items-center text-sm">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="px-3 py-1 border border-slate-200 rounded-lg text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="7days">Últimos 7 dias</option>
            <option value="30days">Últimos 30 dias</option>
            <option value="90days">Últimos 90 dias</option>
            <option value="all">Todo período</option>
          </select>
          <button className="flex items-center gap-2 px-3 py-1 hover:bg-slate-100 rounded-lg transition text-slate-700">
            <RefreshCw className="w-4 h-4" />
            Atualizar
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-8">
        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {kpis.map((kpi, idx) => (
            <div
              key={idx}
              className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm hover:shadow-md transition"
            >
              <div className="flex items-start justify-between mb-4">
                <div className={`${kpi.color} p-3 rounded-lg text-white`}>
                  {kpi.icon}
                </div>
                {kpi.change !== 0 && (
                  <span
                    className={`text-xs font-semibold px-2 py-1 rounded ${
                      kpi.change > 0
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    }`}
                  >
                    {kpi.change > 0 ? "+" : ""}{kpi.change}%
                  </span>
                )}
              </div>
              <p className="text-slate-600 text-sm mb-1">{kpi.label}</p>
              <p className="text-2xl font-bold text-slate-900">{kpi.value}</p>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* Orçado vs Executado */}
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-6">
              Orçado vs Executado
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={monthlyDataItems}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2E7AD4" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="#2E7AD4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="month" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip
                  formatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                  labelStyle={{ color: "#000" }}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#2E7AD4"
                  fillOpacity={1}
                  fill="url(#colorValue)"
                  name="Executado"
                />
                <Line
                  type="monotone"
                  dataKey="planned"
                  stroke="#f59e0b"
                  strokeDasharray="5 5"
                  name="Planejado"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Distribuição por Categoria */}
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-6">
              Distribuição por Categoria
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <RechartsPieChart>
                <Pie
                  data={categoryData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percentage }) =>
                    `${name} ${percentage}%`
                  }
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {categoryData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                />
              </RechartsPieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* Top Fornecedores */}
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-6">
              Top 5 Fornecedores
            </h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={topSuppliers}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip
                  formatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                />
                <Bar dataKey="spent" fill="#1F4E78" name="Gasto (R$)" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Variação de Preços */}
          <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900 mb-6">
              Variação de Preços (Top 5)
            </h3>
            <div className="space-y-4">
              {priceVariationData.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3 bg-slate-50 rounded-lg"
                >
                  <div>
                    <p className="font-medium text-slate-900">{item.item}</p>
                    <p className="text-xs text-slate-600">
                      Orçado: R$ {item.budgeted.toFixed(2)} | Atual: R${" "}
                      {item.actual.toFixed(2)}
                    </p>
                  </div>
                  <span
                    className={`font-bold px-3 py-1 rounded ${
                      item.variance > 0
                        ? "bg-red-100 text-red-700"
                        : "bg-green-100 text-green-700"
                    }`}
                  >
                    {item.variance > 0 ? "+" : ""}{item.variance.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Tabela de Fornecedores Detalhada */}
        <div className="bg-white rounded-lg border border-slate-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-slate-900 mb-6">
            Análise Detalhada de Fornecedores
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-6 py-4 text-left font-semibold text-slate-900">
                    Fornecedor
                  </th>
                  <th className="px-6 py-4 text-right font-semibold text-slate-900">
                    Gasto Total
                  </th>
                  <th className="px-6 py-4 text-right font-semibold text-slate-900">
                    % do Total
                  </th>
                  <th className="px-6 py-4 text-right font-semibold text-slate-900">
                    Itens
                  </th>
                  <th className="px-6 py-4 text-center font-semibold text-slate-900">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {topSuppliers.map((supplier, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition">
                    <td className="px-6 py-4 font-medium text-slate-900">
                      {supplier.name}
                    </td>
                    <td className="px-6 py-4 text-right text-slate-700">
                      R$ {(supplier.spent / 1000).toFixed(0)}k
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-24 bg-slate-200 rounded-full h-2">
                          <div
                            className="bg-blue-600 h-2 rounded-full"
                            style={{ width: `${supplier.percentage}%` }}
                          />
                        </div>
                        <span className="text-slate-700 font-medium w-12 text-right">
                          {supplier.percentage}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right text-slate-700">
                      {supplier.items}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className="inline-block px-3 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full">
                        Ativo
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Analytics;
