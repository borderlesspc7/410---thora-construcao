import type { WizardStep } from "../../components/WizardStepper";

/** Passos do fluxo de análise Curva ABC (PDF → tabelas → IA → validação). */
export const ANALISE_ABC_WIZARD_STEPS: WizardStep[] = [
  {
    id: 1,
    label: "PDF",
    description: "Envie o PDF do orçamento para análise",
  },
  {
    id: 2,
    label: "Tabelas",
    description: "Selecione as tabelas com os itens do orçamento",
  },
  {
    id: 3,
    label: "Análise IA",
    description: "A IA extrai os dados e monta a Curva ABC",
  },
  {
    id: 4,
    label: "Validação",
    description: "Revise valores, ajuste dados e exporte a planilha",
  },
];

/** @deprecated Use ANALISE_ABC_WIZARD_STEPS */
export const NOVO_ORCAMENTO_WIZARD_STEPS = ANALISE_ABC_WIZARD_STEPS;

export const ANALISE_ABC_VALIDATION_STEP = 4;

/** Passos do fluxo de Orçamento Analítico (PDF completo → IA → planilha). */
export const ORCAMENTO_ANALITICO_WIZARD_STEPS: WizardStep[] = [
  {
    id: 1,
    label: "PDF",
    description: "Envie o PDF ou edital completo do orçamento",
  },
  {
    id: 2,
    label: "Análise IA",
    description: "A IA lê todo o documento e extrai a estrutura hierárquica",
  },
  {
    id: 3,
    label: "Planilha",
    description: "Revise grupos, itens e composições e exporte o Excel NOVACAP",
  },
];

export const ORCAMENTO_ANALITICO_RESULTS_STEP = 3;
