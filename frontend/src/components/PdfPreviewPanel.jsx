/**
 * components/PdfPreviewPanel.jsx
 * --------------------------------
 * Feature 2: PDF preview panel.
 *
 * Renders a resizable right panel showing the selected document's PDF.
 * Uses react-pdf (which wraps PDF.js) to render pages client-side.
 *
 * Props:
 *   doc      — the full document object from useDocuments (or null)
 *   onClose  — callback to close the panel
 *
 * Controls:
 *   ← / → buttons for prev/next page
 *   − / + buttons for zoom out/in
 *   Page X of Y indicator
 *   Scrollable page canvas
 *   Loading spinner while PDF loads
 *   Error state with retry
 *
 * PDF.js worker:
 *   We configure the worker URL once at module level using the CDN path.
 *   This avoids bundling the worker (which is ~1MB) into the main chunk.
 */

import React, { useState, useCallback, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import {
  X,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Loader2,
  AlertCircle,
  FileText,
  RotateCcw,
} from 'lucide-react'
import { getDocumentFileUrl } from '../api/client'

// Configure PDF.js worker — use the CDN version that matches pdfjs-dist
// This must be set before any <Document> renders.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();
// Zoom steps: each click multiplies or divides by this factor
const ZOOM_STEP = 0.2
const MIN_ZOOM = 0.5
const MAX_ZOOM = 3.0
const DEFAULT_ZOOM = 1.0

export default function PdfPreviewPanel({ doc, onClose }) {
  const [numPages, setNumPages] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [scale, setScale] = useState(DEFAULT_ZOOM)
  const [loadError, setLoadError] = useState(null)
  const [isDocLoading, setIsDocLoading] = useState(true)

  // Reset page and zoom whenever the document changes
  useEffect(() => {
    setCurrentPage(1)
    setScale(DEFAULT_ZOOM)
    setNumPages(null)
    setLoadError(null)
    setIsDocLoading(true)
  }, [doc?.doc_id])

  const onDocumentLoadSuccess = useCallback(({ numPages }) => {
    setNumPages(numPages)
    setIsDocLoading(false)
    setLoadError(null)
  }, [])

  const onDocumentLoadError = useCallback((error) => {
    setLoadError(error?.message || 'Failed to load PDF.')
    setIsDocLoading(false)
  }, [])

  const goToPrev = () => setCurrentPage((p) => Math.max(1, p - 1))
  const goToNext = () => setCurrentPage((p) => Math.min(numPages ?? p, p + 1))
  const zoomIn = () => setScale((s) => Math.min(MAX_ZOOM, +(s + ZOOM_STEP).toFixed(1)))
  const zoomOut = () => setScale((s) => Math.max(MIN_ZOOM, +(s - ZOOM_STEP).toFixed(1)))
  const resetZoom = () => setScale(DEFAULT_ZOOM)
  const retry = () => {
    setLoadError(null)
    setIsDocLoading(true)
  }

  if (!doc) return null

  const fileUrl = getDocumentFileUrl(doc.doc_id)

  return (
    <div className="w-[480px] shrink-0 flex flex-col bg-ink-950 border-l border-ink-800 h-full overflow-hidden animate-slide-in">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded bg-ink-800 flex items-center justify-center shrink-0">
            <FileText className="w-3.5 h-3.5 text-ink-400" />
          </div>
          <span
            className="text-xs font-medium text-ink-200 truncate"
            title={doc.filename}
          >
            {_displayName(doc.filename)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded flex items-center justify-center text-ink-500 hover:text-ink-200 hover:bg-ink-800 transition-colors shrink-0 ml-2"
          title="Close preview"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Controls ───────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 bg-ink-900/60 shrink-0 gap-2">

        {/* Page navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={goToPrev}
            disabled={currentPage <= 1 || !numPages}
            className="w-7 h-7 rounded flex items-center justify-center text-ink-400 hover:text-ink-200 hover:bg-ink-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>

          <span className="text-[11px] font-mono text-ink-400 min-w-[64px] text-center">
            {numPages
              ? `${currentPage} / ${numPages}`
              : isDocLoading
                ? '…'
                : '—'}
          </span>

          <button
            onClick={goToNext}
            disabled={!numPages || currentPage >= numPages}
            className="w-7 h-7 rounded flex items-center justify-center text-ink-400 hover:text-ink-200 hover:bg-ink-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={zoomOut}
            disabled={scale <= MIN_ZOOM}
            className="w-7 h-7 rounded flex items-center justify-center text-ink-400 hover:text-ink-200 hover:bg-ink-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={resetZoom}
            className="text-[11px] font-mono text-ink-400 hover:text-ink-200 transition-colors min-w-[42px] text-center px-1 py-1 rounded hover:bg-ink-800"
            title="Reset zoom"
          >
            {Math.round(scale * 100)}%
          </button>

          <button
            onClick={zoomIn}
            disabled={scale >= MAX_ZOOM}
            className="w-7 h-7 rounded flex items-center justify-center text-ink-400 hover:text-ink-200 hover:bg-ink-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── PDF canvas area ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto bg-ink-950 flex flex-col items-center py-4 px-2">

        {/* Loading state */}
        {isDocLoading && !loadError && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <Loader2 className="w-7 h-7 text-ink-500 animate-spin" />
            <p className="text-[11px] text-ink-600">Loading PDF…</p>
          </div>
        )}

        {/* Error state */}
        {loadError && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 px-6 text-center">
            <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
              <AlertCircle className="w-6 h-6 text-rose-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-rose-300 mb-1">Failed to load PDF</p>
              <p className="text-[11px] text-ink-500 leading-relaxed">{loadError}</p>
            </div>
            <button
              onClick={retry}
              className="flex items-center gap-1.5 text-xs text-ink-400 hover:text-ink-200 bg-ink-800 hover:bg-ink-700 px-3 py-1.5 rounded-lg border border-ink-700 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              Retry
            </button>
          </div>
        )}

        {/* PDF document */}
        {!loadError && (
          <Document
            key={`${doc.doc_id}-${loadError}`}
            file={fileUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={null}   // We show our own loading indicator above
            className="flex flex-col items-center"
          >
            {/* Only render the current page for performance */}
            {numPages && (
              <Page
                pageNumber={currentPage}
                scale={scale}
                renderTextLayer={false}    // Skip text layer — not needed for preview
                renderAnnotationLayer={false}
                loading={
                  <div className="flex items-center justify-center w-full py-8">
                    <Loader2 className="w-5 h-5 text-ink-600 animate-spin" />
                  </div>
                }
                className="shadow-2xl shadow-black/60"
              />
            )}
          </Document>
        )}
      </div>
    </div>
  )
}

/** Strip the YYYYMMDD_HHMMSS_ prefix from the stored filename for display. */
function _displayName(filename) {
  if (!filename) return 'Unknown'
  const match = filename.match(/^\d{8}_\d{6}_(.+)$/)
  return match ? match[1] : filename
}
