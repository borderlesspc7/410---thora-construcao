export type OutputModelId = "analitico" | "sintetico" | "curva_abc";

export type OutputModelsSelection = Record<OutputModelId, boolean>;

export const DEFAULT_OUTPUT_MODELS: OutputModelsSelection = {
  analitico: false,
  sintetico: false,
  curva_abc: true,
};

/** Único modelo ativo no fluxo atual (Curva ABC). */
export const CURVA_ABC_ONLY: OutputModelsSelection = {
  analitico: false,
  sintetico: false,
  curva_abc: true,
};

export const OUTPUT_MODEL_OPTIONS: {
  id: OutputModelId;
  label: string;
  description: string;
}[] = [
  {
    id: "analitico",
    label: "Orçamento Analítico",
    description: "Visão detalhada com todos os insumos",
  },
  {
    id: "sintetico",
    label: "Orçamento Sintético",
    description: "Visão macro agrupada por etapas",
  },
  {
    id: "curva_abc",
    label: "Curva ABC",
    description: "Análise estratégica de Pareto",
  },
];

export function hasAnyOutputModelSelected(selection: OutputModelsSelection): boolean {
  return OUTPUT_MODEL_OPTIONS.some((opt) => selection[opt.id]);
}

export type NovoOrcamentoFlowState = {
  nomeProjeto?: string;
  modelosSelecionados?: OutputModelsSelection;
  file?: File;
  uploadId?: string;
  selectedTableIds?: string[];
  selectedTablePreviews?: unknown[];
  extractedData?: unknown[];
  structuredData?: { items?: unknown[]; resumo?: unknown };
  iaMetadata?: unknown;
};
