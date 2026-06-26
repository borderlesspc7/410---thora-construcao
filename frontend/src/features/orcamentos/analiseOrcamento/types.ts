export type StatusVerificacao =
  | "ok"
  | "divergente"
  | "alerta"
  | "nao_aplicavel"
  | "pendente";

export type StatusGeralLinha = "aprovado" | "alerta" | "reprovado" | "ignorado";

export type SeveridadeVerificacao = "erro" | "alerta" | "info";

export type RegraAnaliseId =
  | "CALC_SUBTOTAL"
  | "CALC_BDI"
  | "BDI_GLOBAL"
  | "MEMORIA_CALCULO"
  | "CAMPOS_OBRIGATORIOS";

export type VerificacaoLinha = {
  regraId: RegraAnaliseId;
  status: StatusVerificacao;
  severidade: SeveridadeVerificacao;
  valorCalculado?: number;
  valorInformado?: number;
  diferenca?: number;
  mensagem: string;
};

export type MemoriaCalculoResultado = {
  expressoesEncontradas: string[];
  resultadoExtraido: number | null;
  unidadeExtraida: string | null;
  bateComQuantidade: boolean;
  explicacao: string;
};

export type LinhaOrcamentoEntrada = {
  id: string | number;
  itemNumero: string;
  banco: string;
  codigo: string;
  descricao: string;
  unidade: string;
  quantidade: number;
  precoUnitario: number;
  precoTotalSemBdi: number;
  bdiPercent: number;
  precoTotalComBdi: number;
  observacoes: string;
  tipoLinha?: "grupo" | "item" | "composicao";
};

export type ContextoAnaliseOrcamento = {
  bdiGlobalPercent?: number;
  toleranciaMonetaria?: number;
  toleranciaPercentual?: number;
};

export type ResultadoLinhaAnalise = {
  linhaId: string | number;
  itemNumero: string;
  descricao: string;
  statusGeral: StatusGeralLinha;
  motivoIgnorado?: string;
  verificacoes: VerificacaoLinha[];
  memoriaCalculo?: MemoriaCalculoResultado;
};

export type ResumoAnaliseOrcamento = {
  totalLinhas: number;
  linhasAnalisadas: number;
  linhasIgnoradas: number;
  aprovadas: number;
  comAlerta: number;
  reprovadas: number;
};

export type ResultadoAnaliseOrcamento = {
  versaoModelo: string;
  contexto: Required<ContextoAnaliseOrcamento>;
  linhas: ResultadoLinhaAnalise[];
  resumo: ResumoAnaliseOrcamento;
};

export const ANALISE_ORCAMENTO_VERSAO = "1.0";

export const CONTEXTO_PADRAO: Required<ContextoAnaliseOrcamento> = {
  bdiGlobalPercent: 0,
  toleranciaMonetaria: 0.02,
  toleranciaPercentual: 0.5,
};
