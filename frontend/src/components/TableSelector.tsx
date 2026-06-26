import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { btnPrimary, btnSecondary } from "./ui/buttonClasses";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.1;
const INITIAL_ZOOM = 1;

function useWheelZoom(initialScale = INITIAL_ZOOM) {
  const [scale, setScale] = useState(initialScale);

  const applyWheelDelta = useCallback((delta: number) => {
    setScale((s) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, s + delta)));
  }, []);

  const resetZoom = useCallback(() => setScale(initialScale), [initialScale]);

  return { scale, applyWheelDelta, resetZoom, setScale };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function CarouselTableImage({
  src,
  alt,
  scale,
  applyWheelDelta,
  onResetZoom,
}: {
  src: string;
  alt: string;
  scale: number;
  applyWheelDelta: (delta: number) => void;
  onResetZoom: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [fitWidth, setFitWidth] = useState<number | null>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [containerSize, setContainerSize] = useState<{ w: number; h: number } | null>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragState = useRef({ startX: 0, startY: 0, originX: 0, originY: 0 });
  const panRef = useRef(pan);
  panRef.current = pan;

  const padding = 32;
  const displayWidthPx =
    fitWidth != null ? Math.round(fitWidth * scale) : null;
  const displayHeightPx =
    naturalSize && fitWidth
      ? Math.round((naturalSize.h / naturalSize.w) * fitWidth * scale)
      : null;

  const getPanBounds = useCallback(() => {
    if (!containerSize || !displayWidthPx || !displayHeightPx) {
      return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
    }
    const innerW = containerSize.w - padding;
    const innerH = containerSize.h - padding;
    const overflowX = Math.max(0, displayWidthPx - innerW);
    const overflowY = Math.max(0, displayHeightPx - innerH);
    const margin = 24;
    return {
      minX: -(overflowX / 2 + margin),
      maxX: overflowX / 2 + margin,
      minY: -(overflowY / 2 + margin),
      maxY: overflowY / 2 + margin,
    };
  }, [containerSize, displayWidthPx, displayHeightPx]);

  const clampPan = useCallback(
    (next: { x: number; y: number }) => {
      const bounds = getPanBounds();
      return {
        x: clamp(next.x, bounds.minX, bounds.maxX),
        y: clamp(next.y, bounds.minY, bounds.maxY),
      };
    },
    [getPanBounds],
  );

  const canPan = useMemo(() => {
    if (!containerSize || !displayWidthPx || !displayHeightPx) return false;
    const innerW = containerSize.w - padding;
    const innerH = containerSize.h - padding;
    return displayWidthPx > innerW + 4 || displayHeightPx > innerH + 4;
  }, [containerSize, displayWidthPx, displayHeightPx]);

  useEffect(() => {
    setFitWidth(null);
    setNaturalSize(null);
    setPan({ x: 0, y: 0 });
  }, [src]);

  useEffect(() => {
    setPan((current) => clampPan(current));
  }, [scale, displayWidthPx, displayHeightPx, containerSize, clampPan]);

  const measureFit = useCallback(() => {
    const img = imgRef.current;
    const container = containerRef.current;
    if (!img || !container || img.naturalWidth === 0) return;
    const available = Math.max(200, container.clientWidth - padding);
    const fitted = Math.min(img.naturalWidth, available);
    setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    setFitWidth(fitted);
    setContainerSize({ w: container.clientWidth, h: container.clientHeight });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      applyWheelDelta(e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [applyWheelDelta]);

  useEffect(() => {
    const onResize = () => measureFit();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [measureFit]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!canPan || e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setIsDragging(true);
    dragState.current = {
      startX: e.clientX,
      startY: e.clientY,
      originX: panRef.current.x,
      originY: panRef.current.y,
    };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.clientX - dragState.current.startX;
    const dy = e.clientY - dragState.current.startY;
    setPan(
      clampPan({
        x: dragState.current.originX + dx,
        y: dragState.current.originY + dy,
      }),
    );
  };

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setIsDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const handleDoubleClick = () => {
    onResetZoom();
    setPan({ x: 0, y: 0 });
  };

  const maxZoomBeforeBlur =
    naturalSize && fitWidth
      ? Math.round((naturalSize.w / fitWidth) * 10) / 10
      : null;

  return (
    <div className="space-y-2">
      <div
        ref={containerRef}
        className={`relative min-h-[min(32rem,58vh)] w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80 ${
          canPan ? (isDragging ? "cursor-grabbing" : "cursor-grab") : "cursor-default"
        }`}
        style={{ touchAction: canPan ? "none" : "auto" }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={handleDoubleClick}
        role="region"
        aria-label={alt}
      >
        <div
          className="flex min-h-[min(32rem,58vh)] w-full items-center justify-center"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px)`,
            transition: isDragging ? "none" : "transform 0.08s ease-out",
            willChange: "transform",
          }}
        >
          <img
            ref={imgRef}
            src={src}
            alt={alt}
            className="block max-h-none select-none"
            draggable={false}
            decoding="sync"
            onLoad={measureFit}
            style={{
              width: displayWidthPx ? `${displayWidthPx}px` : `calc(100% - ${padding}px)`,
              height: "auto",
              maxWidth: "none",
              imageRendering: "auto",
              pointerEvents: "none",
              userSelect: "none",
            }}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-slate-500">
        <span>
          Roda do mouse para zoom
          {canPan ? " · arraste para mover" : ""}
          {" · duplo clique para redefinir"}
        </span>
        {maxZoomBeforeBlur != null && maxZoomBeforeBlur > 1 && (
          <span className="text-slate-400">· Nítido até {maxZoomBeforeBlur}x</span>
        )}
        <span className="font-medium text-slate-600">{Math.round(scale * 100)}%</span>
      </div>
    </div>
  );
}

export interface MockTableOption {
  id: string;
  name: string;
  page: number;
  preview: string;
  imagem_base64?: string;
  preview_rows?: string[][];
  row_count?: number;
  budget_score?: number;
  is_budget_likely?: boolean;
  source?: string;
}

interface TableSelectorProps {
  tables: MockTableOption[];
  loading: boolean;
  disabled?: boolean;
  selectedIds?: string[];
  layout?: "default" | "large";
  confirmLabel?: string;
  onSelect: (table: MockTableOption) => void;
  onSetSelectedIds?: (ids: string[]) => void;
  onConfirm?: () => void;
}

export const TableSelector: React.FC<TableSelectorProps> = ({
  tables,
  loading,
  disabled = false,
  selectedIds = [],
  confirmLabel = "Processar com IA",
  onSelect,
  onSetSelectedIds,
  onConfirm,
}) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const { scale, applyWheelDelta, resetZoom } = useWheelZoom(INITIAL_ZOOM);

  const sortedTables = useMemo(
    () =>
      [...tables].sort(
        (a, b) =>
          a.page - b.page ||
          (b.row_count ?? 0) - (a.row_count ?? 0) ||
          a.name.localeCompare(b.name),
      ),
    [tables],
  );

  const currentTable = sortedTables[currentIndex] ?? null;
  const total = sortedTables.length;
  const isSelected = currentTable ? selectedIds.includes(currentTable.id) : false;

  useEffect(() => {
    resetZoom();
    setCurrentIndex(0);
  }, [tables, resetZoom]);

  useEffect(() => {
    resetZoom();
  }, [currentIndex, resetZoom]);

  useEffect(() => {
    if (currentIndex >= total && total > 0) {
      setCurrentIndex(total - 1);
    }
  }, [currentIndex, total]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (total <= 1) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setCurrentIndex((i) => Math.max(0, i - 1));
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setCurrentIndex((i) => Math.min(total - 1, i + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [total]);

  const goPrev = () => setCurrentIndex((i) => Math.max(0, i - 1));
  const goNext = () => setCurrentIndex((i) => Math.min(total - 1, i + 1));

  const handleSelectLikely = () => {
    const ids = tables.filter((t) => t.is_budget_likely).map((t) => t.id);
    onSetSelectedIds?.(ids);
  };

  if (loading) {
    return (
      <div
        className="mt-6 flex min-h-[24rem] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
        role="status"
        aria-label="Detectando tabelas"
      >
        <div className="h-48 w-full max-w-2xl animate-pulse rounded-xl bg-slate-100" />
        <p className="mt-4 text-sm text-slate-500">Detectando tabelas no PDF…</p>
      </div>
    );
  }

  if (!currentTable) {
    return null;
  }

  return (
    <div className={`mt-6 w-full ${disabled ? "pointer-events-none opacity-60" : ""}`}>
      {/* Cabeçalho */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-700">
            {total} planilha{total !== 1 ? "s" : ""} encontrada{total !== 1 ? "s" : ""}
          </p>
          <p className="text-xs text-slate-500">
            Use as setas para navegar · marque as planilhas que deseja analisar
          </p>
        </div>
        {tables.some((t) => t.is_budget_likely) && (
          <button
            type="button"
            className={`${btnSecondary} gap-1.5 px-3 py-1.5 text-xs`}
            onClick={handleSelectLikely}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Selecionar prováveis
          </button>
        )}
      </div>

      {/* Carrossel */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-base font-semibold text-slate-900 sm:text-lg">
                {currentTable.name}
              </h3>
              <p className="mt-0.5 text-sm text-slate-500">
                Planilha {currentIndex + 1} de {total}
                {currentTable.row_count != null && ` · ${currentTable.row_count} linhas`}
              </p>
            </div>
            <label className="flex shrink-0 cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100">
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onSelect(currentTable)}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Selecionar esta planilha
            </label>
          </div>
          {currentTable.is_budget_likely && (
            <span className="mt-2 inline-block rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
              Provável planilha de orçamento
            </span>
          )}
        </div>

        <div className="relative flex items-stretch px-2 py-4 sm:px-4 sm:py-6">
          <button
            type="button"
            onClick={goPrev}
            disabled={currentIndex === 0}
            className="absolute top-1/2 left-1 z-10 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-md transition hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-30 sm:left-3 sm:h-12 sm:w-12"
            aria-label="Planilha anterior"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>

          <div className="mx-12 w-full min-w-0 flex-1 sm:mx-16">
            {currentTable.imagem_base64 ? (
              <>
                <CarouselTableImage
                  src={`data:image/png;base64,${currentTable.imagem_base64}`}
                  alt={currentTable.name}
                  scale={scale}
                  applyWheelDelta={applyWheelDelta}
                  onResetZoom={resetZoom}
                />
              </>
            ) : (
              <div className="flex min-h-[min(20rem,40vh)] items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
                <p>{currentTable.preview || "Imagem indisponível para esta planilha."}</p>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={goNext}
            disabled={currentIndex >= total - 1}
            className="absolute top-1/2 right-1 z-10 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 shadow-md transition hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-30 sm:right-3 sm:h-12 sm:w-12"
            aria-label="Próxima planilha"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        </div>

        {/* Indicadores */}
        {total > 1 && (
          <div className="flex flex-wrap items-center justify-center gap-2 border-t border-slate-100 px-4 py-3">
            {sortedTables.map((table, idx) => {
              const active = idx === currentIndex;
              const selected = selectedIds.includes(table.id);
              return (
                <button
                  key={table.id}
                  type="button"
                  onClick={() => setCurrentIndex(idx)}
                  className={`h-2.5 rounded-full transition-all ${
                    active
                      ? "w-8 bg-blue-600"
                      : selected
                        ? "w-2.5 bg-blue-300 hover:bg-blue-400"
                        : "w-2.5 bg-slate-300 hover:bg-slate-400"
                  }`}
                  aria-label={`Ir para planilha ${idx + 1}: ${table.name}`}
                  aria-current={active ? "true" : undefined}
                />
              );
            })}
          </div>
        )}
      </div>

      {onConfirm && (
        <div className="mt-6 flex flex-col gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-600">
            {selectedIds.length === 0
              ? "Selecione ao menos uma planilha para continuar."
              : `${selectedIds.length} planilha(s) selecionada(s)`}
          </p>
          <button
            type="button"
            className={`${btnPrimary} px-8 py-3.5 text-base font-semibold shadow-sm sm:shrink-0`}
            onClick={onConfirm}
            disabled={disabled || selectedIds.length === 0}
          >
            {confirmLabel}
            {selectedIds.length > 0 ? ` (${selectedIds.length})` : ""}
          </button>
        </div>
      )}
    </div>
  );
};
