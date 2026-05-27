import React, { useCallback, useState } from "react";
import { useDropzone, type DropzoneOptions } from "react-dropzone";
import { AlertCircle, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary } from "../ui/buttonClasses";
import { TableSelector, type MockTableOption } from "../TableSelector";
import { WizardStepper, type WizardStep } from "../WizardStepper";
import {
  detectOrcamentoTables,
  processAnaliticoFullPdf,
  processOrcamentoConfirmed,
  uploadPDF,
} from "../../services/api";

export type OrcamentoWizardResult = {
  uploadId: string;
  file: File;
  selectedTableIds: string[];
  selectedTablePreviews: {
    id: string;
    name: string;
    page: number;
    imagem_base64?: string;
  }[];
  extractedData: unknown[];
  hierarchicalItems: unknown[];
  structuredItems: unknown[];
  resumo: unknown;
  iaMetadata: unknown;
};

type FlowPhase =
  | "pick_file"
  | "uploading"
  | "detecting"
  | "selecting_table"
  | "processing_ai";

type WizardMode = "table_selection" | "full_pdf";

function getWizardStep(phase: FlowPhase, mode: WizardMode): number {
  if (mode === "full_pdf") {
    switch (phase) {
      case "pick_file":
      case "uploading":
        return 1;
      case "processing_ai":
        return 2;
      default:
        return 1;
    }
  }
  switch (phase) {
    case "pick_file":
    case "uploading":
      return 1;
    case "detecting":
    case "selecting_table":
      return 2;
    case "processing_ai":
      return 3;
    default:
      return 1;
  }
}

type OrcamentoPdfWizardProps = {
  steps: WizardStep[];
  title: string;
  subtitle: string;
  processingLabel: string;
  logTag?: string;
  mode?: WizardMode;
  onComplete: (result: OrcamentoWizardResult) => void | Promise<void>;
};

