import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useDropzone, type DropzoneOptions } from "react-dropzone";
import { AlertCircle, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";
import { btnPrimary } from "../ui/buttonClasses";
import { TableSelector, type MockTableOption } from "../TableSelector";
import { WizardStepper, type WizardStep } from "../WizardStepper";
import {
  detectOrcamentoTables,
  processAnaliticoFullBatch,
  processAnaliticoFullPdf,
  resolveOrcamentoProcessResult,
  uploadPDF,
  type AnaliticoBatchJobStatus,
  type AnaliticoFullPdfResult,
} from "../../services/api";
import {
  enqueueAbcProcess,
  getAbcBatchStatus,
  registerAbcBatch,
  updateAbcJob,
} from "../../services/abcAnalysis";
import {
  markAbcJobNotified,
  trackAbcBackgroundJob,
  untrackAbcBackgroundJob,
} from "../../features/abc/abcBackgroundJobs";
import { appendAbcAnalysisUploadId } from "../../features/abc/abcSession";
import {
  ProcessingQueuePanel,
  type ProcessingQueueItem,
  type QueueItemStatus,
} from "./ProcessingQueuePanel";

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

const MAX_BATCH_PDF_FILES = 20;

function computeProgressPercent(done: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round((done / total) * 100));
}

function aggregateBatchProgress(jobs: AnaliticoBatchJobStatus[]): number {
  let total = 0;
  let done = 0;
  for (const job of jobs) {
    const jobTotal = job.pages_total ?? 0;
    if (jobTotal <= 0) continue;
    const jobDone =
      job.status === "completed" ? jobTotal : (job.pages_done ?? 0);
    total += jobTotal;
    done += jobDone;
  }
  return computeProgressPercent(done, total);
}

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

function mapJobToQueueItem(
  job: AnaliticoBatchJobStatus,
  filename: string,
): ProcessingQueueItem {
  const isWaitingInQueue =
    (job.status === "queued" ||
      (job.status === "processing" &&
        (job.queue_position ?? 0) > 0 &&
        (job.pages_total ?? 0) === 0));

  const status: QueueItemStatus = isWaitingInQueue
    ? "queued"
    : job.status === "processing"
      ? "processing"
      : job.status === "completed"
        ? "completed"
        : job.status === "failed"
          ? "failed"
          : "processing";

  return {
    uploadId: job.upload_id,
    filename,
    status,
    pagesTotal: job.pages_total,
    pagesDone: job.pages_done,
    currentPage: job.current_page,
    queuePosition: job.queue_position,
    message: job.message,
    error: job.error,
  };
}

type OrcamentoPdfWizardProps = {
  steps: WizardStep[];
  title: string;
  subtitle: string;
  processingLabel: string;
  logTag?: string;
  mode?: WizardMode;
  enableMultiUpload?: boolean;
  onBatchUpload?: (files: File[]) => void | Promise<void>;
  onComplete: (result: OrcamentoWizardResult) => void | Promise<void>;
};

