import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Home,
  FileText,
  BarChart3,
  TrendingUp,
  Brain,
  Menu,
  X,
  LogOut,
} from "lucide-react";

interface SidebarLayoutProps {
  children: React.ReactNode;
}

const SidebarLayout: React.FC<SidebarLayoutProps> = ({ children }) => {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + "/");
  };

  const menuItems = [
    { path: "/", label: "Dashboard", icon: Home },
    { path: "/orcamento", label: "Novo Orçamento", icon: FileText },
    { path: "/validacao", label: "Validação", icon: FileText },
    { path: "/analise-detalhada", label: "Análise Detalhada", icon: Brain },
    { path: "/relatorios", label: "Relatórios", icon: BarChart3 },
    { path: "/analytics", label: "BI & Analytics", icon: TrendingUp },
  ];

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? "w-64" : "w-20"
        } bg-gradient-to-b from-slate-900 to-slate-800 text-white shadow-lg transition-all duration-300 flex flex-col`}
      >
        {/* Logo */}
        <div
          className={`flex items-center justify-between px-6 py-6 border-b border-slate-700 ${
            !sidebarOpen && "px-2"
          }`}
        >
          {sidebarOpen && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center font-bold">
                T
              </div>
              <span className="font-bold text-lg">Thora</span>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 hover:bg-slate-700 rounded-lg transition"
          >
            {sidebarOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Menu Items */}
        <nav className="flex-1 px-3 py-8 space-y-3">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition ${
                  active
                    ? "bg-blue-600 text-white font-medium"
                    : "text-slate-300 hover:bg-slate-700 hover:text-white"
                }`}
                title={!sidebarOpen ? item.label : ""}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {sidebarOpen && <span className="text-sm">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* User Section */}
        <div className="px-3 py-4 border-t border-slate-700">
          <button
            className={`flex items-center gap-3 w-full px-4 py-3 rounded-lg text-slate-300 hover:bg-slate-700 hover:text-white transition ${
              !sidebarOpen && "justify-center"
            }`}
            title={!sidebarOpen ? "Sair" : ""}
          >
            <LogOut className="w-5 h-5 flex-shrink-0" />
            {sidebarOpen && <span className="text-sm">Sair</span>}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-y-auto overflow-x-hidden">
        {children}
      </div>
    </div>
  );
};

export default SidebarLayout;