export function OrcamentoPdfWizard({
  steps,
  title,
  subtitle,
  processingLabel,
  logTag = "Orçamento",
  mode = "table_selection",
  onComplete,
}: OrcamentoPdfWizardProps) {
  const isFullPdf = mode === "full_pdf";
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<FlowPhase>("pick_file");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [tableOptions, setTableOptions] = useState<MockTableOption[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [processingDetail, setProcessingDetail] = useState("");

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      setPhase("pick_file");
      setUploadId(null);
      setTableOptions([]);
      setSelectedTableIds([]);
      setErrorMessage("");
      setProcessingDetail("");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    multiple: false,
  } as unknown as DropzoneOptions);

  const removeFile = (e: React.MouseEvent) => {
    e.stopPropagation();
    setFile(null);
    setUploadId(null);
    setTableOptions([]);
    setSelectedTableIds([]);
    setErrorMessage("");
    setProcessingDetail("");
    setPhase("pick_file");
  };

  const finishWithResult = async (
    currentUploadId: string,
    result: {
      hierarchical_items?: unknown[];
      structured_items?: unknown[];
      items?: unknown[];
      tables?: unknown[];
      resumo?: unknown;
      ia_metadata?: unknown;
      upload_id?: string;
    },
    tableIds: string[] = [],
    previews: OrcamentoWizardResult["selectedTablePreviews"] = [],
  ) => {
    const hierarchicalItems =
      result.hierarchical_items ?? result.structured_items ?? result.items ?? [];
    const structuredItems = result.structured_items ?? result.items ?? [];

    await onComplete({
      uploadId: (result.upload_id as string) ?? currentUploadId,
      file: file!,
      selectedTableIds: tableIds,
      selectedTablePreviews: previews,
      extractedData: result.tables ?? [],
      hierarchicalItems,
      structuredItems,
      resumo: result.resumo,
      iaMetadata: result.ia_metadata,
    });
  };

  const handleFullPdfFlow = async () => {
    if (!file) return;
    setErrorMessage("");
    setProcessingDetail("");

    try {
      setPhase("uploading");
      const uploadResponse = await uploadPDF(file);
      const currentUploadId = uploadResponse.upload_id as string;
      setUploadId(currentUploadId);

      setPhase("processing_ai");
      setProcessingDetail("Lendo todo o conteúdo do PDF página a página…");
      console.info(`[${logTag}] Processamento integral do PDF:`, currentUploadId);

      const result = await processAnaliticoFullPdf(currentUploadId);
      const pages = (result.resumo?.paginas_processadas as number | undefined) ?? 0;
      setProcessingDetail(
        pages > 0
          ? `${pages} página(s) analisadas — montando planilha hierárquica…`
          : "Montando planilha hierárquica…",
      );
      await finishWithResult(currentUploadId, result);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar arquivo";
      setErrorMessage(msg);
      setPhase("pick_file");
      toast.error("Falha no processamento", { description: msg });
    }
  };

  const handleTableFlowStart = async () => {
    if (!file) return;
    setErrorMessage("");

    try {
      setPhase("uploading");
      const uploadResponse = await uploadPDF(file);
      const currentUploadId = uploadResponse.upload_id as string;
      setUploadId(currentUploadId);

      setPhase("detecting");
      const detectResponse = await detectOrcamentoTables(currentUploadId);
      const mappedOptions: MockTableOption[] = (detectResponse.options || []).map(
        (option) => ({
          id: option.id,
          name: option.nome_tabela || `Página ${option.pagina}`,
          page: option.num_pagina || option.pagina,
          preview: option.preview_texto || "Visualização disponível via imagem.",
          imagem_base64: option.imagem_base64,
        }),
      );

      setTableOptions(mappedOptions);
      setSelectedTableIds([]);
      if (mappedOptions.length === 0) {
        setPhase("pick_file");
        setErrorMessage(
          "Nenhuma tabela com dados suficientes foi encontrada. Verifique se o PDF contém planilha analítica.",
        );
        toast.error("Nenhuma tabela válida", {
          description: "O PDF não retornou tabelas com linhas suficientes para análise.",
        });
        return;
      }
      setPhase("selecting_table");
      toast.success("Tabelas encontradas", {
        description: "Selecione a tabela correta para continuar.",
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar arquivo";
      setErrorMessage(msg);
      setPhase("pick_file");
      toast.error("Falha no fluxo", { description: msg });
    }
  };

  const handleStartFlow = () => {
    if (isFullPdf) {
      void handleFullPdfFlow();
    } else {
      void handleTableFlowStart();
    }
  };

  const handleSelectTable = (table: MockTableOption) => {
    setSelectedTableIds((prev) =>
      prev.includes(table.id) ? prev.filter((id) => id !== table.id) : [...prev, table.id],
    );
  };

  const handleConfirmSelection = async () => {
    if (!file || !uploadId || selectedTableIds.length === 0) return;

    setPhase("processing_ai");
    toast.success(
      `${selectedTableIds.length} tabela(s) selecionada(s). Iniciando processamento de IA...`,
    );

    try {
      const selectedLabels = selectedTableIds
        .map((id) => tableOptions.find((t) => t.id === id)?.name || id)
        .join(", ");
      console.info(`[${logTag}] Tabelas enviadas ao backend:`, selectedTableIds, selectedLabels);

      const result = await processOrcamentoConfirmed(uploadId, selectedTableIds);
      const selectedTablePreviews = selectedTableIds
        .map((id) => tableOptions.find((t) => t.id === id))
        .filter((t): t is MockTableOption => Boolean(t))
        .map((t) => ({
          id: t.id,
          name: t.name,
          page: t.page,
          imagem_base64: t.imagem_base64,
        }));

      await finishWithResult(uploadId, result, selectedTableIds, selectedTablePreviews);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar com IA";
      setErrorMessage(msg);
      setPhase("selecting_table");
      toast.error("Falha ao processar", { description: msg });
    }
  };

  const showUploadProgress =
    phase === "uploading" || (!isFullPdf && phase === "detecting");
  const showTablePhase =
    !isFullPdf &&
    (phase === "detecting" || phase === "selecting_table" || phase === "processing_ai");
  const wizardStep = getWizardStep(phase, mode);
  const canRemoveFile =
    phase === "pick_file" || phase === "selecting_table" || (isFullPdf && phase === "uploading");

  return (
    <div className="mx-auto w-full max-w-5xl">
      <header className="mb-5">
        <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">{title}</h1>
        <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
      </header>

      <WizardStepper steps={steps} currentStep={wizardStep} className="mb-6" />

      {!file ? (
        <div
          {...getRootProps()}
          className={`mt-4 w-full cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition duration-200 ${
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-blue-200 bg-white hover:border-blue-400 hover:bg-blue-50/30"
          }`}
          aria-label="Área para selecionar arquivo PDF"
        >
          <input {...(getInputProps() as React.InputHTMLAttributes<HTMLInputElement>)} />

          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-50">
            <UploadCloud
              className={`h-7 w-7 ${isDragActive ? "text-blue-600" : "text-blue-500"}`}
              aria-hidden="true"
            />
          </div>

          <p className="text-lg font-medium text-slate-800">
            {isDragActive ? "Pode soltar o arquivo agora" : "Arraste e solte seu PDF ou edital"}
          </p>
          <p className="text-sm text-slate-500">ou clique para selecionar</p>
          <p className="mt-2 text-xs text-slate-400">
            {isFullPdf
              ? "A IA analisará todo o conteúdo do documento — não é necessário selecionar tabelas"
              : "Suporta arquivos PDF de até 50MB"}
          </p>
        </div>
      ) : (
        <div className="mt-4 flex w-full flex-col items-stretch">
          <div className="relative w-full overflow-hidden rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-4">
              <div className="rounded-lg bg-red-50 p-3" aria-hidden="true">
                <FileText className="h-8 w-8 text-red-500" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-slate-900">{file.name}</p>
                <p className="text-sm text-slate-500">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
              {canRemoveFile && (
                <button
                  type="button"
                  onClick={removeFile}
                  className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-red-600"
                  aria-label="Remover arquivo selecionado"
                >
                  <X className="h-5 w-5" />
                </button>
              )}
            </div>

            {showUploadProgress && (
              <div className="mt-4 border-t border-slate-100 pt-4" role="status" aria-live="polite">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-600">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {phase === "uploading"
                    ? "Enviando arquivo…"
                    : "Detectando tabelas…"}
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full bg-blue-600 ${
                      phase === "uploading" ? "w-1/3 animate-pulse" : "w-2/3 animate-pulse"
                    }`}
                  />
                </div>
              </div>
            )}

            {phase === "processing_ai" && (
              <div className="mt-4 border-t border-slate-100 pt-4" role="status" aria-live="polite">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-violet-700">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {processingLabel}
                </div>
                {processingDetail ? (
                  <p className="mb-2 text-xs text-slate-500">{processingDetail}</p>
                ) : null}
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full w-full animate-pulse rounded-full bg-blue-600" />
                </div>
              </div>
            )}

            {errorMessage && (
              <div className="mt-3 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{errorMessage}</span>
              </div>
            )}
          </div>

          {phase === "pick_file" && (
            <button
              type="button"
              onClick={() => void handleStartFlow()}
              className={`${btnPrimary} mt-6 w-full py-3`}
            >
              {isFullPdf ? "Enviar e analisar documento completo" : "Enviar e escolher tabela"}
            </button>
          )}

          {showTablePhase && (
            <TableSelector
              tables={tableOptions}
              loading={phase === "uploading" || phase === "detecting"}
              disabled={phase === "processing_ai"}
              selectedIds={selectedTableIds}
              onSelect={handleSelectTable}
              onConfirm={() => void handleConfirmSelection()}
              confirmLabel="Analisar com IA"
            />
          )}
        </div>
      )}
    </div>
  );
}
