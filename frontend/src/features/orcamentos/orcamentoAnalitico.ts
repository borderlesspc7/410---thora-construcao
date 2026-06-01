import { parseEditableNumber, resolveTipoLinha } from "./recalcularCurvaABC";

export type LinhaAnalitica = {
  id: number;
  itemNumero: string;
  rotuloLinha: string;
  tipoLinha: "grupo" | "item" | "composicao";
  codigo: string;
  banco: string;
  descricao: string;
  tipoCategoria: string;
  unidade: string;
  quantidade: number;
  bdi: number;
  porcentagem: number;
  valorUnitario: number;
  valorTotal: number;
};

export function mapRawToLinhaAnalitica(raw: unknown, index: number): LinhaAnalitica | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;

  const descricao = String(item.descricao ?? item.description ?? "").trim();
  const tipoLinha = resolveTipoLinha({
    tipo: String(item.tipo ?? item.tipo_linha ?? "item"),
    tipo_linha: String(item.tipo_linha ?? item.tipo ?? "item"),
  });

  if (!descricao && tipoLinha === "item") return null;

  const quantidade = parseEditableNumber(
    item.quantidade ?? item.quantity ?? item.qty,
  );
  const valorUnitario = parseEditableNumber(
    item.valor_unitario ?? item.unitValue ?? item.unitPrice ?? item.unit_com_bdi,
  );
  const bdi = parseEditableNumber(String(item.bdi ?? item.BDI ?? 0).replace("%", ""));
  const valorTotalExplicit = parseEditableNumber(
    item.valor_total ?? item.totalValue ?? item.lineTotal ?? item.total_com_bdi,
  );
  const valorTotal =
    valorTotalExplicit > 0
      ? valorTotalExplicit
      : quantidade * valorUnitario * (1 + bdi / 100);

  return {
    id: index + 1,
    itemNumero: String(item.item_numero ?? item.item ?? "").trim(),
    rotuloLinha: String(item.rotulo_linha ?? "").trim(),
    tipoLinha,
    codigo: String(item.codigo ?? item.code ?? "").trim(),
    banco: String(item.banco ?? "").trim(),
    descricao,
    tipoCategoria: String(item.tipo_categoria ?? item.tipoCategoria ?? "").trim(),
    unidade: String(item.unidade ?? item.unit ?? "").trim(),
    quantidade,
    bdi,
    porcentagem: parseEditableNumber(item.porcentagem ?? item.percentual),
    valorUnitario,
    valorTotal,
  };
}

export function mapRawListToLinhasAnaliticas(rawItems: unknown[]): LinhaAnalitica[] {
  const linhas: LinhaAnalitica[] = [];
  for (let i = 0; i < rawItems.length; i += 1) {
    const linha = mapRawToLinhaAnalitica(rawItems[i], i);
    if (linha) linhas.push({ ...linha, id: linhas.length + 1 });
  }
  return linhas;
}

/** Reexportado para uso na tela analítica. */
export { parseEditableNumber } from "./recalcularCurvaABC";

export function linhasToExportPayload(linhas: LinhaAnalitica[]): Record<string, unknown>[] {
  return linhas.map((linha) => ({
    item: linha.itemNumero,
    item_numero: linha.itemNumero,
    rotulo_linha: linha.rotuloLinha || null,
    tipo: linha.tipoLinha,
    tipo_linha: linha.tipoLinha,
    tipo_categoria: linha.tipoCategoria || null,
    banco: linha.banco,
    codigo: linha.codigo,
    code: linha.codigo,
    descricao: linha.descricao,
    description: linha.descricao,
    unidade: linha.unidade,
    unit: linha.unidade,
    quantidade: linha.quantidade,
    qty: linha.quantidade,
    bdi: linha.bdi,
    BDI: linha.bdi,
    porcentagem: linha.porcentagem,
    valor_unitario: linha.valorUnitario,
    unitPrice: linha.valorUnitario,
    valor_total: linha.valorTotal,
    totalValue: linha.valorTotal,
  }));
}

export function calcularResumoAnalitico(linhas: LinhaAnalitica[]) {
  const itens = linhas.filter((l) => l.tipoLinha === "item");
  const grupos = linhas.filter((l) => l.tipoLinha === "grupo");
  const composicoes = linhas.filter((l) => l.tipoLinha === "composicao");
  const totalGeral = itens.reduce((acc, l) => acc + l.valorTotal, 0);

  return {
    totalLinhas: linhas.length,
    totalGrupos: grupos.length,
    totalItens: itens.length,
    totalComposicoes: composicoes.length,
    totalGeral,
  };
}
