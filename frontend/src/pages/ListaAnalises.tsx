import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { AbcAnalysisList } from "../components/abc/AbcAnalysisList";
import { TableSelector, type MockTableOption } from "../components/TableSelector";
import { btnPrimary, btnMuted } from "../components/ui/buttonClasses";
import {
  detectOrcamentoTables,
  ensureApiReady,
  getOrcamentoTableCandidates,
  uploadPDF,
  type OrcamentoTableCandidate,
} from "../services/api";
import {
  enqueueAbcProcess,
  fetchAbcJobsSafe,
  getAbcBatchStatus,
  registerAbcBatch,
  updateAbcJob,
  type AbcAnalysisJob,
} from "../services/abcAnalysis";
import { trackAbcBackgroundJob } from "../features/abc/abcBackgroundJobs";
import {
  appendAbcAnalysisUploadId,
  loadAbcAnalysisUploadIds,
  saveAbcAnalysisUploadIds,
} from "../features/abc/abcSession";

const POLL_MS = 5000;

type LocationState = {
  pendingFiles?: File[];
};

function sortJobsNewestFirst(jobs: AbcAnalysisJob[]): AbcAnalysisJob[] {
  return [...jobs].sort((a, b) => {
    const aTime = a.completed_at || a.updated_at || a.created_at || "";
    const bTime = b.completed_at || b.updated_at || b.created_at || "";
    return bTime.localeCompare(aTime);
  });
}

function mapTableCandidates(options: OrcamentoTableCandidate[]): MockTableOption[] {
  return options.map((option) => ({
    id: option.id,
    name: option.nome_tabela || `Página ${option.pagina ?? option.num_pagina ?? "?"}`,
    page: option.num_pagina || option.pagina || 1,
    preview: option.preview_texto || "Visualização disponível via imagem.",
    imagem_base64: option.imagem_base64,
  }));
}

