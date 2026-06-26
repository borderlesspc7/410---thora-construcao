import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Download,
  GitCompare,
  Layers,
  Loader2,
  Lock,
  Plus,
  Calculator,
} from "lucide-react";
import { toast } from "sonner";
import { getOrcamento, getOrcamentoFromFirebase } from "../services/api";
import {
  OrcamentoPdfWizard,
  type OrcamentoWizardResult,
} from "../components/orcamento/OrcamentoPdfWizard";
import { WizardStepper } from "../components/WizardStepper";
import {
  ORCAMENTO_ANALITICO_RESULTS_STEP,
  ORCAMENTO_ANALITICO_WIZARD_STEPS,
} from "../features/orcamentos/novoOrcamentoWizard";
import {
  calcularResumoAnalitico,
  mapRawListToLinhasAnaliticas,
  type LinhaAnalitica,
} from "../features/orcamentos/orcamentoAnalitico";
import {
  analisarOrcamentoFromLinhasAnaliticas,
  resultadoAnalisePorId,
} from "../features/orcamentos/analiseOrcamento";
import { AnaliseOrcamentoResumo } from "../components/orcamento/AnaliseOrcamentoResumo";
import { AnaliseOrcamentoStatusBadge } from "../components/orcamento/AnaliseOrcamentoStatusBadge";
import {
  aplicarEdicaoAnalitica,
  recalcularGruposAnalitico,
  type AnaliticoEditableField,
} from "../features/orcamentos/recalcularAnaliticoHierarquico";
import type { NovoOrcamentoFlowState } from "../features/orcamentos/outputModels";
import { FULL_ORCAMENTO_EXPORT } from "../features/orcamentos/outputModels";
import ExportModal from "../components/ExportModal";
import { useOrcamentoLinhasContext } from "../features/orcamentos/OrcamentoLinhasContext";
import { btnAccent, btnMuted } from "../components/ui/buttonClasses";
import { useAuth } from "../features/auth/AuthContext";
import { useActiveLocks } from "../features/orcamentos/useActiveLocks";
import {
  acquireItemLock,
  mapEditableFieldToAuditCampo,
  postAuditLog,
  releaseItemLock,
} from "../features/orcamentos/orcamentoEnterpriseApi";
import { RevisoesPanel } from "../features/orcamentos/RevisoesPanel";

