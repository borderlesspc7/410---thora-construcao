import type { LinhaAnalitica } from "./orcamentoAnalitico";
import { parseEditableNumber } from "./recalcularCurvaABC";

const HALLUCINATION_PATTERNS = [
  /servi[cç]o de instala[cç][aã]o de cabos el[eé]tricos/i,
  /instala[cç][aã]o de cabos el[eé]tricos/i,
  /fornecimento de lumin[aá]rias?\s*led/i,
  /fornecimento de concreto usinado/i,
  /fornecimento de materiais de constru[cç][aã]o/i,
  /m[aã]o de obra para pintura/i,
  /pintura de paredes internas/i,
];

const GENERIC_UNCODED_PHANTOM_PREFIXES = [
  /^fornecimento de /i,
  /^m[aã]o de obra para /i,
  /^servi[cç]o de instala[cç][aã]o de /i,
];

function isHallucinatedRow(linha: {
  codigo: string;
  descricao: string;
  quantidade?: number;
  valorUnitario?: number;
}): boolean {
  if (linha.codigo.trim()) return false;
  const desc = linha.descricao.trim();
  if (!desc) return false;
  if (HALLUCINATION_PATTERNS.some((p) => p.test(desc))) return true;
  const descLower = desc.toLowerCase();
  if (GENERIC_UNCODED_PHANTOM_PREFIXES.some((p) => p.test(descLower))) return true;
  const qty = linha.quantidade ?? 0;
  const vu = linha.valorUnitario ?? 0;
  return (
    qty === 50 &&
    vu === 200 &&
    descLower.includes("concreto") &&
    descLower.includes("fornecimento")
  );
}

function extractGroupPrefix(itemNumero: string, descricao: string): string | null {
  for (const field of [itemNumero.trim(), descricao.trim()]) {
    if (!field) continue;
    const m = field.match(/^(\d+)/);
    if (m) return m[1];
    const mDesc = field.match(/^(\d+)\s*[-–—.\)]/);
    if (mDesc) return mDesc[1];
  }
  return null;
}

export function classifyTipoLinhaAnalitico(linha: {
  quantidade: number;
  valorUnitario: number;
  tipoLinha: LinhaAnalitica["tipoLinha"];
}): LinhaAnalitica["tipoLinha"] {
  if (linha.quantidade <= 0 && linha.valorUnitario <= 0) {
    return "grupo";
  }
  if (linha.tipoLinha === "composicao") return "composicao";
  return "item";
}

export function computeValorTotalLinha(
  quantidade: number,
  valorUnitario: number,
  bdi: number,
  tipoLinha: LinhaAnalitica["tipoLinha"],
  valorTotalExplicit = 0,
): number {
  if (tipoLinha === "grupo") return 0;
  if (quantidade > 0 && valorUnitario > 0) {
    return Math.round(quantidade * valorUnitario * (1 + bdi / 100) * 100) / 100;
  }
  return valorTotalExplicit > 0 ? valorTotalExplicit : 0;
}

