import { FileWarning, LocateFixed, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { EvidenceDetail } from '../../api/types';

type ViewerState = 'loading' | 'rendered' | 'fallback';

export function DocumentViewer({ filename, evidence }: { filename: string; evidence: EvidenceDetail | null }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [viewerState, setViewerState] = useState<ViewerState>('loading');
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    setPageNumber(1);
    setPageCount(null);
    setViewerState('loading');
  }, [filename]);

  useEffect(() => {
    const evidencePage = evidence?.page_number;
    if (!evidencePage || evidencePage < 1) return;
    setPageNumber((current) => {
      const nextPage = pageCount ? Math.min(evidencePage, pageCount) : evidencePage;
      return current === nextPage ? current : nextPage;
    });
  }, [evidence?.page_number, pageCount]);

  useEffect(() => {
    if (navigator.userAgent.includes('jsdom')) return;
    let cancelled = false;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
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
      .then(async (document) => {
        if (!cancelled) setPageCount(document.numPages);
        const safePage = Math.min(Math.max(pageNumber, 1), document.numPages);
        if (safePage !== pageNumber) setPageNumber(safePage);
        return document.getPage(safePage);
      })
      .then((page) => {
        if (cancelled) return;
        const viewport = page.getViewport({ scale: 1.15 });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        return page.render({ canvas, canvasContext: context, viewport }).promise;
      })
      .then(() => {
        if (!cancelled) setViewerState('rendered');
      })
      .catch(() => {
        if (!cancelled) setViewerState('fallback');
      });
    return () => {
      cancelled = true;
    };
  }, [filename, pageNumber]);

  const canPageBackward = viewerState === 'rendered' && pageNumber > 1;
  const canPageForward = viewerState === 'rendered' && pageCount !== null && pageNumber < pageCount;
  const highlight = viewerState === 'rendered' ? evidence?.bbox : null;

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
          <a href={api.documentFileUrl(filename)} target="_blank" rel="noreferrer">Open source</a>
        </div>
      </div>
      <div className="page-controls" aria-label="PDF page controls">
        <button disabled={!canPageBackward} onClick={() => setPageNumber((current) => Math.max(1, current - 1))}>
          Previous page
        </button>
        <span aria-live="polite">Page {pageNumber}{pageCount ? ` / ${pageCount}` : ''}</span>
        <button disabled={!canPageForward} onClick={() => setPageNumber((current) => Math.min(pageCount ?? current, current + 1))}>
          Next page
        </button>
      </div>
      <div className="page-surface">
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
            <canvas
              ref={canvasRef}
              className={viewerState === 'rendered' ? 'pdf-canvas ready' : 'pdf-canvas'}
              aria-label={`PDF page ${pageNumber}`}
            />
            {viewerState === 'loading' && (
              <div className="viewer-status">Loading document page...</div>
            )}
            {viewerState === 'loading' && (
            <>
              <div className="doc-line strong" />
              <div className="doc-line" />
              <div className="doc-line medium" />
              <div className="doc-table">
                {Array.from({ length: 8 }).map((_, index) => <div key={index} className="doc-cell" />)}
              </div>
            </>
            )}
            {highlight && (
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
