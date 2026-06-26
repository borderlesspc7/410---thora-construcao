import { AlertCircle, CheckCircle2, MinusCircle, XCircle } from "lucide-react";
import type { ResultadoLinhaAnalise } from "../../features/orcamentos/analiseOrcamento";
import { mensagensAnaliseLinha } from "../../features/orcamentos/analiseOrcamento";

type AnaliseOrcamentoStatusBadgeProps = {
  resultado?: ResultadoLinhaAnalise;
  compact?: boolean;
};

function statusConfig(status?: ResultadoLinhaAnalise["statusGeral"]) {
  switch (status) {
    case "aprovado":
      return {
        icon: CheckCircle2,
        className: "text-emerald-600",
        label: "Aprovado",
      };
    case "alerta":
      return {
        icon: AlertCircle,
        className: "text-amber-600",
        label: "Alerta",
      };
    case "reprovado":
      return {
        icon: XCircle,
        className: "text-red-600",
        label: "Reprovado",
      };
    case "ignorado":
      return {
        icon: MinusCircle,
        className: "text-slate-400",
        label: "Ignorado",
      };
    default:
      return null;
  }
}

export function AnaliseOrcamentoStatusBadge({
  resultado,
  compact = false,
}: AnaliseOrcamentoStatusBadgeProps) {
  if (!resultado) return <span className="text-slate-300">-</span>;

  const config = statusConfig(resultado.statusGeral);
  if (!config) return <span className="text-slate-300">-</span>;

  const Icon = config.icon;
  const mensagens = mensagensAnaliseLinha(resultado);
  const tooltip =
    resultado.statusGeral === "ignorado"
      ? resultado.motivoIgnorado ?? "Linha ignorada na análise"
      : mensagens.length > 0
        ? mensagens.join(" · ")
        : resultado.verificacoes.map((verificacao) => verificacao.mensagem).join(" · ");

  return (
    <span
      className={`inline-flex items-center gap-1 ${config.className}`}
      title={tooltip}
      aria-label={`Análise: ${config.label}`}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      {!compact ? <span className="text-xs font-medium">{config.label}</span> : null}
    </span>
  );
}