export function OrcamentoPdfWizard({
  steps,
  title,
  subtitle,
  processingLabel,
  logTag = "Orçamento",
  mode = "table_selection",
  enableMultiUpload = false,
  onBatchUpload,
  onComplete,
}: OrcamentoPdfWizardProps) {
  const isFullPdf = mode === "full_pdf";
  const allowsMultiple = isFullPdf || enableMultiUpload;
  const [files, setFiles] = useState<File[]>([]);
  const file = files[0] ?? null;
  const [phase, setPhase] = useState<FlowPhase>("pick_file");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [tableOptions, setTableOptions] = useState<MockTableOption[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState("");
  const [processingDetail, setProcessingDetail] = useState("");
  const [progressPercent, setProgressPercent] = useState(0);
  const [queueItems, setQueueItems] = useState<ProcessingQueueItem[]>([]);
  const [batchFileMap, setBatchFileMap] = useState<Map<string, File>>(new Map());
  const [batchResults, setBatchResults] = useState<Map<string, AnaliticoFullPdfResult>>(
    new Map(),
  );
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const autoOpenedRef = useRef<string | null>(null);
  const processingTableIdsRef = useRef<string[]>([]);
  const processingPreviewsRef = useRef<OrcamentoWizardResult["selectedTablePreviews"]>([]);

  const resetFlow = useCallback(() => {
    setFiles([]);
    setUploadId(null);
    setTableOptions([]);
    setSelectedTableIds([]);
    setErrorMessage("");
    setProcessingDetail("");
    setProgressPercent(0);
    setQueueItems([]);
    setBatchFileMap(new Map());
    setBatchResults(new Map());
    setSelectedQueueId(null);
    autoOpenedRef.current = null;
    processingTableIdsRef.current = [];
    processingPreviewsRef.current = [];
    setPhase("pick_file");
  }, []);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;
      const nextFiles = allowsMultiple ? acceptedFiles : [acceptedFiles[0]];
      setFiles(nextFiles);
      setPhase("pick_file");
      setUploadId(null);
      setTableOptions([]);
      setSelectedTableIds([]);
      setErrorMessage("");
      setProcessingDetail("");
      setProgressPercent(0);
      setQueueItems([]);
      setBatchFileMap(new Map());
      setBatchResults(new Map());
      setSelectedQueueId(null);
    },
    [allowsMultiple],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: allowsMultiple ? MAX_BATCH_PDF_FILES : 1,
    multiple: allowsMultiple,
  } as unknown as DropzoneOptions);

  const removeFile = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const next = files.filter((_, i) => i !== index);
    if (next.length === 0) {
      resetFlow();
      return;
    }
    setFiles(next);
    setPhase("pick_file");
    setUploadId(null);
    setErrorMessage("");
    setProcessingDetail("");
    setProgressPercent(0);
    setQueueItems([]);
    setBatchFileMap(new Map());
    setBatchResults(new Map());
    setSelectedQueueId(null);
  };

  const finishWithResult = useCallback(async (
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
    sourceFile: File,
    tableIds: string[] = [],
    previews: OrcamentoWizardResult["selectedTablePreviews"] = [],
  ) => {
    const resolved = await resolveOrcamentoProcessResult(
      currentUploadId,
      result as Parameters<typeof resolveOrcamentoProcessResult>[1],
    );

    const hierarchicalItems =
      resolved.hierarchical_items ?? resolved.structured_items ?? resolved.items ?? [];
    const structuredItems = resolved.structured_items ?? resolved.items ?? [];

    await onComplete({
      uploadId: (resolved.upload_id as string) ?? currentUploadId,
      file: sourceFile,
      selectedTableIds: tableIds,
      selectedTablePreviews: previews,
      extractedData: resolved.tables ?? [],
      hierarchicalItems,
      structuredItems,
      resumo: resolved.resumo,
      iaMetadata: resolved.ia_metadata,
    });
  }, [onComplete]);

  useEffect(() => {
    if (isFullPdf || phase !== "processing_ai" || !uploadId || !file) {
      return;
    }

    let cancelled = false;

    const pollJob = async () => {
      try {
        const jobs = (await getAbcBatchStatus([uploadId])) ?? [];
        if (cancelled) return;

        const job = jobs[0];
        if (!job) return;

        if (job.status === "queued" || job.status === "processing") {
          const total = job.pages_total ?? job.table_ids?.length ?? 0;
          const done = job.pages_done ?? 0;
          if (total > 0) {
            setProgressPercent(computeProgressPercent(done, total));
          }
          setProcessingDetail(
            job.message ??
              (total > 0
                ? `IA analisando tabela ${Math.min(done + 1, total)} de ${total}…`
                : job.queue_position
                  ? `Na fila (posição ${job.queue_position})…`
                  : "IA analisando tabelas…"),
          );
          return;
        }

        if (job.status === "completed" && job.result) {
          setProgressPercent(100);
          markAbcJobNotified(uploadId);
          untrackAbcBackgroundJob(uploadId);
          setProcessingDetail("Análise concluída — abrindo validação…");
          await finishWithResult(
            uploadId,
            job.result as Parameters<typeof finishWithResult>[1],
            file,
            processingTableIdsRef.current,
            processingPreviewsRef.current,
          );
          return;
        }

        if (job.status === "failed") {
          const msg = job.error || job.message || "Falha no processamento com IA";
          setErrorMessage(msg);
          setPhase("selecting_table");
          toast.error("Falha ao processar", { description: msg });
        }
      } catch {
        /* poller global também acompanha */
      }
    };

    void pollJob();
    const timer = window.setInterval(() => void pollJob(), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isFullPdf, phase, uploadId, file, finishWithResult]);

  const handleQueueSelect = async (item: ProcessingQueueItem) => {
    const result = batchResults.get(item.uploadId);
    const sourceFile = batchFileMap.get(item.uploadId);
    if (!result || !sourceFile) return;
    setSelectedQueueId(item.uploadId);
    await finishWithResult(item.uploadId, result, sourceFile);
  };

  const handleFullPdfFlow = async () => {
    if (files.length === 0) return;

    if (files.length === 1) {
      await handleSingleFullPdfFlow(files[0]);
      return;
    }

    await handleBatchFullPdfFlow(files);
  };

  const handleSingleFullPdfFlow = async (singleFile: File) => {
    setErrorMessage("");
    setProcessingDetail("");
    setProgressPercent(0);

    setQueueItems([
      {
        uploadId: "pending-0",
        filename: singleFile.name,
        status: "uploading",
        message: "Enviando arquivo…",
      },
    ]);

    try {
      setPhase("uploading");
      const uploadResponse = await uploadPDF(singleFile);
      const currentUploadId = uploadResponse.upload_id as string;
      setUploadId(currentUploadId);
      setBatchFileMap(new Map([[currentUploadId, singleFile]]));

      setQueueItems([
        {
          uploadId: currentUploadId,
          filename: singleFile.name,
          status: "queued",
          message: "Aguardando processamento…",
        },
      ]);

      setPhase("processing_ai");
      setProcessingDetail("Documento enfileirado — processamento sequencial…");
      console.info(`[${logTag}] Processamento integral do PDF:`, currentUploadId);

      const result = await processAnaliticoFullPdf(currentUploadId, {
        forceReprocess: true,
        onProgress: (update) => {
          setQueueItems([
            mapJobToQueueItem(
              { ...update, upload_id: currentUploadId },
              singleFile.name,
            ),
          ]);

          const total = update.pages_total || 0;
          const done = update.pages_done || 0;
          if (total > 0) {
            setProgressPercent(computeProgressPercent(done, total));
          }
          if (update.status === "queued") {
            setProcessingDetail(
              update.message ??
                `Na fila de processamento${update.queue_position ? ` (#${update.queue_position})` : ""}…`,
            );
            return;
          }
          if (total > 0) {
            setProcessingDetail(
              update.message ??
                `Analisando página ${update.current_page ?? done} (${done}/${total})…`,
            );
          } else if (update.message) {
            setProcessingDetail(update.message);
          }
        },
      });

      setBatchResults(new Map([[currentUploadId, result]]));
      setSelectedQueueId(currentUploadId);

      const pages = (result.resumo?.paginas_processadas as number | undefined) ?? 0;
      setProcessingDetail(
        result.cached
          ? "Resultado recuperado do cache — montando planilha…"
          : pages > 0
            ? `${pages} página(s) analisadas — montando planilha hierárquica…`
            : "Montando planilha hierárquica…",
      );
      await finishWithResult(currentUploadId, result, singleFile);
      setProgressPercent(100);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar arquivo";
      console.error(`[${logTag}] Falha no processamento integral:`, error);
      setErrorMessage(msg);
      setPhase("pick_file");
      setQueueItems((prev) =>
        prev.map((item) =>
          item.uploadId.startsWith("pending-")
            ? item
            : { ...item, status: "failed" as const, error: msg },
        ),
      );
      toast.error("Falha no processamento", { description: msg });
    }
  };

  const handleBatchFullPdfFlow = async (pdfFiles: File[]) => {
    setErrorMessage("");
    setProcessingDetail("");
    setProgressPercent(0);

    const initialQueue: ProcessingQueueItem[] = pdfFiles.map((f, index) => ({
      uploadId: `pending-${index}`,
      filename: f.name,
      status: "uploading",
      message: "Enviando arquivo…",
    }));
    setQueueItems(initialQueue);

    try {
      setPhase("uploading");

      const uploadResults = await Promise.all(
        pdfFiles.map(async (pdfFile, index) => {
          const response = await uploadPDF(pdfFile);
          return {
            uploadId: response.upload_id as string,
            file: pdfFile,
            index,
          };
        }),
      );

      const fileMap = new Map<string, File>();
      const nameMap = new Map<string, string>();
      for (const item of uploadResults) {
        fileMap.set(item.uploadId, item.file);
        nameMap.set(item.uploadId, item.file.name);
      }
      setBatchFileMap(fileMap);

      setQueueItems(
        uploadResults.map((item) => ({
          uploadId: item.uploadId,
          filename: item.file.name,
          status: "queued",
          message: "Aguardando processamento…",
        })),
      );

      setPhase("processing_ai");
      setProcessingDetail(`${pdfFiles.length} arquivo(s) enfileirados — processamento sequencial…`);

      const resultsMap = await processAnaliticoFullBatch(
        uploadResults.map((r) => r.uploadId),
        {
          forceReprocess: true,
          onProgress: (jobs) => {
            setQueueItems(
              jobs.map((job) =>
                mapJobToQueueItem(job, nameMap.get(job.upload_id) ?? job.upload_id),
              ),
            );

            const batchPct = aggregateBatchProgress(jobs);
            if (batchPct > 0) {
              setProgressPercent(batchPct);
            }

            const partialResults = new Map<string, AnaliticoFullPdfResult>();
            for (const job of jobs) {
              if (job.status === "completed" && job.result) {
                partialResults.set(job.upload_id, job.result);
              }
            }
            if (partialResults.size > 0) {
              setBatchResults((prev) => new Map([...prev, ...partialResults]));

              const firstCompleted = uploadResults.find((r) => partialResults.has(r.uploadId));
              if (firstCompleted && !autoOpenedRef.current) {
                const result = partialResults.get(firstCompleted.uploadId)!;
                autoOpenedRef.current = firstCompleted.uploadId;
                setSelectedQueueId(firstCompleted.uploadId);
                setProcessingDetail("Primeiro resultado pronto — abrindo planilha…");
                void finishWithResult(
                  firstCompleted.uploadId,
                  result,
                  firstCompleted.file,
                );
              }
            }
          },
        },
      );

      setBatchResults(resultsMap);

      const failedJobs = uploadResults.filter((r) => !resultsMap.has(r.uploadId));
      if (failedJobs.length > 0) {
        toast.warning(`${failedJobs.length} arquivo(s) falharam no processamento`);
      }

      if (resultsMap.size === 0) {
        throw new Error("Nenhum arquivo foi processado com sucesso.");
      }

      setProgressPercent(100);
      setProcessingDetail("Análise do lote concluída.");
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar lote";
      console.error(`[${logTag}] Falha no lote:`, error);
      setErrorMessage(msg);
      setPhase("pick_file");
      toast.error("Falha no processamento em lote", { description: msg });
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

      await registerAbcBatch([{ uploadId: currentUploadId, filename: file.name }]);
      appendAbcAnalysisUploadId(currentUploadId);
      await updateAbcJob(currentUploadId, {
        status: "detecting",
        message: "Detectando tabelas no PDF…",
      });

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
        await updateAbcJob(currentUploadId, {
          status: "failed",
          error: "Nenhuma tabela válida encontrada neste PDF.",
          tables_found: 0,
        });
        setPhase("pick_file");
        setErrorMessage(
          "Nenhuma tabela com dados suficientes foi encontrada. Verifique se o PDF contém planilha analítica.",
        );
        toast.error("Nenhuma tabela válida", {
          description: "O PDF não retornou tabelas com linhas suficientes para análise.",
        });
        return;
      }
      await updateAbcJob(currentUploadId, {
        status: "awaiting_selection",
        message: `${mappedOptions.length} tabela(s) encontrada(s) — selecione para analisar`,
        tables_found: mappedOptions.length,
      });
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
    if (enableMultiUpload && !isFullPdf && files.length > 1) {
      void onBatchUpload?.(files);
      return;
    }
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
    setProcessingDetail("Enfileirando análise no servidor…");

    try {
      const selectedLabels = selectedTableIds
        .map((id) => tableOptions.find((t) => t.id === id)?.name || id)
        .join(", ");
      console.info(`[${logTag}] Tabelas enviadas ao backend:`, selectedTableIds, selectedLabels);

      const selectedTablePreviews = selectedTableIds
        .map((id) => tableOptions.find((t) => t.id === id))
        .filter((t): t is MockTableOption => Boolean(t))
        .map((t) => ({
          id: t.id,
          name: t.name,
          page: t.page,
          imagem_base64: t.imagem_base64,
        }));

      processingTableIdsRef.current = selectedTableIds;
      processingPreviewsRef.current = selectedTablePreviews;

      await enqueueAbcProcess(uploadId, selectedTableIds);
      appendAbcAnalysisUploadId(uploadId);
      trackAbcBackgroundJob(uploadId);

      toast.success(
        `${selectedTableIds.length} tabela(s) em análise`,
        {
          description:
            "Acompanhe em Lista de análises. O processamento continua em segundo plano.",
          duration: 8000,
        },
      );
      setProcessingDetail("IA processando na fila do servidor…");
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
  const showQueuePanel = isFullPdf && queueItems.length > 0;

  return (
    <div className="mx-auto w-full max-w-6xl">
      <header className="mb-5">
        <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">{title}</h1>
        <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
      </header>

      <WizardStepper steps={steps} currentStep={wizardStep} className="mb-6" />

      <div className={`flex flex-col gap-6 ${showQueuePanel ? "lg:flex-row lg:items-start" : ""}`}>
        <div className="min-w-0 flex-1">
          {files.length === 0 ? (
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
                {isDragActive
                  ? "Pode soltar os arquivos agora"
                  : allowsMultiple
                    ? "Arraste e solte um ou vários PDFs/editais"
                    : "Arraste e solte seu PDF ou edital"}
              </p>
              <p className="text-sm text-slate-500">ou clique para selecionar</p>
              <p className="mt-2 text-xs text-slate-400">
                {allowsMultiple
                  ? enableMultiUpload && !isFullPdf
                    ? `Até ${MAX_BATCH_PDF_FILES} arquivos — lotes vão para a Lista de análises`
                    : `Até ${MAX_BATCH_PDF_FILES} arquivos — processamento sequencial em fila`
                  : "Suporta arquivos PDF de até 50MB"}
              </p>
            </div>
          ) : (
            <div className="mt-4 flex w-full flex-col items-stretch">
              <div className="relative w-full overflow-hidden rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="space-y-3">
                  {files.map((f, index) => (
                    <div key={`${f.name}-${index}`} className="flex items-center gap-4">
                      <div className="rounded-lg bg-red-50 p-3" aria-hidden="true">
                        <FileText className="h-8 w-8 text-red-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-slate-900">{f.name}</p>
                        <p className="text-sm text-slate-500">
                          {(f.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                      {canRemoveFile && (
                        <button
                          type="button"
                          onClick={(e) => removeFile(index, e)}
                          className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-red-600"
                          aria-label={`Remover ${f.name}`}
                        >
                          <X className="h-5 w-5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                {showUploadProgress && !showQueuePanel && (
                  <div className="mt-4 border-t border-slate-100 pt-4" role="status" aria-live="polite">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-600">
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      {phase === "uploading" ? "Enviando arquivo…" : "Detectando tabelas…"}
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

                {phase === "processing_ai" && !showQueuePanel && (
                  <div className="mt-4 border-t border-slate-100 pt-4" role="status" aria-live="polite">
                    <div className="mb-2 flex items-center gap-2 text-sm font-medium text-violet-700">
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      {processingLabel}
                    </div>
                    {!isFullPdf ? (
                      <p className="mb-2 text-xs text-blue-600">
                        Esta análise aparece na{" "}
                        <Link to="/lista-analises" className="font-medium underline">
                          Lista de análises
                        </Link>{" "}
                        — você pode sair desta tela.
                      </p>
                    ) : null}
                    {processingDetail ? (
                      <p className="mb-2 text-xs text-slate-500">{processingDetail}</p>
                    ) : null}
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-blue-600 transition-all duration-500 ease-out"
                        style={{ width: `${Math.max(progressPercent, 3)}%` }}
                      />
                    </div>
                    {progressPercent > 0 ? (
                      <p className="mt-1 text-right text-xs text-slate-400">{progressPercent}%</p>
                    ) : null}
                  </div>
                )}

                {phase === "processing_ai" && showQueuePanel && processingDetail ? (
                  <p className="mt-4 border-t border-slate-100 pt-4 text-xs text-slate-500">
                    {processingDetail}
                  </p>
                ) : null}

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
                  {allowsMultiple && files.length > 1
                    ? enableMultiUpload && !isFullPdf
                      ? `Enviar ${files.length} editais para a fila`
                      : `Enviar e analisar ${files.length} documentos`
                    : allowsMultiple
                      ? "Enviar e analisar documento completo"
                      : "Enviar e escolher tabela"}
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

        {showQueuePanel ? (
          <ProcessingQueuePanel
            items={queueItems}
            selectedUploadId={selectedQueueId}
            onSelectCompleted={(item) => void handleQueueSelect(item)}
          />
        ) : null}
      </div>
    </div>
  );
}