export default function ListaAnalises() {
  const navigate = useNavigate();
  const location = useLocation();
  const pendingFiles = (location.state as LocationState | null)?.pendingFiles;
  const bootstrapRef = useRef(false);
  const tableOptionsCacheRef = useRef<Map<string, MockTableOption[]>>(new Map());

  const [jobs, setJobs] = useState<AbcAnalysisJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null);
  const [tableOptions, setTableOptions] = useState<MockTableOption[]>([]);
  const [isLoadingTables, setIsLoadingTables] = useState(false);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [modalUploadId, setModalUploadId] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);

  const cacheTableOptions = useCallback((uploadId: string, options: MockTableOption[]) => {
    if (options.length > 0) {
      tableOptionsCacheRef.current.set(uploadId, options);
    }
  }, []);

  const loadTableOptionsForUpload = useCallback(
    async (uploadId: string): Promise<MockTableOption[]> => {
      const cached = tableOptionsCacheRef.current.get(uploadId);
      if (cached && cached.length > 0) {
        return cached;
      }

      try {
        const cachedResponse = await getOrcamentoTableCandidates(uploadId);
        const fromServer = mapTableCandidates(cachedResponse.options ?? []);
        if (fromServer.length > 0) {
          cacheTableOptions(uploadId, fromServer);
          return fromServer;
        }
      } catch {
        /* cache miss — detecta abaixo */
      }

      const detectResponse = await detectOrcamentoTables(uploadId);
      const mapped = mapTableCandidates(detectResponse.options ?? []);
      cacheTableOptions(uploadId, mapped);
      return mapped;
    },
    [cacheTableOptions],
  );

  const refreshJobs = useCallback(async (extraUploadIds?: string[]) => {
    const list = (await fetchAbcJobsSafe()) ?? [];
    const sessionIds = loadAbcAnalysisUploadIds();
    const allIds = [
      ...new Set([
        ...list.map((j) => j.upload_id),
        ...sessionIds,
        ...(extraUploadIds ?? []),
      ]),
    ].filter((id) => !id.startsWith("pending-"));

    if (allIds.length === 0) {
      setJobs([]);
      return;
    }

    let batch: AbcAnalysisJob[] = [];
    try {
      batch = (await getAbcBatchStatus(allIds)) ?? [];
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } }).response?.status;
      if (status === 403 || status === 401) {
        saveAbcAnalysisUploadIds(list.map((j) => j.upload_id));
      }
      if (list.length === 0) throw error;
    }

    const map = new Map<string, AbcAnalysisJob>();
    for (const job of list) {
      map.set(job.upload_id, job);
    }
    for (const job of batch) {
      const prev = map.get(job.upload_id);
      map.set(job.upload_id, prev ? { ...prev, ...job } : job);
    }

    const merged = sortJobsNewestFirst(
      Array.from(map.values()).filter(
        (job) =>
          job.status !== "not_found" &&
          !job.message?.includes("não pertence"),
      ),
    );
    setJobs(merged);
    saveAbcAnalysisUploadIds(merged.map((j) => j.upload_id));
  }, []);

  const runDetectForUpload = useCallback(
    async (uploadId: string, filename: string) => {
      await updateAbcJob(uploadId, {
        status: "detecting",
        message: "Detectando tabelas no PDF…",
      });

      try {
        const mapped = await loadTableOptionsForUpload(uploadId);
        const tablesFound = mapped.length;

        if (tablesFound === 0) {
          await updateAbcJob(uploadId, {
            status: "failed",
            error: "Nenhuma tabela válida encontrada neste PDF.",
            tables_found: 0,
          });
          return;
        }

        await updateAbcJob(uploadId, {
          status: "awaiting_selection",
          message: `${tablesFound} tabela(s) encontrada(s) — clique para escolher`,
          tables_found: tablesFound,
        });
      } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : "Erro ao detectar tabelas";
        await updateAbcJob(uploadId, {
          status: "failed",
          error: msg,
        });
        toast.error(`Falha em ${filename}`, { description: msg });
      }
    },
    [loadTableOptionsForUpload],
  );

  const bootstrapPendingFiles = useCallback(
    async (files: File[]) => {
      await ensureApiReady();

      const initialJobs: AbcAnalysisJob[] = files.map((file, index) => ({
        upload_id: `pending-${index}`,
        filename: file.name,
        status: "uploading",
        message: "Enviando arquivo…",
      }));
      setJobs(initialJobs);

      const uploadResults: { uploadId: string; filename: string }[] = [];
      for (const file of files) {
        const response = await uploadPDF(file);
        const uploadId = response.upload_id as string;
        appendAbcAnalysisUploadId(uploadId);
        uploadResults.push({ uploadId, filename: file.name });
      }

      const registered = (await registerAbcBatch(uploadResults)) ?? [];
      const uploadIds = uploadResults.map((r) => r.uploadId);
      saveAbcAnalysisUploadIds(uploadIds);
      setJobs(
        registered.length > 0
          ? registered
          : uploadResults.map((r) => ({
              upload_id: r.uploadId,
              filename: r.filename,
              status: "uploading" as const,
              message: "Arquivo recebido — detectando tabelas…",
            })),
      );

      for (const item of uploadResults) {
        await runDetectForUpload(item.uploadId, item.filename);
      }
      await refreshJobs(uploadIds);
    },
    [refreshJobs, runDetectForUpload],
  );

  useEffect(() => {
    if (bootstrapRef.current) return;

    const init = async () => {
      setIsLoading(true);
      try {
        if (pendingFiles && pendingFiles.length > 0) {
          bootstrapRef.current = true;
          await bootstrapPendingFiles(pendingFiles);
          navigate("/lista-analises", { replace: true, state: null });
        } else {
          await refreshJobs();
        }
      } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : "Erro ao carregar análises";
        toast.error("Falha ao iniciar fila", { description: msg });
      } finally {
        setIsLoading(false);
      }
    };

    void init();
  }, [pendingFiles, bootstrapPendingFiles, navigate, refreshJobs]);

  useEffect(() => {
    const uploadIds = jobs.map((j) => j.upload_id).filter((id) => !id.startsWith("pending-"));
    if (uploadIds.length === 0) return;

    const hasActive = jobs.some((j) =>
      ["uploading", "detecting", "queued", "processing", "awaiting_selection"].includes(
        j.status,
      ),
    );
    if (!hasActive) return;

    const timer = window.setInterval(() => {
      void refreshJobs(uploadIds).catch(() => undefined);
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [jobs, refreshJobs]);

  const openTableSelection = async (item: AbcAnalysisJob) => {
    setModalUploadId(item.upload_id);
    setSelectedUploadId(item.upload_id);
    setSelectedTableIds([]);
    setTableOptions([]);
    setIsLoadingTables(true);

    try {
      const mapped = await loadTableOptionsForUpload(item.upload_id);
      setTableOptions(mapped);

      if (mapped.length === 0) {
        toast.error("Nenhuma tabela disponível", {
          description: "Tente reenviar o PDF na Curva ABC.",
        });
        setModalUploadId(null);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao carregar tabelas";
      toast.error("Falha ao abrir seleção", { description: msg });
      setModalUploadId(null);
    } finally {
      setIsLoadingTables(false);
    }
  };

  const handleConfirmTables = async () => {
    if (!modalUploadId || selectedTableIds.length === 0) return;

    setIsConfirming(true);
    try {
      await enqueueAbcProcess(modalUploadId, selectedTableIds);
      appendAbcAnalysisUploadId(modalUploadId);
      trackAbcBackgroundJob(modalUploadId);
      toast.success("Análise enfileirada", {
        description: "Visível nesta lista em segundo plano — permanece salva ao concluir.",
      });
      setModalUploadId(null);
      setSelectedTableIds([]);
      setTableOptions([]);
      await refreshJobs(jobs.map((j) => j.upload_id));
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao enfileirar processamento";
      toast.error("Falha ao confirmar", { description: msg });
    } finally {
      setIsConfirming(false);
    }
  };

  const handleOpenCompleted = (item: AbcAnalysisJob) => {
    navigate(`/validacao/${item.upload_id}`, {
      state: {
        fromListaAnalises: true,
        uploadId: item.upload_id,
        filename: item.filename,
      },
    });
  };

  const closeModal = () => {
    setModalUploadId(null);
    setSelectedTableIds([]);
    setTableOptions([]);
    setIsLoadingTables(false);
  };

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6 pb-12 sm:px-6">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/orcamento"
            className={`${btnMuted} inline-flex items-center gap-2 text-sm`}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Voltar à Curva ABC
          </Link>
          <h1 className="mt-3 text-2xl font-bold text-slate-900">Lista de análises</h1>
          <p className="mt-1 text-sm text-slate-600">
            Todas as análises da Curva ABC aparecem aqui — em andamento, aguardando tabela ou
            concluídas. Clique em uma análise pronta para revisar itens e o PDF novamente.
          </p>
        </div>
        <Link to="/orcamento" className={`${btnPrimary} inline-flex items-center gap-2`}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Novo lote
        </Link>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-16 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          Carregando análises…
        </div>
      ) : (
        <AbcAnalysisList
          items={jobs ?? []}
          selectedUploadId={selectedUploadId}
          onSelectAwaiting={(item) => void openTableSelection(item)}
          onSelectCompleted={handleOpenCompleted}
        />
      )}

      {modalUploadId ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-label="Selecionar tabela do orçamento"
          onClick={() => {
            if (!isConfirming && !isLoadingTables) closeModal();
          }}
        >
          <div
            className="max-h-[92vh] w-full max-w-6xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl sm:p-6 lg:max-w-7xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-slate-900">Selecionar tabela</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Escolha a planilha analítica correta para este edital.
                </p>
              </div>
              <button
                type="button"
                onClick={closeModal}
                disabled={isConfirming || isLoadingTables}
                className="shrink-0 rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Fechar seleção de tabela"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>

            <div className="mt-4">
              <TableSelector
                tables={tableOptions}
                loading={isLoadingTables}
                disabled={isConfirming}
                selectedIds={selectedTableIds}
                layout="large"
                onSelect={(table) => {
                  setSelectedTableIds((prev) =>
                    prev.includes(table.id)
                      ? prev.filter((id) => id !== table.id)
                      : [...prev, table.id],
                  );
                }}
                onConfirm={() => void handleConfirmTables()}
                confirmLabel={isConfirming ? "Enfileirando…" : "Analisar com IA"}
              />
            </div>

            <button
              type="button"
              className={`${btnMuted} mt-4`}
              disabled={isConfirming || isLoadingTables}
              onClick={closeModal}
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
