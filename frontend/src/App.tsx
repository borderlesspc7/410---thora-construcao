import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import NovoOrcamento from "./pages/NovoOrcamento";
import ValidacaoOrcamento from "./pages/ValidacaoOrcamento";
import CurvaABC from "./pages/CurvaABC";
import ListaAnalises from "./pages/ListaAnalises";
import OrcamentoAnalitico from "./pages/OrcamentoAnalitico";
import OrcamentoSintetico from "./pages/OrcamentoSintetico";
import CatalogoProdutos from "./pages/CatalogoProdutos";
import BDICalculator from "./pages/BDICalculator";
import Reports from "./pages/Reports";
import AnaliseDetalhada from "./pages/AnaliseDetalhada";
import TesteAnaliseOrcamento from "./pages/TesteAnaliseOrcamento";
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
        <Route path="/lista-analises" element={<ListaAnalises />} />
        <Route path="/orcamento-analitico/:uploadId" element={<OrcamentoAnalitico />} />
        <Route path="/orcamento-analitico" element={<OrcamentoAnalitico />} />
        <Route path="/orcamento-sintetico/:uploadId" element={<OrcamentoSintetico />} />
        <Route path="/orcamento-sintetico" element={<OrcamentoSintetico />} />
        <Route
          path="/analise-detalhada/:uploadId"
          element={<AnaliseDetalhada />}
        />
        <Route path="/catalogo" element={<CatalogoProdutos />} />
        <Route path="/bdi" element={<BDICalculator />} />
        <Route path="/bdi/:uploadId" element={<BDICalculator />} />
        <Route path="/relatorios" element={<Reports />} />
        <Route path="/teste-analise" element={<TesteAnaliseOrcamento />} />
        <Route path="/analytics" element={<Navigate to="/" replace />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default App;
