import { isLinhaAnalisavel, motivoExclusaoLinha } from "./filtrarLinhas";
import { analisarMemoriaCalculo } from "./memoriaCalculo";
import {
  ANALISE_ORCAMENTO_VERSAO,
  CONTEXTO_PADRAO,
  type ContextoAnaliseOrcamento,
  type LinhaOrcamentoEntrada,
  type ResultadoLinhaAnalise,
  type VerificacaoLinha,
} from "./types";

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function resolveContexto(contexto?: ContextoAnaliseOrcamento) {
  return {
    bdiGlobalPercent: contexto?.bdiGlobalPercent ?? CONTEXTO_PADRAO.bdiGlobalPercent,
    toleranciaMonetaria: contexto?.toleranciaMonetaria ?? CONTEXTO_PADRAO.toleranciaMonetaria,
    toleranciaPercentual: contexto?.toleranciaPercentual ?? CONTEXTO_PADRAO.toleranciaPercentual,
  };
}

function compararValores(
  calculado: number,
  informado: number,
  toleranciaMonetaria: number,
): { ok: boolean; diferenca: number } {
  const diferenca = Math.abs(calculado - informado);
  return { ok: diferenca <= toleranciaMonetaria, diferenca };
}

function statusGeralFromVerificacoes(verificacoes: VerificacaoLinha[]): ResultadoLinhaAnalise["statusGeral"] {
  const hasErro = verificacoes.some(
    (verificacao) =>
      verificacao.severidade === "erro" &&
      (verificacao.status === "divergente" || verificacao.status === "alerta"),
  );
  if (hasErro) return "reprovado";

  const hasAlerta = verificacoes.some(
    (verificacao) =>
      verificacao.severidade === "alerta" &&
      (verificacao.status === "divergente" || verificacao.status === "alerta"),
  );
  if (hasAlerta) return "alerta";

  return "aprovado";
}