/** Tipagem, totais, numeração PP.NN e rollup (espelha backend). */
export function normalizarLinhasAnaliticas(linhas: LinhaAnalitica[]): LinhaAnalitica[] {
  const rows = linhas
    .filter((l) => !isHallucinatedRow(l))
    .map((l) => ({ ...l }));

  let currentGroupPrefix = "";
  let childCounter = 1;
  let orphanGroupSeq = 0;

  for (const row of rows) {
    row.tipoLinha = classifyTipoLinhaAnalitico(row);

    if (row.tipoLinha === "grupo") {
      const prefix =
        extractGroupPrefix(row.itemNumero, row.descricao) ??
        String(++orphanGroupSeq);
      currentGroupPrefix = prefix;
      childCounter = 1;
      row.itemNumero = currentGroupPrefix;
      row.unidade = "";
      row.quantidade = 0;
      row.valorUnitario = 0;
      row.bdi = 0;
      row.valorTotal = 0;
      continue;
    }

    if (!currentGroupPrefix) {
      orphanGroupSeq += 1;
      currentGroupPrefix = String(orphanGroupSeq);
      childCounter = 1;
    }

    row.itemNumero = `${currentGroupPrefix}.${String(childCounter).padStart(2, "0")}`;
    childCounter += 1;

    row.valorTotal = computeValorTotalLinha(
      row.quantidade,
      row.valorUnitario,
      row.bdi,
      row.tipoLinha,
      row.valorTotal,
    );
  }

  for (let i = rows.length - 1; i >= 0; i -= 1) {
    if (rows[i].tipoLinha !== "grupo") continue;
    let sum = 0;
    for (let j = i + 1; j < rows.length && rows[j].tipoLinha !== "grupo"; j += 1) {
      sum += rows[j].valorTotal;
    }
    rows[i].valorTotal = Math.round(sum * 100) / 100;
  }

  return rows;
}

export function mapRawToLinhaAnaliticaNormalizada(raw: unknown, index: number): LinhaAnalitica | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;

  const descricao = String(item.descricao ?? item.description ?? "").trim();
  const codigo = String(item.codigo ?? item.code ?? "").trim();
  const quantidade = parseEditableNumber(item.quantidade ?? item.quantity ?? item.qty);
  const valorUnitario = parseEditableNumber(
    item.valor_unitario ?? item.unitValue ?? item.unitPrice ?? item.unit_com_bdi,
  );
  const bdi = parseEditableNumber(String(item.bdi ?? item.BDI ?? 0).replace("%", ""));

  let tipoLinha = String(item.tipo_linha ?? item.tipo ?? "item").toLowerCase() as LinhaAnalitica["tipoLinha"];
  if (tipoLinha !== "grupo" && tipoLinha !== "item" && tipoLinha !== "composicao") {
    tipoLinha = "item";
  }

  if (quantidade <= 0 && valorUnitario <= 0) {
    tipoLinha = "grupo";
  } else if (tipoLinha === "composicao") {
    tipoLinha = "composicao";
  } else {
    tipoLinha = "item";
  }

  if (!descricao && tipoLinha !== "grupo") {
    if (quantidade <= 0 && valorUnitario <= 0) return null;
  }

  const linha: LinhaAnalitica = {
    id: index + 1,
    itemNumero: String(item.item_numero ?? item.item ?? "").trim(),
    rotuloLinha: String(item.rotulo_linha ?? "").trim(),
    tipoLinha,
    codigo,
    banco: String(item.banco ?? "").trim(),
    descricao,
    tipoCategoria: String(item.tipo_categoria ?? item.tipoCategoria ?? "").trim(),
    unidade: String(item.unidade ?? item.unit ?? "").trim(),
    quantidade,
    bdi,
    porcentagem: parseEditableNumber(item.porcentagem ?? item.percentual),
    valorUnitario,
    valorTotal: 0,
  };

  if (isHallucinatedRow(linha)) return null;

  const valorTotalExplicit = parseEditableNumber(
    item.valor_total ?? item.totalValue ?? item.lineTotal ?? item.total_com_bdi,
  );
  linha.valorTotal = computeValorTotalLinha(
    quantidade,
    valorUnitario,
    bdi,
    tipoLinha,
    valorTotalExplicit,
  );

  return linha;
}

export function mapRawListToLinhasAnaliticasNormalizadas(rawItems: unknown[]): LinhaAnalitica[] {
  const linhas: LinhaAnalitica[] = [];
  for (let i = 0; i < rawItems.length; i += 1) {
    const linha = mapRawToLinhaAnaliticaNormalizada(rawItems[i], i);
    if (linha) linhas.push({ ...linha, id: linhas.length + 1 });
  }
  return normalizarLinhasAnaliticas(linhas);
}
