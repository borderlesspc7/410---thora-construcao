import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  analisarOrcamentoFromRaw,
  type ResultadoLinhaAnalise,
} from "../features/orcamentos/analiseOrcamento";
import { AnaliseOrcamentoResumo } from "../components/orcamento/AnaliseOrcamentoResumo";
import { AnaliseOrcamentoStatusBadge } from "../components/orcamento/AnaliseOrcamentoStatusBadge";

/** Dados de exemplo baseados na planilha que vocês enviaram na conversa. */
const LINHAS_DEMO = [
  {
    item_numero: "1",
    descricao: "SERVIÇOS PRELIMINARES E CANTEIRO",
    tipo_linha: "grupo",
  },
  {
    item_numero: "1.2",
    descricao: "INSTALAÇÕES DA OBRA CANTEIRO CENTRAL E BOTA ESPERA",
    tipo_linha: "grupo",
  },
  {
    item_numero: "1.2.1",
    banco: "ORSE-M",
    codigo: "9936-M",
    descricao: "LIMPEZA MECANIZADA DO TERRENO COM RETROESCAVADEIRA (VEGETAÇÃO RASTEIRA) SEM CARGA E DESCARGA",
    unidade: "M2",
    quantidade: 600,
    preco_unitario: 0.52,
    preco_total_sem_bdi: 312,
    bdi: 21.22,
    preco_total_com_bdi: 378.2,
    observacoes:
      "DIMENSIONAMENTO DE CANTEIRO DE OBRAS CONF. NR-18 E NR-24 ÁREA CANTEIRO 400 M2 + 200 M2 BOTA-ESPERA. (CÁLCULO ORÇAMENTO)",
    tipo_linha: "item",
  },
  {
    item_numero: "1.2.2",
    banco: "SINAPI",
    codigo: "100979",
    descricao: "ITEM COM SUBTOTAL ERRADO (DEMO)",
    unidade: "UN",
    quantidade: 10,
    preco_unitario: 100,
    preco_total_sem_bdi: 500,
    bdi: 21.22,
    preco_total_com_bdi: 605.5,
    tipo_linha: "item",
  },
  {
    item_numero: "1.2.3",
    banco: "SINAPI",
    codigo: "100980",
    descricao: "ITEM COM MEMÓRIA DIVERGENTE (DEMO)",
    unidade: "M2",
    quantidade: 600,
    preco_unitario: 1,
    preco_total_sem_bdi: 600,
    bdi: 21.22,
    preco_total_com_bdi: 727.32,
    observacoes: "ÁREA 300 M2 + 200 M2",
    tipo_linha: "item",
  },
  {
    descricao: "ITEM",
    preco_total_com_bdi: 396490.67,
    valor_total: 396490.67,
    tipo_linha: "grupo",
  },
];

function detalhesLinha(linha: ResultadoLinhaAnalise): string {
  if (linha.statusGeral === "ignorado") {
    return linha.motivoIgnorado ?? "Ignorado";
  }
  return linha.verificacoes.map((v) => v.mensagem).join(" · ");
}

export default function TesteAnaliseOrcamento() {
  const resultado = useMemo(() => analisarOrcamentoFromRaw(LINHAS_DEMO), []);

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar ao dashboard
        </Link>

        <div className="mb-6 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm text-violet-950">
          <strong>Página de teste rápido</strong> — usa dados fixos da planilha de exemplo.
          Abra <code className="rounded bg-white px-1">/teste-analise</code> após login.
          Esperado: 1.2.1 <em>aprovado</em>, 1.2.2 <em>reprovado</em>, 1.2.3 <em>alerta</em>,
          grupos/subtotal <em>ignorados</em>.
        </div>

        <h1 className="text-2xl font-bold text-slate-900">Teste — Análise determinística</h1>
        <p className="mt-1 text-sm text-slate-600">Sem IA · roda 100% no navegador</p>

        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <AnaliseOrcamentoResumo resultado={resultado} />
        </div>

        <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Item</th>
                <th className="px-4 py-3">Descrição</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3">Detalhes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {resultado.linhas.map((linha) => (
                <tr key={String(linha.linhaId)}>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
                    {linha.itemNumero || "—"}
                  </td>
                  <td className="max-w-md px-4 py-3">{linha.descricao || "—"}</td>
                  <td className="px-4 py-3 text-center">
                    <AnaliseOrcamentoStatusBadge resultado={linha} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">{detalhesLinha(linha)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