export function analisarLinhaOrcamento(
  linha: LinhaOrcamentoEntrada,
  contexto?: ContextoAnaliseOrcamento,
): ResultadoLinhaAnalise {
  const resolved = resolveContexto(contexto);
  const motivoIgnorado = motivoExclusaoLinha(linha);

  if (motivoIgnorado || !isLinhaAnalisavel(linha)) {
    return {
      linhaId: linha.id,
      itemNumero: linha.itemNumero,
      descricao: linha.descricao,
      statusGeral: "ignorado",
      motivoIgnorado: motivoIgnorado ?? "Linha sem dados suficientes para análise",
      verificacoes: [],
    };
  }

  const verificacoes: VerificacaoLinha[] = [];

  const camposFaltantes: string[] = [];
  if (!linha.descricao.trim()) camposFaltantes.push("descrição");
  if (!linha.unidade.trim()) camposFaltantes.push("unidade");
  if (linha.quantidade <= 0) camposFaltantes.push("quantidade");
  if (linha.precoUnitario <= 0) camposFaltantes.push("preço unitário");

  verificacoes.push({
    regraId: "CAMPOS_OBRIGATORIOS",
    status: camposFaltantes.length === 0 ? "ok" : "divergente",
    severidade: camposFaltantes.length === 0 ? "info" : "erro",
    mensagem:
      camposFaltantes.length === 0
        ? "Campos obrigatórios preenchidos."
        : `Campos obrigatórios ausentes: ${camposFaltantes.join(", ")}.`,
  });

  const subtotalCalculado = roundMoney(linha.quantidade * linha.precoUnitario);
  const subtotalInformado =
    linha.precoTotalSemBdi > 0 ? linha.precoTotalSemBdi : subtotalCalculado;
  const subtotalCheck = compararValores(
    subtotalCalculado,
    subtotalInformado,
    resolved.toleranciaMonetaria,
  );

  verificacoes.push({
    regraId: "CALC_SUBTOTAL",
    status: subtotalCheck.ok ? "ok" : "divergente",
    severidade: subtotalCheck.ok ? "info" : "erro",
    valorCalculado: subtotalCalculado,
    valorInformado: subtotalInformado,
    diferenca: roundMoney(subtotalCheck.diferenca),
    mensagem: subtotalCheck.ok
      ? `${linha.quantidade} × ${linha.precoUnitario} = ${subtotalCalculado}`
      : `Subtotal divergente: esperado ${subtotalCalculado}, informado ${subtotalInformado}.`,
  });

  if (linha.bdiPercent > 0) {
    const totalComBdiCalculado = roundMoney(subtotalInformado * (1 + linha.bdiPercent / 100));
    const totalComBdiInformado =
      linha.precoTotalComBdi > 0 ? linha.precoTotalComBdi : totalComBdiCalculado;
    const bdiCheck = compararValores(
      totalComBdiCalculado,
      totalComBdiInformado,
      resolved.toleranciaMonetaria,
    );

    verificacoes.push({
      regraId: "CALC_BDI",
      status: bdiCheck.ok ? "ok" : "divergente",
      severidade: bdiCheck.ok ? "info" : "erro",
      valorCalculado: totalComBdiCalculado,
      valorInformado: totalComBdiInformado,
      diferenca: roundMoney(bdiCheck.diferenca),
      mensagem: bdiCheck.ok
        ? `${subtotalInformado} × (1 + ${linha.bdiPercent}%) = ${totalComBdiCalculado}`
        : `Total c/ BDI divergente: esperado ${totalComBdiCalculado}, informado ${totalComBdiInformado}.`,
    });

    if (resolved.bdiGlobalPercent > 0) {
      const bdiGlobalCheck =
        Math.abs(linha.bdiPercent - resolved.bdiGlobalPercent) <= resolved.toleranciaPercentual;

      verificacoes.push({
        regraId: "BDI_GLOBAL",
        status: bdiGlobalCheck ? "ok" : "alerta",
        severidade: bdiGlobalCheck ? "info" : "alerta",
        valorCalculado: resolved.bdiGlobalPercent,
        valorInformado: linha.bdiPercent,
        diferenca: roundMoney(Math.abs(linha.bdiPercent - resolved.bdiGlobalPercent)),
        mensagem: bdiGlobalCheck
          ? `BDI ${linha.bdiPercent}% confere com o BDI global (${resolved.bdiGlobalPercent}%).`
          : `BDI da linha (${linha.bdiPercent}%) difere do BDI global (${resolved.bdiGlobalPercent}%).`,
      });
    }
  } else {
    verificacoes.push({
      regraId: "CALC_BDI",
      status: "nao_aplicavel",
      severidade: "info",
      mensagem: "BDI não informado na linha.",
    });
  }

  let memoriaCalculo;
  if (linha.observacoes.trim()) {
    memoriaCalculo =
      analisarMemoriaCalculo(
        linha.observacoes,
        linha.quantidade,
        linha.unidade,
        resolved.toleranciaMonetaria,
      ) ?? undefined;

    if (memoriaCalculo) {
      verificacoes.push({
        regraId: "MEMORIA_CALCULO",
        status: memoriaCalculo.bateComQuantidade ? "ok" : "alerta",
        severidade: memoriaCalculo.bateComQuantidade ? "info" : "alerta",
        valorCalculado: memoriaCalculo.resultadoExtraido ?? undefined,
        valorInformado: linha.quantidade,
        diferenca:
          memoriaCalculo.resultadoExtraido != null
            ? roundMoney(Math.abs(memoriaCalculo.resultadoExtraido - linha.quantidade))
            : undefined,
        mensagem: memoriaCalculo.explicacao,
      });
    } else {
      verificacoes.push({
        regraId: "MEMORIA_CALCULO",
        status: "nao_aplicavel",
        severidade: "info",
        mensagem: "Observações presentes, mas sem padrão numérico reconhecível.",
      });
    }
  }

  return {
    linhaId: linha.id,
    itemNumero: linha.itemNumero,
    descricao: linha.descricao,
    statusGeral: statusGeralFromVerificacoes(verificacoes),
    verificacoes,
    memoriaCalculo,
  };
}

export function getAnaliseOrcamentoVersao(): string {
  return ANALISE_ORCAMENTO_VERSAO;
}
