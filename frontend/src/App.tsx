import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import NovoOrcamento from "./pages/NovoOrcamento";
import ValidacaoOrcamento from "./pages/ValidacaoOrcamento";
import CurvaABC from "./pages/CurvaABC";
import Reports from "./pages/Reports";
import Analytics from "./pages/Analytics";
import SidebarLayout from "./components/SidebarLayout";

const App = () => {
  return (
    <SidebarLayout>
      <Routes>
        {/* Rota principal */}
        <Route path="/" element={<Dashboard />} />
        <Route path="/orcamento" element={<NovoOrcamento />} />
        <Route path="/validacao" element={<ValidacaoOrcamento />} />
        <Route path="/curva-abc/:uploadId" element={<CurvaABC />} />
        <Route path="/relatorios" element={<Reports />} />
        <Route path="/analytics" element={<Analytics />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </SidebarLayout>
  );
};

export default App;
