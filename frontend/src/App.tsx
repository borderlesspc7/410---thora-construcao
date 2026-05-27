import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import NovoOrcamento from "./pages/NovoOrcamento";
import ValidacaoOrcamento from "./pages/ValidacaoOrcamento";
import CurvaABC from "./pages/CurvaABC";
import OrcamentoAnalitico from "./pages/OrcamentoAnalitico";
import Reports from "./pages/Reports";
import AnaliseDetalhada from "./pages/AnaliseDetalhada";
import Login from "./pages/Login";
import Cadastro from "./pages/Cadastro";
import { ProtectedApp } from "./features/auth/ProtectedApp";

const App = () => {
  return (
    <Routes>
      {/* Público */}
      <Route path="/login" element={<Login />} />
      <Route path="/cadastro" element={<Cadastro />} />

      {/* App protegido */}
      <Route element={<ProtectedApp />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/orcamento" element={<NovoOrcamento />} />
        <Route path="/validacao/:uploadId" element={<ValidacaoOrcamento />} />
        <Route path="/validacao" element={<Navigate to="/orcamento" replace />} />
        <Route path="/curva-abc/:uploadId" element={<CurvaABC />} />
        <Route path="/orcamento-analitico/:uploadId" element={<OrcamentoAnalitico />} />
        <Route path="/orcamento-analitico" element={<OrcamentoAnalitico />} />
        <Route
          path="/analise-detalhada/:uploadId"
          element={<AnaliseDetalhada />}
        />
        <Route path="/relatorios" element={<Reports />} />
        <Route path="/analytics" element={<Navigate to="/" replace />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default App;
