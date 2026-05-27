/**
 * components/DocumentList.jsx
 * ----------------------------
 * Feature 1 changes:
 *   - Accepts selectedDocId, onSelectDoc, onClearSelection props
 *   - Clicking a DocCard calls onSelectDoc(doc.doc_id)
 *   - Selected card gets a highlighted border + background
 *   - A "×" clear button appears on the selected card to deselect
 *   - When a doc is selected, a small pill below the header shows its name
 *
 * All existing markup (icon, name, page count, chunk count, OCR badge,
 * timestamp, loading/error/empty states) is completely preserved.
 */

import React from 'react'
import { FileText, ScanLine, Loader2, RefreshCw, AlertCircle, X } from 'lucide-react'
import { relativeTime } from '../utils/helpers'

export default function DocumentList({
  documents,
  loading,
  error,
  onRefresh,
  selectedDocId,
  onSelectDoc,
  onClearSelection,
}) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden px-3 pb-3">
      {/* Section header */}
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-500 px-1">
          Documents
          {documents.length > 0 && (
            <span className="ml-1.5 text-ink-600 font-mono">{documents.length}</span>
          )}
        </p>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="w-6 h-6 rounded flex items-center justify-center text-ink-600 hover:text-ink-400 hover:bg-ink-800 transition-colors"
          title="Refresh document list"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Feature 1: active filter pill */}
      {selectedDocId && (
        <div className="flex items-center gap-1.5 mb-2 px-1">
          <span className="text-[10px] text-ember-400 bg-ember-400/10 border border-ember-400/20 rounded-full px-2 py-0.5 truncate max-w-[160px]">
            Searching selected
          </span>
          <button
            onClick={onClearSelection}
            title="Clear selection — search all documents"
            className="text-ink-600 hover:text-ink-400 transition-colors shrink-0"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* States */}
      {loading && documents.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-4 h-4 text-ink-600 animate-spin" />
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-rose-500/10 border border-rose-500/20 p-2.5 flex items-start gap-2">
          <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
          <p className="text-[11px] text-rose-400 leading-relaxed">{error}</p>
        </div>
      )}

      {!loading && !error && documents.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 py-8">
          <div className="w-10 h-10 rounded-xl bg-ink-900 border border-ink-800 flex items-center justify-center">
            <FileText className="w-5 h-5 text-ink-700" />
          </div>
          <p className="text-[11px] text-ink-600 text-center">
            No documents yet.<br />Upload a PDF to get started.
          </p>
        </div>
      )}

      {/* Document list */}
      {documents.length > 0 && (
        <div className="space-y-1.5 overflow-y-auto flex-1">
          {documents.map((doc) => (
            <DocCard
              key={doc.doc_id}
              doc={doc}
              isSelected={doc.doc_id === selectedDocId}
              onSelect={onSelectDoc}
              onDeselect={onClearSelection}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function DocCard({ doc, isSelected, onSelect, onDeselect }) {
  const name = doc.filename || 'Unknown file'
  const pages = doc.total_pages
  const chunks = doc.chunk_count
  const ocr = doc.ocr_applied

  const handleClick = () => {
    if (isSelected) {
      onDeselect()
    } else {
      onSelect(doc.doc_id)
    }
  }

  return (
    <div
      onClick={handleClick}
      title={isSelected ? 'Click to deselect (search all docs)' : 'Click to search only this document'}
      className={`
        group rounded-lg border p-2.5 transition-all cursor-pointer animate-fade-in
        ${isSelected
          ? 'bg-ember-500/10 border-ember-500/40 ring-1 ring-ember-500/20'
          : 'bg-ink-900 border-ink-800 hover:border-ink-700'
        }
      `}
    >
      <div className="flex items-start gap-2">
        {/* Icon */}
        <div className={`
          w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5
          ${isSelected ? 'bg-ember-500/20' : 'bg-ink-800'}
        `}>
          <FileText className={`w-3.5 h-3.5 ${isSelected ? 'text-ember-400' : 'text-ink-400'}`} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p
            className={`text-xs font-medium truncate leading-tight ${isSelected ? 'text-ember-300' : 'text-ink-200'}`}
            title={name}
          >
            {name}
          </p>

          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            {pages != null && (
              <span className="text-[10px] text-ink-500 font-mono">{pages}p</span>
            )}
            {chunks != null && (
              <span className="text-[10px] text-ink-600 font-mono">· {chunks} chunks</span>
            )}
            {ocr ? (
              <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-400 bg-amber-400/10 border border-amber-400/20 px-1.5 py-0.5 rounded-full font-medium">
                <ScanLine className="w-2.5 h-2.5" />
                OCR
              </span>
            ) : (
              <span className="text-[10px] text-ink-700 px-1.5 py-0.5 rounded-full border border-ink-800">
                text
              </span>
            )}
          </div>

          {doc.upload_timestamp && (
            <p className="text-[10px] text-ink-700 mt-0.5">
              {relativeTime(doc.upload_timestamp)}
            </p>
          )}
        </div>

        {/* Feature 1: deselect button — only visible on selected card */}
        {isSelected && (
          <button
            onClick={(e) => { e.stopPropagation(); onDeselect() }}
            title="Deselect — search all documents"
            className="shrink-0 text-ember-400/60 hover:text-ember-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Feature 1: selected label */}
      {isSelected && (
        <p className="text-[10px] text-ember-400/70 mt-1.5 pl-9">
          Searching this document only
        </p>
      )}
    </div>
  )
}
