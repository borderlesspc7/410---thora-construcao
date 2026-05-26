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
