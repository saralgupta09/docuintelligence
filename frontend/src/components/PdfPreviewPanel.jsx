/**
 * components/PdfPreviewPanel.jsx
 * --------------------------------
 * Highlight feature changes:
 *
 *  1. Accepts a new `highlights` prop:
 *       Array<{ chunk_id, text, page_num, filename, score }>
 *     Passed from App.jsx; contains every retrieved chunk that belongs to
 *     the currently displayed document.
 *
 *  2. renderTextLayer is now TRUE.
 *     Imports 'react-pdf/dist/Page/TextLayer.css' for correct positioning.
 *     This makes PDF.js render an invisible text-selection layer on top of
 *     the canvas; our <mark> tags create visible coloured rectangles over
 *     the matching text in the canvas.
 *
 *  3. customTextRenderer — per-text-item callback from react-pdf.
 *     For each text item (str) on the current page:
 *       • Build a Set of n-gram phrases (bigrams…6-grams) from the retrieved
 *         chunk texts for that page (buildPhraseSet).
 *       • A span is highlighted only if its normalised text is an EXACT MEMBER
 *         of that phrase Set (Set.has — O(1) lookup).
 *       • This prevents over-highlighting: common domain words like "skills"
 *         or "engineering" only match when they appear in the *exact phrase
 *         context* of the retrieved chunk, not as isolated tokens elsewhere
 *         on the page.
 *       • If matched: return '<mark class="pdf-highlight">…</mark>'
 *       • HTML special characters in str are escaped before injection
 *
 *  4. Auto-navigation — useEffect watches `highlights` and navigates to
 *     the lowest page_num present in highlights when the set changes
 *     (i.e. after a new question is answered).  Does not override manual
 *     navigation; only fires when highlights change identity.
 *
 *  5. Per-page match count badge — "N matches" pill shown next to the
 *     page counter when the current page has highlighted chunks.
 *
 *  6. Highlight strip — a compact row of page-number pills at the bottom
 *     of the controls bar, one per page that has highlights.  Clicking one
 *     navigates to that page.
 *
 * All other behaviour — zoom, page navigation buttons, loading/error states,
 * doc reset on doc_id change, header, close button — is completely unchanged.
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'          // required for text layer positioning
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
  Highlighter,
} from 'lucide-react'
import { getDocumentFileUrl } from '../api/client'

// Configure PDF.js worker — CDN version matching pdfjs-dist
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString()

const ZOOM_STEP = 0.2
const MIN_ZOOM = 0.5
const MAX_ZOOM = 3.0
const DEFAULT_ZOOM = 1.0

// ── HTML escaping helper ───────────────────────────────────────────────────────
// customTextRenderer return values are injected via dangerouslySetInnerHTML,
// so we must escape special characters in the raw PDF text items.
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ── Text normalisation ────────────────────────────────────────────────────────
function normalise(s) {
  return s
    .toLowerCase()
    .replace(/[^\w\s]/g, '')   // strip punctuation — keeps letters, digits, whitespace
    .replace(/\s+/g, ' ')      // collapse whitespace
    .trim()
}

// ── Phrase-set builder ────────────────────────────────────────────────────────
// Indexes a retrieved chunk into a Set of n-gram phrases (bigrams … PHRASE_MAX_WORDS-grams)
// plus any single token that is long enough to be considered uniquely identifying.
//
// WHY THIS FIXES OVER-HIGHLIGHTING
// ─────────────────────────────────
// The previous algorithm asked: "does the chunk text *contain* this PDF span?"
// That is a substring check in the wrong direction.  Because the chunk is a
// large blob (500–1000 chars of text extracted from the same page), almost
// every individual word on the page matches — flooding the highlight layer.
//
// The correct question is: "is this PDF span an *exact phrase* from the chunk?"
// A PDF.js text span is typically 1–6 words long.  If that exact word sequence
// appears in the chunk, it is genuinely part of the retrieved passage.
// Common domain words like "skills" or "engineering" appear everywhere on the
// page, but they only appear as a *specific bigram/trigram* in the retrieved
// chunk (e.g. "machine learning skills"), so standalone occurrences of "skills"
// in section headers or other paragraphs are not in the phrase set and won't match.
//
const PHRASE_MAX_WORDS = 6        // longest n-gram indexed
const PHRASE_MIN_WORDS = 2        // require at least a bigram (avoids single-word noise)
const UNIQUE_TOKEN_MIN_CHARS = 7  // single tokens this long are specific enough on their own
                                  // (e.g. "8.617", "roorkee", "langchain", "electrical")

function buildPhraseSet(chunkText) {
  const words = normalise(chunkText).split(' ').filter(Boolean)
  const phrases = new Set()

  // Index all n-grams of length PHRASE_MIN_WORDS … PHRASE_MAX_WORDS
  for (let n = PHRASE_MIN_WORDS; n <= PHRASE_MAX_WORDS; n++) {
    for (let i = 0; i <= words.length - n; i++) {
      phrases.add(words.slice(i, i + n).join(' '))
    }
  }

  // Also index long single tokens — proper nouns, numbers, tech terms
  for (const w of words) {
    if (w.length >= UNIQUE_TOKEN_MIN_CHARS) {
      phrases.add(w)
    }
  }

  return phrases
}

// ── Span matching ─────────────────────────────────────────────────────────────
// Returns true if the PDF.js span `item` should be highlighted.
// `pagePhraseSet` is the union phrase-set for all retrieved chunks on this page.
//
// A span matches when its normalised text is an EXACT MEMBER of the phrase set.
// This means the span must be a verbatim n-gram from the retrieved passage —
// not merely a word that happens to occur somewhere in the chunk blob.
//
function shouldHighlight(item, pagePhraseSet) {
  if (!pagePhraseSet || pagePhraseSet.size === 0) return false
  const normItem = normalise(item)
  if (normItem.length < 3) return false          // skip trivial spans
  return pagePhraseSet.has(normItem)
}


export default function PdfPreviewPanel({ doc, onClose, highlights = [] }) {
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

  // ── Highlight feature: auto-navigate to first highlighted page ─────────────
  // Fires when `highlights` changes identity (i.e. after a new /ask response).
  // Navigates to the lowest page_num in the highlights set.
  // We skip navigation if highlights is empty (no match for this doc).
  useEffect(() => {
    if (!highlights || highlights.length === 0) return
    const pages = highlights.map((c) => c.page_num).filter(Boolean)
    if (pages.length === 0) return
    const firstPage = Math.min(...pages)
    setCurrentPage(firstPage)
  }, [highlights]) // eslint-disable-line react-hooks/exhaustive-deps
  // Note: intentionally NOT listing currentPage in deps — we only want this
  // to fire when the highlights set itself changes, not on every page turn.

  // ── Highlight feature: pre-compute per-page normalised chunk texts ─────────
  // Memoised so we don't recompute on every rendered text item.
  // Shape: Map<pageNum, string[]>  where each string is a normalised chunk text.
  // ── Highlight feature: pre-compute per-page phrase sets ───────────────────
  // Memoised so we don't recompute on every rendered text item.
  // Shape: Map<pageNum, Set<phrase>>
  //   Each Set contains every n-gram (bigram…6-gram) extracted from all
  //   retrieved chunk texts on that page, plus long single tokens.
  //   customTextRenderer does a Set.has(normSpan) lookup — O(1) per span.
  const pageChunkMap = useMemo(() => {
    const map = new Map()
    for (const chunk of highlights) {
      const page = chunk.page_num
      if (!chunk.text) continue
      const phrases = buildPhraseSet(chunk.text)
      if (!map.has(page)) {
        map.set(page, phrases)
      } else {
        // Merge phrase sets when multiple chunks share a page
        const existing = map.get(page)
        for (const p of phrases) existing.add(p)
      }
    }
    return map
  }, [highlights])

  // ── Highlight feature: set of page numbers that have highlights ────────────
  const highlightedPages = useMemo(
    () => new Set(highlights.map((c) => c.page_num).filter(Boolean)),
    [highlights],
  )

  // ── Highlight feature: count of highlight chunks on the current page ───────
  const currentPageMatchCount = useMemo(
    () => highlights.filter((c) => c.page_num === currentPage).length,
    [highlights, currentPage],
  )

  // ── Highlight feature: customTextRenderer ─────────────────────────────────
  // Called by react-pdf for every text item on the current page.
  // Returns an HTML string; react-pdf injects it via dangerouslySetInnerHTML.
  const customTextRenderer = useCallback(
    ({ str }) => {
      const pagePhrases = pageChunkMap.get(currentPage)   // now a Set<phrase>
      if (shouldHighlight(str, pagePhrases)) {
        return `<mark class="pdf-highlight">${escapeHtml(str)}</mark>`
      }
      return escapeHtml(str)
    },
    [pageChunkMap, currentPage],
  )

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
          {/* Highlight feature: header badge when highlights are present */}
          {highlights.length > 0 && (
            <span className="flex items-center gap-1 text-[10px] font-mono text-ember-400 bg-ember-400/10 border border-ember-400/20 rounded-full px-1.5 py-0.5 shrink-0">
              <Highlighter className="w-2.5 h-2.5" />
              {highlights.length}
            </span>
          )}
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
      <div className="flex flex-col border-b border-ink-800 bg-ink-900/60 shrink-0">
        <div className="flex items-center justify-between px-3 py-2 gap-2">

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

            <div className="flex items-center gap-1.5 min-w-[80px] justify-center">
              <span className="text-[11px] font-mono text-ink-400">
                {numPages
                  ? `${currentPage} / ${numPages}`
                  : isDocLoading
                    ? '…'
                    : '—'}
              </span>
              {/* Highlight feature: per-page match count */}
              {currentPageMatchCount > 0 && (
                <span className="text-[10px] font-mono text-ember-400 bg-ember-400/10 rounded px-1">
                  {currentPageMatchCount}↑
                </span>
              )}
            </div>

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

        {/* Highlight feature: highlighted page pills strip ─────────────────── */}
        {/* Shown only when there are highlights; clicking a pill jumps to that page */}
        {highlightedPages.size > 0 && (
          <div className="flex items-center gap-1.5 px-3 pb-2 flex-wrap">
            <span className="text-[10px] text-ink-600 font-mono shrink-0">match on:</span>
            {[...highlightedPages].sort((a, b) => a - b).map((pageNum) => (
              <button
                key={pageNum}
                onClick={() => setCurrentPage(pageNum)}
                className={`
                  text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors
                  ${currentPage === pageNum
                    ? 'bg-ember-500/20 border-ember-500/40 text-ember-400'
                    : 'bg-ink-800 border-ink-700 text-ink-400 hover:border-ink-600 hover:text-ink-200'
                  }
                `}
                title={`Jump to page ${pageNum}`}
              >
                p{pageNum}
              </button>
            ))}
          </div>
        )}
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
            loading={null}
            className="flex flex-col items-center"
          >
            {numPages && (
              <Page
                pageNumber={currentPage}
                scale={scale}
                renderTextLayer={true}         // ← Highlight feature: text layer ON
                renderAnnotationLayer={false}
                customTextRenderer={customTextRenderer}   // ← Highlight feature
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
