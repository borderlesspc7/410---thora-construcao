import type { LinhaAnalitica } from "./orcamentoAnalitico";
import { normalizarLinhasAnaliticas } from "./normalizarAnalitico";
import { parseEditableNumber } from "./recalcularCurvaABC";

export type AnaliticoEditableField = "quantidade" | "valorUnitario" | "bdi";

/** Soma filhos, totais Qtd×VU e tipagem de grupos. */
export function recalcularGruposAnalitico(linhas: LinhaAnalitica[]): LinhaAnalitica[] {
  return normalizarLinhasAnaliticas(linhas.map((linha) => ({ ...linha })));
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
    return updated;
  });

  return normalizarLinhasAnaliticas(next);
}
