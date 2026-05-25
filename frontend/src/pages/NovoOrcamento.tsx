import React, { useCallback, useState } from "react";
import { useDropzone, DropzoneOptions } from "react-dropzone";
import { AlertCircle, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { btnPrimary } from "../components/ui/buttonClasses";
import { TableSelector, type MockTableOption } from "../components/TableSelector";
import {
  detectOrcamentoTables,
  processOrcamentoConfirmed,
  uploadPDF,
} from "../services/api";

type FlowPhase = "pick_file" | "uploading" | "detecting" | "selecting_table" | "processing_ai";

export default function NovoOrcamento() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<FlowPhase>("pick_file");
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [tableOptions, setTableOptions] = useState<MockTableOption[]>([]);
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      setPhase("pick_file");
      setUploadId(null);
      setTableOptions([]);
      setSelectedTableIds([]);
      setErrorMessage("");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
    },
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
    setPhase("pick_file");
  };

  const handleStartFlow = async () => {
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

  const handleSelectTable = (table: MockTableOption) => {
    setSelectedTableIds((prev) =>
      prev.includes(table.id)
        ? prev.filter((id) => id !== table.id)
        : [...prev, table.id],
    );
  };

  const handleConfirmSelection = async () => {
    if (!file || !uploadId || selectedTableIds.length === 0) return;

    setPhase("processing_ai");
    toast.success(
      `${selectedTableIds.length} tabela(s) selecionada(s). Iniciando processamento de IA...`,
    );

    try {
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

      navigate(`/validacao/${uploadId}`, {
        state: {
          file,
          uploadId: result.upload_id ?? uploadId,
          selectedTableIds,
          selectedTablePreviews,
          extractedData: result.tables ?? [],
          structuredData: {
            items: result.structured_items ?? result.items ?? [],
            resumo: result.resumo,
          },
          iaMetadata: result.ia_metadata,
        },
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Erro ao processar com IA";
      setErrorMessage(msg);
      setPhase("selecting_table");
      toast.error("Falha ao processar", { description: msg });
    }
  };

  const showUploadProgress = phase === "uploading" || phase === "detecting";
  const showTablePhase =
    phase === "detecting" || phase === "selecting_table" || phase === "processing_ai";

  return (
    <div className="flex flex-1 flex-col items-center overflow-auto bg-slate-50 px-6 py-12">
      <h1 className="text-2xl font-semibold text-slate-900">Novo Orçamento</h1>

      <p className="mt-2 max-w-xl text-center text-slate-600">
        Envie o PDF, escolha a tabela do orçamento e processe com a OpenAI antes da
        validação e da Curva ABC.
      </p>

      {!file ? (
        <div
          {...getRootProps()}
          className={`mt-8 w-full max-w-2xl cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition duration-200 ${
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-blue-200 bg-white hover:border-blue-400 hover:bg-blue-50/30"
          }`}
          aria-label="Área para selecionar arquivo PDF"
        >
          <input {...(getInputProps() as any)} aria-label="Selecionar arquivo PDF" />

          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-50">
            <UploadCloud
              className={`h-7 w-7 ${isDragActive ? "text-blue-600" : "text-blue-500"}`}
              aria-hidden="true"
            />
          </div>

          <p className="text-lg font-medium text-slate-800">
            {isDragActive ? "Pode soltar o arquivo agora" : "Arraste e solte seu PDF"}
          </p>

          <p className="text-sm text-slate-500">ou clique para selecionar</p>

          <p className="mt-2 text-xs text-slate-400">Suporta arquivos PDF de até 50MB</p>
        </div>
      ) : (
        <div className="mt-8 flex w-full max-w-5xl flex-col items-stretch">
          <div className="relative w-full max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
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

              {(phase === "pick_file" || phase === "selecting_table") && (
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

            {phase === "processing_ai" && (
              <div className="mt-4 border-t border-slate-100 pt-4" role="status" aria-live="polite">
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-600">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Processando com IA…
                </div>
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
              className={`${btnPrimary} mt-6 w-full max-w-2xl self-center py-3`}
              aria-label="Enviar arquivo e detectar tabelas"
            >
              Enviar e escolher tabela
            </button>
          )}

          {showTablePhase && (
            <TableSelector
              tables={tableOptions}
              loading={phase === "uploading" || phase === "detecting"}
              disabled={phase === "processing_ai"}
              selectedIds={selectedTableIds}
              onSelect={handleSelectTable}
              onConfirm={handleConfirmSelection}
            />
          )}
        </div>
      )}
    </div>
  );
}
