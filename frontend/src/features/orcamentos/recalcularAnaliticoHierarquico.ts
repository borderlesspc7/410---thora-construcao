import type { LinhaAnalitica } from "./orcamentoAnalitico";
import { calcularLineTotalComBdi, parseEditableNumber } from "./recalcularCurvaABC";

export type AnaliticoEditableField = "quantidade" | "valorUnitario" | "bdi";

function findNextGrupoIndex(linhas: LinhaAnalitica[], afterIndex: number): number {
  for (let i = afterIndex + 1; i < linhas.length; i += 1) {
    if (linhas[i].tipoLinha === "grupo") return i;
  }
  return linhas.length;
}

/** Soma filhos de cada grupo (de dentro para fora) e atualiza valorTotal do grupo. */
export function recalcularGruposAnalitico(linhas: LinhaAnalitica[]): LinhaAnalitica[] {
  const next = linhas.map((linha) => ({ ...linha }));
  const grupoIndices: number[] = [];
  for (let i = 0; i < next.length; i += 1) {
    if (next[i].tipoLinha === "grupo") grupoIndices.push(i);
  }

  for (let gi = grupoIndices.length - 1; gi >= 0; gi -= 1) {
    const gIdx = grupoIndices[gi];
    const end = findNextGrupoIndex(next, gIdx);
    let sum = 0;
    for (let i = gIdx + 1; i < end; i += 1) {
      sum += next[i].valorTotal;
    }
    next[gIdx] = { ...next[gIdx], valorTotal: sum };
  }

  return next;
}

export function aplicarEdicaoAnalitica(
  linhas: LinhaAnalitica[],
  index: number,
  field: AnaliticoEditableField,
  value: string | number,
): LinhaAnalitica[] {
  if (index < 0 || index >= linhas.length) return linhas;

  const linha = linhas[index];
  if (linha.tipoLinha !== "item" && linha.tipoLinha !== "composicao") {
    return linhas;
  }

  const parsed = typeof value === "number" ? value : parseEditableNumber(value);

  const next = linhas.map((row, i) => {
    if (i !== index) return { ...row };
    const updated: LinhaAnalitica = {
      ...row,
      [field]: parsed,
    };
    updated.valorTotal = calcularLineTotalComBdi(
      updated.quantidade,
      updated.valorUnitario,
      updated.bdi,
    );
    return updated;
  });

  return recalcularGruposAnalitico(next);
}
