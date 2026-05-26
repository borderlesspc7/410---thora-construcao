import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Home,
  FileText,
  BarChart3,
  Menu,
  X,
  LogOut,
  Upload,
} from "lucide-react";
import { signOutCurrentUser } from "../features/auth/authService";

interface SidebarLayoutProps {
  children: React.ReactNode;
}

const SidebarLayout: React.FC<SidebarLayoutProps> = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  const isActive = (path: string) => {
    if (path === "/orcamento") {
      return (
        location.pathname === path ||
        location.pathname.startsWith(`${path}/`) ||
        location.pathname.startsWith("/validacao") ||
        location.pathname.startsWith("/curva-abc")
      );
    }
    return (
      location.pathname === path || location.pathname.startsWith(`${path}/`)
    );
  };

  const menuItems = [
    { path: "/", label: "Dashboard", icon: Home },
    { path: "/orcamento", label: "Curva ABC", icon: Upload },
    { path: "/relatorios", label: "Relatórios", icon: BarChart3 },
  ];

  const asideWidth = sidebarOpen ? "w-64" : "w-20";

  return (
    <div className="flex h-dvh max-h-dvh w-full overflow-hidden bg-slate-50">
      {mobileNavOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-900/45 backdrop-blur-[1px] lg:hidden"
          aria-label="Fechar menu"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-800/80 bg-linear-to-b from-slate-900 to-slate-800 text-white shadow-lg transition-transform duration-300 lg:static lg:translate-x-0 ${asideWidth} ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div
          className={`flex items-center justify-between border-b border-slate-700 px-6 py-6 ${
            !sidebarOpen && "px-2"
          }`}
        >
          {sidebarOpen && (
            <Link
              to="/"
              className="flex items-center gap-2"
              onClick={() => setMobileNavOpen(false)}
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500 font-bold">
                T
              </div>
              <span className="text-lg font-bold">Thora</span>
            </Link>
          )}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden rounded-lg p-2 transition hover:bg-slate-700 lg:inline-flex"
              aria-label={
                sidebarOpen ? "Recolher menu lateral" : "Expandir menu lateral"
              }
            >
              {sidebarOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
            <button
              type="button"
              className="rounded-lg p-2 transition hover:bg-slate-700 lg:hidden"
              aria-label="Fechar menu"
              onClick={() => setMobileNavOpen(false)}
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <nav className="flex-1 space-y-2 overflow-y-auto px-3 py-6">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMobileNavOpen(false)}
                className={`flex items-center gap-3 rounded-lg px-4 py-3 transition ${
                  active
                    ? "bg-blue-600 font-medium text-white"
                    : "text-slate-300 hover:bg-slate-700 hover:text-white"
                }`}
                title={!sidebarOpen ? item.label : undefined}
              >
                <Icon className="h-5 w-5 shrink-0" />
                {sidebarOpen && <span className="text-sm">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-slate-700 px-3 py-4">
          <button
            type="button"
            onClick={async () => {
              await signOutCurrentUser();
              navigate("/login", { replace: true });
            }}
            className={`flex w-full items-center gap-3 rounded-lg px-4 py-3 text-slate-300 transition hover:bg-slate-700 hover:text-white ${
              !sidebarOpen && "justify-center"
            }`}
            title={!sidebarOpen ? "Sair" : undefined}
          >
            <LogOut className="h-5 w-5 shrink-0" />
            {sidebarOpen && <span className="text-sm">Sair</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 shadow-sm lg:hidden">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100"
            aria-label="Abrir menu de navegação"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-semibold text-slate-900">Thora</span>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-y-contain">
          {children}
        </main>
      </div>
    </div>
  );
};

export default SidebarLayout;
