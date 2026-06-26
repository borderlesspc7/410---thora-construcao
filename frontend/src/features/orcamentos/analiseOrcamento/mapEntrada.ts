import type { LinhaAnalitica } from "../orcamentoAnalitico";
import {
  calcularLineTotalComBdi,
  parseEditableNumber,
  resolveTipoLinha,
  type OrcamentoItem,
} from "../recalcularCurvaABC";
import type { LinhaOrcamentoEntrada } from "./types";

function extractObservacoes(raw: Record<string, unknown>): string {
  return String(
    raw.observacoes ??
      raw.observação ??
      raw.observacao ??
      raw.OBSERVAÇÕES ??
      raw.OBSERVACOES ??
      raw.notas ??
      "",
  ).trim();
}

function resolvePrecosFromRaw(
  raw: Record<string, unknown>,
  quantidade: number,
  bdiPercent: number,
): Pick<LinhaOrcamentoEntrada, "precoUnitario" | "precoTotalSemBdi" | "precoTotalComBdi"> {
  const precoUnitarioExplicit = parseEditableNumber(
    raw.preco_unitario_sem_bdi ??
      raw.preco_unitario ??
      raw.valor_unitario_sem_bdi ??
      raw.unitPrice ??
      raw.valor_unitario,
  );
  const precoTotalSemBdiExplicit = parseEditableNumber(
    raw.preco_total_sem_bdi ??
      raw.preco_total_s_bdi ??
      raw.valor_total_sem_bdi ??
      raw.subtotal,
  );
  const precoTotalComBdiExplicit = parseEditableNumber(
    raw.preco_total_com_bdi ??
      raw.preco_total_c_bdi ??
      raw.valor_total_com_bdi ??
      raw.total_com_bdi ??
      raw.valor_total ??
      raw.totalValue ??
      raw.lineTotal,
  );

  let precoUnitario = precoUnitarioExplicit;
  let precoTotalSemBdi = precoTotalSemBdiExplicit;
  let precoTotalComBdi = precoTotalComBdiExplicit;

  if (precoTotalSemBdi <= 0 && quantidade > 0 && precoUnitario > 0) {
    precoTotalSemBdi = quantidade * precoUnitario;
  }
  if (precoUnitario <= 0 && precoTotalSemBdi > 0 && quantidade > 0) {
    precoUnitario = precoTotalSemBdi / quantidade;
  }
  if (precoTotalComBdi <= 0 && precoTotalSemBdi > 0 && bdiPercent > 0) {
    precoTotalComBdi = precoTotalSemBdi * (1 + bdiPercent / 100);
  }
  if (precoTotalComBdi <= 0 && quantidade > 0 && precoUnitario > 0) {
    precoTotalComBdi = calcularLineTotalComBdi(quantidade, precoUnitario, bdiPercent);
  }

  return {
    precoUnitario: Math.round(precoUnitario * 10000) / 10000,
    precoTotalSemBdi: Math.round(precoTotalSemBdi * 100) / 100,
    precoTotalComBdi: Math.round(precoTotalComBdi * 100) / 100,
  };
}

export function mapRawToLinhaOrcamentoEntrada(
  raw: unknown,
  index: number,
  fallbackId?: string | number,
): LinhaOrcamentoEntrada | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;

  const quantidade = parseEditableNumber(item.quantidade ?? item.quantity ?? item.qty);
  const bdiPercent = parseEditableNumber(String(item.bdi ?? item.BDI ?? 0).replace("%", ""));
  const precos = resolvePrecosFromRaw(item, quantidade, bdiPercent);
  const tipoLinha = resolveTipoLinha({
    tipo: String(item.tipo ?? item.tipo_linha ?? "item"),
    tipo_linha: String(item.tipo_linha ?? item.tipo ?? "item"),
  });

  return {
    id: fallbackId ?? item.id ?? index + 1,
    itemNumero: String(item.item_numero ?? item.item ?? "").trim(),
    banco: String(item.banco ?? item.fonte ?? "").trim(),
    codigo: String(item.codigo ?? item.code ?? "").trim(),
    descricao: String(item.descricao ?? item.description ?? "").trim(),
    unidade: String(item.unidade ?? item.unit ?? "").trim(),
    quantidade,
    bdiPercent,
    observacoes: extractObservacoes(item),
    tipoLinha,
    ...precos,
  };
}

