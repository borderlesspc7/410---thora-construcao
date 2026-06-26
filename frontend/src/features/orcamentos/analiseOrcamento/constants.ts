export const CABECALHO_COLUNAS_KEYWORDS = [
  "item",
  "fonte",
  "código",
  "codigo",
  "descrição",
  "descricao",
  "unidade",
  "quantidade",
  "preço unitário",
  "preco unitario",
  "preço total",
  "preco total",
  "bdi",
  "observações",
  "observacoes",
] as const;

export const SUBTOTAL_KEYWORDS = [
  "total geral",
  "subtotal",
  "total do grupo",
  "total:",
  "suma",
  "resumen",
  "grand total",
] as const;

export const SUBTOTAL_DESCRICAO_EXATA = new Set([
  "item",
  "total",
  "subtotal",
  "total geral",
  "total do item",
]);

export const EXCLUSAO_TIPO_LINHA = new Set(["grupo", "titulo", "título", "title"]);
