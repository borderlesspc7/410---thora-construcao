import type { OrcamentoTableCandidate } from "../services/api";
import type { MockTableOption } from "../components/TableSelector";

export function mapTableCandidates(options: OrcamentoTableCandidate[]): MockTableOption[] {
  return options.map((option) => ({
    id: option.id,
    name: option.nome_tabela || `Página ${option.pagina ?? option.num_pagina ?? "?"}`,
    page: option.num_pagina || option.pagina || 1,
    preview: option.preview_texto || "Visualização disponível via imagem.",
    imagem_base64: option.imagem_base64,
    preview_rows: option.preview_rows,
    row_count: option.row_count,
    budget_score: option.budget_score,
    is_budget_likely: option.is_budget_likely,
    source: option.source,
  }));
}