export function mapOrcamentoItemToLinhaEntrada(item: OrcamentoItem): LinhaOrcamentoEntrada {
  const precoTotalSemBdi = item.qty > 0 && item.unitPrice > 0 ? item.qty * item.unitPrice : 0;
  const precoTotalComBdi =
    item.lineTotal > 0
      ? item.lineTotal
      : calcularLineTotalComBdi(item.qty, item.unitPrice, item.bdi);

  return {
    id: item.id,
    itemNumero: String(item.item ?? "").trim(),
    banco: String(item.banco ?? "").trim(),
    codigo: String(item.code ?? "").trim(),
    descricao: String(item.description ?? "").trim(),
    unidade: String(item.unit ?? "").trim(),
    quantidade: item.qty,
    precoUnitario: item.unitPrice,
    precoTotalSemBdi: Math.round(precoTotalSemBdi * 100) / 100,
    bdiPercent: item.bdi,
    precoTotalComBdi: Math.round(precoTotalComBdi * 100) / 100,
    observacoes: "",
    tipoLinha: resolveTipoLinha({ tipo: item.tipo }),
  };
}

export function mapLinhaAnaliticaToEntrada(linha: LinhaAnalitica, observacoes = ""): LinhaOrcamentoEntrada {
  const precoTotalComBdi = linha.valorTotal;
  const precoTotalSemBdi =
    linha.bdi > 0 && precoTotalComBdi > 0
      ? precoTotalComBdi / (1 + linha.bdi / 100)
      : linha.quantidade * linha.valorUnitario;
  const precoUnitario =
    linha.quantidade > 0 && precoTotalSemBdi > 0
      ? precoTotalSemBdi / linha.quantidade
      : linha.valorUnitario;

  return {
    id: linha.id,
    itemNumero: linha.itemNumero,
    banco: linha.banco,
    codigo: linha.codigo,
    descricao: linha.descricao,
    unidade: linha.unidade,
    quantidade: linha.quantidade,
    precoUnitario: Math.round(precoUnitario * 10000) / 10000,
    precoTotalSemBdi: Math.round(precoTotalSemBdi * 100) / 100,
    bdiPercent: linha.bdi,
    precoTotalComBdi: Math.round(precoTotalComBdi * 100) / 100,
    observacoes,
    tipoLinha: linha.tipoLinha,
  };
}

export function mergeObservacoesNasLinhas(
  linhas: LinhaOrcamentoEntrada[],
  rawItems: unknown[],
): LinhaOrcamentoEntrada[] {
  const observacoesPorChave = new Map<string, string>();

  for (const raw of rawItems) {
    const entrada = mapRawToLinhaOrcamentoEntrada(raw, 0);
    if (!entrada) continue;
    const obs = entrada.observacoes.trim();
    if (!obs) continue;
    const chaveCodigo = `${entrada.itemNumero}|${entrada.codigo}`.toLowerCase();
    const chaveItem = entrada.itemNumero.toLowerCase();
    observacoesPorChave.set(chaveCodigo, obs);
    if (!observacoesPorChave.has(chaveItem)) {
      observacoesPorChave.set(chaveItem, obs);
    }
  }

  return linhas.map((linha) => {
    if (linha.observacoes.trim()) return linha;
    const chaveCodigo = `${linha.itemNumero}|${linha.codigo}`.toLowerCase();
    const chaveItem = linha.itemNumero.toLowerCase();
    const observacoes =
      observacoesPorChave.get(chaveCodigo) ?? observacoesPorChave.get(chaveItem) ?? "";
    return observacoes ? { ...linha, observacoes } : linha;
  });
}

export function inferirBdiGlobal(linhas: LinhaOrcamentoEntrada[]): number {
  const valores = linhas
    .map((linha) => linha.bdiPercent)
    .filter((bdi) => bdi > 0);
  if (valores.length === 0) return 0;

  const frequencia = new Map<number, number>();
  for (const valor of valores) {
    const arredondado = Math.round(valor * 100) / 100;
    frequencia.set(arredondado, (frequencia.get(arredondado) ?? 0) + 1);
  }

  let melhorValor = 0;
  let melhorContagem = 0;
  for (const [valor, contagem] of frequencia.entries()) {
    if (contagem > melhorContagem) {
      melhorValor = valor;
      melhorContagem = contagem;
    }
  }
  return melhorValor;
}
