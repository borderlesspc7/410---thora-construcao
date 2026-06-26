import { parseEditableNumber } from "../recalcularCurvaABC";
import type { MemoriaCalculoResultado } from "./types";

const VALOR_UNIDADE_PATTERN =
  /(\d+(?:[.,]\d+)?)\s*(M2|M³|M3|KM|UN|UND|CHP|CHI|MÊS|MES|M)\b/gi;
const SOMA_PATTERN =
  /(\d+(?:[.,]\d+)?)\s*(M2|M³|M3|KM|UN|UND|CHP|CHI|MÊS|MES|M)?\s*\+\s*(\d+(?:[.,]\d+)?)\s*(M2|M³|M3|KM|UN|UND|CHP|CHI|MÊS|MES|M)?/gi;

function normalizeUnidade(unidade: string): string {
  return unidade
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toUpperCase()
    .replace("M³", "M3")
    .replace("MES", "MÊS");
}

function unidadesCompativeis(a: string, b: string): boolean {
  const left = normalizeUnidade(a);
  const right = normalizeUnidade(b);
  if (!left || !right) return true;
  return left === right;
}

function extrairValoresComUnidade(texto: string): Array<{ valor: number; unidade: string }> {
  const resultados: Array<{ valor: number; unidade: string }> = [];
  for (const match of texto.matchAll(VALOR_UNIDADE_PATTERN)) {
    const valor = parseEditableNumber(match[1]);
    const unidade = normalizeUnidade(match[2] ?? "");
    if (valor > 0) resultados.push({ valor, unidade });
  }
  return resultados;
}

function tentarSomarPares(texto: string): { total: number; unidade: string | null; expressoes: string[] } | null {
  const expressoes: string[] = [];
  let total = 0;
  let unidadeReferencia: string | null = null;
  let encontrou = false;

  for (const match of texto.matchAll(SOMA_PATTERN)) {
    const esquerda = parseEditableNumber(match[1]);
    const unidadeEsquerda = normalizeUnidade(match[2] ?? "");
    const direita = parseEditableNumber(match[3]);
    const unidadeDireita = normalizeUnidade(match[4] ?? unidadeEsquerda);

    if (esquerda <= 0 || direita <= 0) continue;

    const unidade = unidadeDireita || unidadeEsquerda;
    if (unidadeReferencia && unidade && !unidadesCompativeis(unidadeReferencia, unidade)) {
      continue;
    }

    unidadeReferencia = unidadeReferencia ?? unidade ?? null;
    total += esquerda + direita;
    expressoes.push(`${match[1]} ${unidadeEsquerda || unidade} + ${match[3]} ${unidadeDireita || unidade}`.trim());
    encontrou = true;
  }

  if (!encontrou) return null;
  return { total, unidade: unidadeReferencia, expressoes };
}

export function analisarMemoriaCalculo(
  observacoes: string,
  quantidade: number,
  unidadeLinha: string,
  toleranciaMonetaria: number,
): MemoriaCalculoResultado | null {
  const texto = observacoes.trim();
  if (!texto) return null;

  const expressoesEncontradas: string[] = [];
  for (const match of texto.matchAll(VALOR_UNIDADE_PATTERN)) {
    expressoesEncontradas.push(`${match[1]} ${match[2]}`.trim());
  }

  const soma = tentarSomarPares(texto);
  if (soma) {
    const bateComQuantidade = Math.abs(soma.total - quantidade) <= toleranciaMonetaria;
    return {
      expressoesEncontradas: soma.expressoes.length > 0 ? soma.expressoes : expressoesEncontradas,
      resultadoExtraido: soma.total,
      unidadeExtraida: soma.unidade,
      bateComQuantidade,
      explicacao: bateComQuantidade
        ? `Memória de cálculo confere: soma = ${soma.total}${soma.unidade ? ` ${soma.unidade}` : ""}.`
        : `Memória de cálculo diverge: soma = ${soma.total}, quantidade informada = ${quantidade}.`,
    };
  }

  const valores = extrairValoresComUnidade(texto);
  if (valores.length === 0) return null;

  const unidadeAlvo = normalizeUnidade(unidadeLinha);
  const filtrados = valores.filter(
    (item) => !unidadeAlvo || !item.unidade || unidadesCompativeis(item.unidade, unidadeAlvo),
  );
  const base = filtrados.length > 0 ? filtrados : valores;

  if (base.length === 1) {
    const unico = base[0];
    const bateComQuantidade = Math.abs(unico.valor - quantidade) <= toleranciaMonetaria;
    return {
      expressoesEncontradas: expressoesEncontradas.length > 0 ? expressoesEncontradas : [`${unico.valor} ${unico.unidade}`.trim()],
      resultadoExtraido: unico.valor,
      unidadeExtraida: unico.unidade || unidadeAlvo || null,
      bateComQuantidade,
      explicacao: bateComQuantidade
        ? `Valor encontrado nas observações confere com a quantidade (${unico.valor}).`
        : `Valor nas observações (${unico.valor}) difere da quantidade (${quantidade}).`,
    };
  }

  const total = base.reduce((acc, item) => acc + item.valor, 0);
  const unidadeExtraida = base.find((item) => item.unidade)?.unidade ?? unidadeAlvo ?? null;
  const bateComQuantidade = Math.abs(total - quantidade) <= toleranciaMonetaria;

  return {
    expressoesEncontradas: expressoesEncontradas.length > 0 ? expressoesEncontradas : base.map((item) => `${item.valor} ${item.unidade}`.trim()),
    resultadoExtraido: total,
    unidadeExtraida,
    bateComQuantidade,
    explicacao: bateComQuantidade
      ? `Soma dos valores nas observações (${total}) confere com a quantidade.`
      : `Soma nas observações (${total}) difere da quantidade informada (${quantidade}).`,
  };
}