const formatMoney = (value: number) =>
  value.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const formatQty = (value: number) =>
  value.toLocaleString("pt-BR", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

const EDITABLE_NUMERIC_CLASS =
  "w-full min-w-[5rem] rounded border border-slate-200 bg-white px-2 py-1 text-right text-sm tabular-nums focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";

const EDITABLE_NUMERIC_LOCKED_CLASS =
  "w-full min-w-[5rem] rounded border border-orange-300 bg-orange-50 px-2 py-1 text-right text-sm tabular-nums opacity-70 cursor-not-allowed";

function rowClassName(tipo: LinhaAnalitica["tipoLinha"]): string {
  if (tipo === "grupo") return "bg-slate-700 text-white font-bold";
  if (tipo === "composicao") return "bg-white text-slate-600 text-sm italic";
  return "bg-white text-slate-800";
}

type ViewMode = "wizard" | "results" | "loading";

const OrcamentoAnalitico: React.FC = () => {
  const { uploadId: uploadIdParam } = useParams<{ uploadId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const flowState = location.state as NovoOrcamentoFlowState | null;
  const bdiAppliedState = location.state as {
    bdiApplied?: boolean;
    bdiPercentual?: number;
    valorComBDI?: number;
  } | null;

  const [viewMode, setViewMode] = useState<ViewMode>("loading");
  const [linhas, setLinhas] = useState<LinhaAnalitica[]>([]);
  const [rawHierarchicalItems, setRawHierarchicalItems] = useState<unknown[]>([]);
  const [currentUploadId, setCurrentUploadId] = useState<string | null>(uploadIdParam ?? null);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [nomeProjeto, setNomeProjeto] = useState<string>(
    flowState?.nomeProjeto ?? "Orçamento",
  );
  const [wizardKey, setWizardKey] = useState(0);
  const [showRevisoes, setShowRevisoes] = useState(false);
  const { setOrcamentoLinhas, clearOrcamentoLinhas } = useOrcamentoLinhasContext();
  const { user } = useAuth();
  const activeLocks = useActiveLocks(currentUploadId);
  const lockedBySelfRef = useRef<Set<string>>(new Set());

  const currentUserId = user?.uid ?? "";
  const currentUserName =
    user?.displayName?.trim() || user?.email?.trim() || "Engenheiro";

  const applyHierarchicalData = useCallback(
    (rawItems: unknown[], uploadId?: string, filename?: string) => {
      const mapped = recalcularGruposAnalitico(mapRawListToLinhasAnaliticas(rawItems));
      if (mapped.length === 0) return false;
      setLinhas(mapped);
      setRawHierarchicalItems(rawItems);
      setViewMode("results");
      if (uploadId) setCurrentUploadId(uploadId);
      if (filename) setNomeProjeto(filename.replace(/\.pdf$/i, ""));
      setOrcamentoLinhas({
        linhas: mapped,
        uploadId: uploadId ?? null,
        nomeProjeto: filename ? filename.replace(/\.pdf$/i, "") : "Orçamento",
      });
      return true;
    },
    [setOrcamentoLinhas],
  );

  useEffect(() => {
    if (linhas.length > 0) {
      setOrcamentoLinhas({ linhas, uploadId: currentUploadId, nomeProjeto });
    }
  }, [linhas, currentUploadId, nomeProjeto, setOrcamentoLinhas]);

  useEffect(() => {
    const load = async () => {
      const fromState =
        (flowState?.hierarchicalItems as unknown[] | undefined) ??
        (flowState?.structuredData?.hierarchicalItems as unknown[] | undefined);

      if (Array.isArray(fromState) && fromState.length > 0) {
        applyHierarchicalData(
          fromState,
          flowState?.uploadId as string | undefined,
          (flowState?.file as File | undefined)?.name,
        );
        return;
      }

      const stateItems = location.state?.items as unknown[] | undefined;
      if (Array.isArray(stateItems) && stateItems.length > 0) {
        applyHierarchicalData(stateItems, uploadIdParam);
        return;
      }

      if (!uploadIdParam) {
        setViewMode("wizard");
        return;
      }

      try {
        const [firebaseDoc, backendDoc] = await Promise.all([
          getOrcamentoFromFirebase(uploadIdParam).catch(() => null),
          getOrcamento(uploadIdParam).catch(() => null),
        ]);

        const itemsData =
          (firebaseDoc?.itemsData as Record<string, unknown> | undefined) ??
          (backendDoc?.orcamento?.itemsData as Record<string, unknown> | undefined);

        const hierarchical =
          (itemsData?.hierarchical_items as unknown[]) ??
          (backendDoc?.orcamento?.hierarchical_items as unknown[]) ??
          (itemsData?.items as unknown[]) ??
          (firebaseDoc?.items as unknown[]) ??
          (backendDoc?.orcamento?.items as unknown[]) ??
          [];

        if (Array.isArray(hierarchical) && hierarchical.length > 0) {
          const filename =
            (firebaseDoc?.filename as string | undefined) ??
            (backendDoc?.orcamento?.filename as string | undefined);
          applyHierarchicalData(hierarchical, uploadIdParam, filename);
          return;
        }

        setViewMode("wizard");
      } catch {
        setViewMode("wizard");
      }
    };

    void load();
  }, [uploadIdParam, flowState, location.state, applyHierarchicalData]);

  const handleWizardComplete = async (result: OrcamentoWizardResult) => {
    const ok = applyHierarchicalData(
      result.hierarchicalItems,
      result.uploadId,
      result.file.name,
    );

    if (!ok) {
      toast.error("Nenhum dado extraído", {
        description: "A IA não retornou linhas para o orçamento analítico.",
      });
      return;
    }

    navigate(`/orcamento-analitico/${result.uploadId}`, {
      replace: true,
      state: {
        file: result.file,
        uploadId: result.uploadId,
        selectedTableIds: result.selectedTableIds,
        selectedTablePreviews: result.selectedTablePreviews,
        extractedData: result.extractedData,
        structuredData: {
          items: result.structuredItems,
          hierarchicalItems: result.hierarchicalItems,
          resumo: result.resumo,
        },
        hierarchicalItems: result.hierarchicalItems,
        iaMetadata: result.iaMetadata,
      },
    });

    toast.success("Orçamento analítico pronto", {
      description: `${result.hierarchicalItems.length} linhas extraídas com sucesso.`,
    });
  };

  const handleNovaAnalise = () => {
    setLinhas([]);
    setCurrentUploadId(null);
    setNomeProjeto("Orçamento");
    clearOrcamentoLinhas();
    setViewMode("wizard");
    setWizardKey((k) => k + 1);
    navigate("/orcamento-analitico", { replace: true, state: null });
  };

  const resumo = useMemo(() => calcularResumoAnalitico(linhas), [linhas]);

  const resultadoAnalise = useMemo(
    () => analisarOrcamentoFromLinhasAnaliticas(linhas, rawHierarchicalItems),
    [linhas, rawHierarchicalItems],
  );

  const analisePorId = useMemo(
    () => resultadoAnalisePorId(resultadoAnalise),
    [resultadoAnalise],
  );

  const getLockForItem = useCallback(
    (itemId: string) => activeLocks.get(itemId) ?? null,
    [activeLocks],
  );

  const isLockedByOther = useCallback(
    (itemId: string) => {
      const lock = getLockForItem(itemId);
      return Boolean(lock && lock.user_id !== currentUserId);
    },
    [getLockForItem, currentUserId],
  );

  const handleCellFocus = useCallback(
    (itemId: string) => {
      if (!currentUploadId || !currentUserId) return;
      lockedBySelfRef.current.add(itemId);
      void acquireItemLock(currentUploadId, itemId, currentUserName).catch(() => undefined);
    },
    [currentUploadId, currentUserId, currentUserName],
  );

  const handleCellBlur = useCallback(
    (itemId: string) => {
      if (!currentUploadId) return;
      lockedBySelfRef.current.delete(itemId);
      void releaseItemLock(currentUploadId, itemId);
    },
    [currentUploadId],
  );

  const handleAnaliticoEdit = useCallback(
    (index: number, field: AnaliticoEditableField, value: string) => {
      setLinhas((prev) => {
        const linha = prev[index];
        if (!linha) return prev;

        const oldValue =
          field === "quantidade"
            ? linha.quantidade
            : field === "valorUnitario"
              ? linha.valorUnitario
              : linha.bdi;

        const parsedNew = value === "" ? 0 : Number(value);
        const parsedOld = typeof oldValue === "number" ? oldValue : Number(oldValue) || 0;

        if (parsedNew !== parsedOld && currentUploadId) {
          const itemCodigo = linha.codigo || linha.itemNumero || String(linha.id);
          void postAuditLog(currentUploadId, {
            item_codigo: itemCodigo,
            campo_alterado: mapEditableFieldToAuditCampo(field),
            valor_antigo: parsedOld,
            valor_novo: parsedNew,
            user_name: currentUserName,
          });
        }

        return aplicarEdicaoAnalitica(prev, index, field, value);
      });
    },
    [currentUploadId, currentUserName],
  );

  if (viewMode === "loading") {
    return (
      <div className="flex min-h-full flex-col items-center justify-center bg-slate-50 py-24">
        <Loader2 className="mb-3 h-8 w-8 animate-spin text-blue-600" />
        <p className="text-slate-600">Carregando…</p>
      </div>
    );
  }

  if (viewMode === "wizard") {
    return (
      <div className="min-h-full bg-slate-50 px-4 py-6 pb-12 sm:px-6">
        <OrcamentoPdfWizard
          key={wizardKey}
          mode="full_pdf"
          steps={ORCAMENTO_ANALITICO_WIZARD_STEPS}
          title="Orçamento Analítico"
          subtitle={`Passo 1 de ${ORCAMENTO_ANALITICO_WIZARD_STEPS.length} — envie um ou vários PDFs/editais; o processamento ocorre em fila sequencial com acompanhamento individual.`}
          processingLabel="Passo 2 — IA analisando todo o conteúdo do PDF (grupos, itens e composições)…"
          logTag="Orçamento Analítico"
          onComplete={handleWizardComplete}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col bg-slate-50">
      <header className="shrink-0 border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Layers className="h-6 w-6 text-blue-600" />
              <h1 className="text-2xl font-bold text-slate-900">Orçamento Analítico</h1>
            </div>
            <p className="mt-1 text-sm text-slate-600">
              Estrutura hierárquica original do edital — ordem sequencial preservada
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {currentUploadId && (
              <button
                type="button"
                className={btnMuted}
                onClick={() => setShowRevisoes(true)}
              >
                <GitCompare className="h-4 w-4" />
                Gerenciar Revisões
              </button>
            )}
            {currentUploadId && (
              <button
                type="button"
                className={btnMuted}
                onClick={() => navigate(`/orcamento-sintetico/${currentUploadId}`)}
              >
                Ver Sintético
              </button>
            )}
            <button type="button" onClick={handleNovaAnalise} className={btnMuted}>
              <Plus className="h-4 w-4" />
              Nova análise
            </button>
            <button
              type="button"
              disabled={linhas.length === 0}
              onClick={() => setExportModalOpen(true)}
              className={btnAccent}
            >
              <Download className="h-4 w-4" />
              Exportar
            </button>
            {currentUploadId && (
              <button
                type="button"
                className={btnMuted}
                onClick={() => navigate(`/bdi/${currentUploadId}`)}
              >
                <Calculator className="h-4 w-4" />
                Calcular BDI
              </button>
            )}
          </div>
        </div>

        <div className="mx-auto mt-4 max-w-[1600px]">
          <WizardStepper
            steps={ORCAMENTO_ANALITICO_WIZARD_STEPS}
            currentStep={ORCAMENTO_ANALITICO_RESULTS_STEP}
          />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">
        {bdiAppliedState?.bdiApplied && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
            BDI de{" "}
            {(bdiAppliedState.bdiPercentual ?? 0).toLocaleString("pt-BR", {
              minimumFractionDigits: 2,
            })}
            % aplicado — Total atualizado:{" "}
            {(bdiAppliedState.valorComBDI ?? 0).toLocaleString("pt-BR", {
              style: "currency",
              currency: "BRL",
            })}
          </div>
        )}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-500">Grupos</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{resumo.totalGrupos}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-500">Itens</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{resumo.totalItens}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-500">Composições</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{resumo.totalComposicoes}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-medium uppercase text-slate-500">Total linhas</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{resumo.totalLinhas}</p>
          </div>
          <div className="col-span-2 rounded-lg border border-blue-200 bg-blue-50 p-4 shadow-sm sm:col-span-1">
            <p className="text-xs font-medium uppercase text-blue-700">Total itens (R$)</p>
            <p className="mt-1 text-2xl font-bold text-blue-900">
              {formatMoney(resumo.totalGeral)}
            </p>
          </div>
        </div>

        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-600">
            Análise determinística (sem IA)
          </p>
          <AnaliseOrcamentoResumo resultado={resultadoAnalise} />
        </div>

        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
            <FileSpreadsheet className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-semibold text-slate-700">
              Planilha analítica — {nomeProjeto}
              {currentUploadId ? (
                <span className="ml-2 font-normal text-slate-400">#{currentUploadId.slice(0, 8)}</span>
              ) : null}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="bg-[#1F4E78] text-white">
                  <th className="px-3 py-3 text-left font-semibold">Item / Rótulo</th>
                  <th className="px-3 py-3 text-left font-semibold">Código</th>
                  <th className="px-3 py-3 text-left font-semibold">Banco</th>
                  <th className="px-3 py-3 text-left font-semibold">Descrição</th>
                  <th className="px-3 py-3 text-center font-semibold">Análise</th>
                  <th className="px-3 py-3 text-left font-semibold">Tipo</th>
                  <th className="px-3 py-3 text-center font-semibold">Und</th>
                  <th className="px-3 py-3 text-right font-semibold">Quant.</th>
                  <th className="px-3 py-3 text-right font-semibold">BDI (%)</th>
                  <th className="px-3 py-3 text-right font-semibold">Porcent.</th>
                  <th className="px-3 py-3 text-right font-semibold">Valor Unit.</th>
                  <th className="px-3 py-3 text-right font-semibold">Total</th>
                </tr>
              </thead>
              <tbody>
                {linhas.map((linha, index) => {
                  const isEditable =
                    linha.tipoLinha === "item" || linha.tipoLinha === "composicao";
                  const itemId = String(linha.id);
                  const rowLock = getLockForItem(itemId);
                  const lockedByOther = isLockedByOther(itemId);
                  const lockTooltip = rowLock
                    ? `O engenheiro ${rowLock.user_name} está editando esta linha agora.`
                    : undefined;
                  return (
                  <tr
                    key={linha.id}
                    className={`border-b border-slate-100 ${rowClassName(linha.tipoLinha)} ${
                      lockedByOther ? "ring-1 ring-inset ring-orange-400" : ""
                    }`}
                    title={lockedByOther ? lockTooltip : undefined}
                  >
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      <span className="inline-flex items-center gap-1">
                        {lockedByOther ? (
                          <Lock
                            className="h-3.5 w-3.5 shrink-0 text-orange-500"
                            aria-label={lockTooltip}
                            title={lockTooltip}
                          />
                        ) : null}
                        {linha.itemNumero || linha.rotuloLinha}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">
                      {linha.tipoLinha === "grupo" ? "" : linha.codigo}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {linha.tipoLinha === "grupo" ? "" : linha.banco}
                    </td>
                    <td className={`px-3 py-2 ${linha.tipoLinha === "composicao" ? "pl-10" : ""}`}>
                      {linha.descricao}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <AnaliseOrcamentoStatusBadge
                        resultado={analisePorId.get(linha.id)}
                        compact
                      />
                    </td>
                    <td className="px-3 py-2 text-sm text-slate-600">
                      {linha.tipoLinha === "grupo" ? "" : linha.tipoCategoria}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {linha.tipoLinha === "grupo" ? "" : linha.unidade}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {isEditable ? (
                        <input
                          type="number"
                          step="0.0001"
                          min={0}
                          inputMode="decimal"
                          value={linha.quantidade || ""}
                          disabled={lockedByOther}
                          onFocus={() => handleCellFocus(itemId)}
                          onBlur={() => handleCellBlur(itemId)}
                          onChange={(e) =>
                            handleAnaliticoEdit(index, "quantidade", e.target.value)
                          }
                          className={lockedByOther ? EDITABLE_NUMERIC_LOCKED_CLASS : EDITABLE_NUMERIC_CLASS}
                          aria-label={`Quantidade — ${linha.descricao}`}
                          title={lockedByOther ? lockTooltip : undefined}
                        />
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {isEditable ? (
                        <input
                          type="number"
                          step="0.01"
                          min={0}
                          inputMode="decimal"
                          value={linha.bdi || ""}
                          disabled={lockedByOther}
                          onChange={(e) => handleAnaliticoEdit(index, "bdi", e.target.value)}
                          className={lockedByOther ? EDITABLE_NUMERIC_LOCKED_CLASS : EDITABLE_NUMERIC_CLASS}
                          aria-label={`BDI — ${linha.descricao}`}
                          title={lockedByOther ? lockTooltip : undefined}
                        />
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {linha.tipoLinha === "grupo" || linha.porcentagem <= 0
                        ? ""
                        : `${linha.porcentagem.toFixed(2)}%`}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {isEditable ? (
                        <input
                          type="number"
                          step="0.01"
                          min={0}
                          inputMode="decimal"
                          value={linha.valorUnitario || ""}
                          disabled={lockedByOther}
                          onFocus={() => handleCellFocus(itemId)}
                          onBlur={() => handleCellBlur(itemId)}
                          onChange={(e) =>
                            handleAnaliticoEdit(index, "valorUnitario", e.target.value)
                          }
                          className={lockedByOther ? EDITABLE_NUMERIC_LOCKED_CLASS : EDITABLE_NUMERIC_CLASS}
                          aria-label={`Valor unitário — ${linha.descricao}`}
                          title={lockedByOther ? lockTooltip : undefined}
                        />
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">
                      {linha.valorTotal > 0 ? formatMoney(linha.valorTotal) : ""}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="bg-slate-100 font-bold">
                  <td colSpan={10} className="px-3 py-3 text-right text-slate-700">
                    TOTAL GERAL (itens):
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-slate-900">
                    {formatMoney(resumo.totalGeral)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </main>

      {showRevisoes && currentUploadId ? (
        <RevisoesPanel
          projectId={currentUploadId}
          linhas={linhas}
          userName={currentUserName}
          onClose={() => setShowRevisoes(false)}
        />
      ) : null}

      <ExportModal
        open={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        uploadId={currentUploadId ?? undefined}
        nomeProjeto={nomeProjeto}
        linhas={linhas}
        defaultModelos={FULL_ORCAMENTO_EXPORT}
      />
    </div>
  );
};

export default OrcamentoAnalitico;
