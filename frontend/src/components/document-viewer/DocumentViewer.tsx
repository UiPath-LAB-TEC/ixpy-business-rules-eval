import { FileWarning, LocateFixed, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { EvidenceDetail } from '../../api/types';

type ViewerState = 'loading' | 'rendered' | 'fallback';
type PdfViewport = { width: number; height: number };
type PdfRenderTask = { promise: Promise<void>; cancel?: () => void };
type PdfPageProxy = {
  getViewport: (options: { scale: number }) => PdfViewport;
  render: (options: {
    canvas: HTMLCanvasElement;
    viewport: unknown;
  }) => PdfRenderTask;
};
type PdfDocumentProxy = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageProxy>;
  destroy?: () => Promise<void> | void;
};

export function DocumentViewer({ filename, evidence }: { filename: string; evidence: EvidenceDetail | null }) {
  const pageSurfaceRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const canvasRefs = useRef<Record<number, HTMLCanvasElement | null>>({});
  const scrollFrameRef = useRef<number | null>(null);
  const previousZoomRef = useRef(1);
  const [viewerState, setViewerState] = useState<ViewerState>('loading');
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pdfDocument, setPdfDocument] = useState<PdfDocumentProxy | null>(null);
  const [renderedPages, setRenderedPages] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setPageNumber(1);
    setPageCount(null);
    setPdfDocument(null);
    setRenderedPages({});
    setViewerState('loading');
    pageRefs.current = {};
    canvasRefs.current = {};
  }, [filename]);

  useEffect(() => {
    if (navigator.userAgent.includes('jsdom')) return;
    let cancelled = false;
    let loadedDocument: PdfDocumentProxy | null = null;
    setViewerState('loading');
    Promise.all([
      import('pdfjs-dist'),
      import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
    ])
      .then(([pdfjs, worker]) => {
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        return pdfjs.getDocument({
          url: api.documentFileUrl(filename),
          wasmUrl: new URL('/pdfjs-wasm/', window.location.href).href,
        }).promise;
      })
      .then((document) => {
        loadedDocument = document as unknown as PdfDocumentProxy;
        if (cancelled) {
          void loadedDocument.destroy?.();
          return;
        }
        setPageCount(loadedDocument.numPages);
        setPdfDocument(loadedDocument);
      })
      .catch(() => {
        if (!cancelled) setViewerState('fallback');
      });
    return () => {
      cancelled = true;
      void loadedDocument?.destroy?.();
    };
  }, [filename]);

  useEffect(() => {
    if (!pdfDocument || !pageCount) return;
    const document = pdfDocument;
    const totalPages = pageCount;
    let cancelled = false;
    const renderTasks: PdfRenderTask[] = [];
    setRenderedPages({});
    setViewerState('rendered');

    async function renderPages() {
      try {
        for (let pageIndex = 1; pageIndex <= totalPages; pageIndex += 1) {
          if (cancelled) return;
          const canvas = canvasRefs.current[pageIndex];
          if (!canvas) throw new Error('PDF canvas is not ready');

          const page = await document.getPage(pageIndex);
          if (cancelled) return;
          const viewport = page.getViewport({ scale: 1.15 });
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const renderTask = page.render({ canvas, viewport });
          renderTasks.push(renderTask);
          await renderTask.promise;
          if (!cancelled) {
            setRenderedPages((current) => ({ ...current, [pageIndex]: true }));
          }
        }
      } catch {
        if (!cancelled) setViewerState('fallback');
      }
    }

    void renderPages();
    return () => {
      cancelled = true;
      renderTasks.forEach((task) => {
        try {
          task.cancel?.();
        } catch {
          // PDF.js can throw if a completed render task is cancelled during cleanup.
        }
      });
    };
  }, [pdfDocument, pageCount]);

  useEffect(() => {
    return () => {
      if (scrollFrameRef.current !== null) window.cancelAnimationFrame(scrollFrameRef.current);
    };
  }, []);

  useEffect(() => {
    if (viewerState !== 'rendered') return;
    const evidencePage = evidence?.page_number;
    if (!evidencePage || evidencePage < 1) return;
    const nextPage = pageCount ? Math.min(evidencePage, pageCount) : evidencePage;
    setPageNumber((current) => current === nextPage ? current : nextPage);
    const frame = window.requestAnimationFrame(() => {
      pageRefs.current[nextPage]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [evidence?.page_number, pageCount, viewerState]);

  useEffect(() => {
    if (previousZoomRef.current === zoom) return;
    previousZoomRef.current = zoom;
    if (viewerState !== 'rendered') return;
    const frame = window.requestAnimationFrame(() => {
      pageRefs.current[pageNumber]?.scrollIntoView({ block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [zoom, viewerState]);

  function goToPage(requestedPage: number) {
    if (!pageCount) return;
    const nextPage = Math.min(Math.max(requestedPage, 1), pageCount);
    setPageNumber(nextPage);
    window.requestAnimationFrame(() => {
      pageRefs.current[nextPage]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function handlePageKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (viewerState !== 'rendered' || !pageCount) return;
    if (event.key === 'PageUp') {
      event.preventDefault();
      goToPage(pageNumber - 1);
    }
    if (event.key === 'PageDown') {
      event.preventDefault();
      goToPage(pageNumber + 1);
    }
    if (event.key === 'Home') {
      event.preventDefault();
      goToPage(1);
    }
    if (event.key === 'End') {
      event.preventDefault();
      goToPage(pageCount);
    }
  }

  function updatePageFromScroll() {
    const surface = pageSurfaceRef.current;
    if (viewerState !== 'rendered' || !pageCount || !surface) return;
    const surfaceRect = surface.getBoundingClientRect();
    const anchorY = surfaceRect.top + Math.min(120, surfaceRect.height * 0.3);
    let visiblePage = pageNumber;
    let closestDistance = Number.POSITIVE_INFINITY;

    for (let pageIndex = 1; pageIndex <= pageCount; pageIndex += 1) {
      const pageElement = pageRefs.current[pageIndex];
      if (!pageElement) continue;
      const pageRect = pageElement.getBoundingClientRect();
      if (anchorY >= pageRect.top && anchorY <= pageRect.bottom) {
        visiblePage = pageIndex;
        break;
      }
      const distance = Math.min(Math.abs(pageRect.top - anchorY), Math.abs(pageRect.bottom - anchorY));
      if (distance < closestDistance) {
        closestDistance = distance;
        visiblePage = pageIndex;
      }
    }

    setPageNumber((current) => current === visiblePage ? current : visiblePage);
  }

  function handleSurfaceScroll() {
    if (scrollFrameRef.current !== null) return;
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = null;
      updatePageFromScroll();
    });
  }

  const highlight = viewerState === 'rendered' ? evidence?.bbox : null;
  const highlightPage = evidence?.page_number ?? pageNumber;
  const pageNumbers = pageCount ? Array.from({ length: pageCount }, (_, index) => index + 1) : [];

  return (
    <section className="viewer-panel" aria-label="Document viewer">
      <div className="viewer-header">
        <span>{filename}</span>
        <div className="viewer-actions">
          <button
            aria-label="Zoom out"
            className="icon-only"
            disabled={zoom <= 0.5}
            title="Zoom out"
            onClick={() => setZoom((current) => Math.max(0.5, Number((current - 0.25).toFixed(2))))}
          >
            <ZoomOut size={17} aria-hidden />
          </button>
          <span className="zoom-label" aria-live="polite">{Math.round(zoom * 100)}%</span>
          <button
            aria-label="Zoom in"
            className="icon-only"
            disabled={zoom >= 3}
            title="Zoom in"
            onClick={() => setZoom((current) => Math.min(3, Number((current + 0.25).toFixed(2))))}
          >
            <ZoomIn size={17} aria-hidden />
          </button>
          <button aria-label="Reset zoom" className="icon-only" title="Reset zoom" onClick={() => setZoom(1)}>
            <RotateCcw size={17} aria-hidden />
          </button>
          <span className="page-position" aria-live="polite">Page {pageNumber}{pageCount ? ` / ${pageCount}` : ''}</span>
          <a href={api.documentFileUrl(filename)} target="_blank" rel="noreferrer">Open source</a>
        </div>
      </div>
      <div
        className="page-surface"
        ref={pageSurfaceRef}
        tabIndex={0}
        onKeyDown={handlePageKeyDown}
        onScroll={handleSurfaceScroll}
      >
        {viewerState === 'fallback' ? (
          <div className="pdf-fallback" style={{ width: `${zoom * 100}%` }}>
            <div className="viewer-status">
              PDF.js could not render this file. Showing the browser PDF viewer instead.
            </div>
            <iframe
              className="pdf-fallback-frame"
              src={api.documentFileUrl(filename)}
              title={`PDF fallback viewer for ${filename}`}
            />
          </div>
        ) : (
          <div
            className={viewerState === 'rendered' ? 'pdf-document' : 'mock-document'}
            style={{ width: `${zoom * 100}%` }}
          >
            {viewerState === 'loading' && (
              <div className="viewer-status">Loading document pages...</div>
            )}
            {pageNumbers.map((page) => (
              <div
                key={page}
                className={renderedPages[page] ? 'pdf-page ready' : 'pdf-page loading'}
                ref={(element) => {
                  pageRefs.current[page] = element;
                }}
                role="img"
                aria-label={`PDF page ${page}`}
              >
                <canvas
                  ref={(element) => {
                    canvasRefs.current[page] = element;
                  }}
                  className={renderedPages[page] ? 'pdf-canvas ready' : 'pdf-canvas'}
                  aria-hidden
                />
                {!renderedPages[page] && (
                  <div className="viewer-status">Loading page {page}...</div>
                )}
                {highlight && highlightPage === page && renderedPages[page] && (
                  <div
                    className="highlight-box"
                    style={{
                      left: `${highlight.x * 100}%`,
                      top: `${highlight.y * 100}%`,
                      width: `${highlight.width * 100}%`,
                      height: `${highlight.height * 100}%`,
                    }}
                  >
                    <LocateFixed size={14} aria-hidden />
                  </div>
                )}
              </div>
            ))}
            {viewerState === 'loading' && !pageCount && (
              <>
                <div className="doc-line strong" />
                <div className="doc-line" />
                <div className="doc-line medium" />
                <div className="doc-table">
                  {Array.from({ length: 8 }).map((_, index) => <div key={index} className="doc-cell" />)}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      {evidence && !evidence.bbox && (
        <div className="fallback-evidence">
          <FileWarning size={18} aria-hidden />
          <span>
            {evidence.filename} · {evidence.source_field_id ?? 'field group n/a'} · {evidence.source_field ?? 'field n/a'} · row {evidence.row_index ?? 'n/a'} · column {evidence.column_index ?? 'n/a'} · {evidence.evidence_role ?? 'evidence'}
          </span>
        </div>
      )}
    </section>
  );
}
