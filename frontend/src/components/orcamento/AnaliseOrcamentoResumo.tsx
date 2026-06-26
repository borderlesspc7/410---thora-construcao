import type { ResultadoAnaliseOrcamento } from "../../features/orcamentos/analiseOrcamento";

type AnaliseOrcamentoResumoProps = {
  resultado: ResultadoAnaliseOrcamento;
};

export function AnaliseOrcamentoResumo({ resultado }: AnaliseOrcamentoResumoProps) {
  const { resumo } = resultado;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-emerald-700">Aprovadas</p>
        <p className="text-xl font-semibold text-emerald-900">{resumo.aprovadas}</p>
      </div>
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-amber-700">Alertas</p>
        <p className="text-xl font-semibold text-amber-900">{resumo.comAlerta}</p>
      </div>
      <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-red-700">Reprovadas</p>
        <p className="text-xl font-semibold text-red-900">{resumo.reprovadas}</p>
      </div>
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-600">Ignoradas</p>
        <p className="text-xl font-semibold text-slate-900">{resumo.linhasIgnoradas}</p>
      </div>
    </div>
  );
}
