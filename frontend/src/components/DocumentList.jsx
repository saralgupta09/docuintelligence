/**
 * components/DocumentList.jsx
 * ----------------------------
 * Deletion feature additions (all other behavior is unchanged):
 *
 *  - Accepts new `onDeleteDoc` prop (async fn from useDocuments.removeDocument).
 *  - Tracks `confirmDeleteId` — which card is showing its "Delete?" prompt.
 *  - Tracks `deletingId`      — which card is mid-deletion (shows spinner).
 *  - Tracks `deleteError`     — { docId, message } for inline error display.
 *
 * Per-card behavior:
 *  - Trash icon visible on group-hover (opacity-0 → opacity-100).
 *    Clicking it sets confirmDeleteId and stops click propagation
 *    (so it does NOT trigger document selection or preview).
 *  - Confirmation row appears below the card content when confirmDeleteId matches.
 *    "Delete" → calls handleDelete; "Cancel" → clears confirmDeleteId.
 *  - During deletion the card is dimmed and a spinner replaces the trash icon.
 *  - On API error a small rose-coloured message appears under the card.
 *
 * Feature 1 (selection / filter pill) and Feature 2 (onOpenPreview) are
 * completely unchanged.
 */

import React, { useState } from 'react'
import {
  FileText, ScanLine, Loader2, RefreshCw,
  AlertCircle, X, Trash2,
} from 'lucide-react'
import { relativeTime } from '../utils/helpers'

export default function DocumentList({
  documents,
  loading,
  error,
  onRefresh,
  selectedDocId,
  onSelectDoc,
  onClearSelection,
  onOpenPreview,
  onDeleteDoc,       // deletion feature
}) {
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [deleteError, setDeleteError] = useState(null) // { docId, message }

  const handleDelete = async (docId) => {
    setDeletingId(docId)
    setConfirmDeleteId(null)
    setDeleteError(null)
    try {
      await onDeleteDoc(docId)
      // On success: useDocuments removes the doc from state automatically.
      // Nothing else needed here.
    } catch (err) {
      setDeleteError({
        docId,
        message: err.userMessage || 'Delete failed. Please try again.',
      })
    } finally {
      setDeletingId(null)
    }
  }

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
              isConfirming={confirmDeleteId === doc.doc_id}
              isDeleting={deletingId === doc.doc_id}
              deleteError={deleteError?.docId === doc.doc_id ? deleteError.message : null}
              onSelect={onSelectDoc}
              onDeselect={onClearSelection}
              onOpenPreview={onOpenPreview}
              onRequestDelete={() => {
                setDeleteError(null)
                setConfirmDeleteId(doc.doc_id)
              }}
              onConfirmDelete={() => handleDelete(doc.doc_id)}
              onCancelDelete={() => setConfirmDeleteId(null)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function DocCard({
  doc,
  isSelected,
  isConfirming,
  isDeleting,
  deleteError,
  onSelect,
  onDeselect,
  onOpenPreview,
  onRequestDelete,
  onConfirmDelete,
  onCancelDelete,
}) {
  const name = doc.filename || 'Unknown file'
  const pages = doc.total_pages
  const chunks = doc.chunk_count
  const ocr = doc.ocr_applied

  const handleClick = () => {
    // Don't trigger selection when confirming or deleting
    if (isConfirming || isDeleting) return
    if (isSelected) {
      onDeselect()
    } else {
      onSelect(doc.doc_id)
      onOpenPreview?.(doc.doc_id)
    }
  }

  return (
    <div
      className={`
        group rounded-lg border transition-all animate-fade-in
        ${isDeleting ? 'opacity-40 pointer-events-none' : 'cursor-pointer'}
        ${isSelected
          ? 'bg-ember-500/10 border-ember-500/40 ring-1 ring-ember-500/20'
          : isConfirming
            ? 'bg-rose-500/5 border-rose-500/30'
            : 'bg-ink-900 border-ink-800 hover:border-ink-700'
        }
      `}
    >
      {/* Main card row — click to select/deselect */}
      <div
        onClick={handleClick}
        title={
          isConfirming
            ? undefined
            : isSelected
              ? 'Click to deselect and close preview'
              : 'Click to select and preview this document'
        }
        className="p-2.5"
      >
        <div className="flex items-start gap-2">
          {/* Icon */}
          <div className={`
            w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5
            ${isSelected ? 'bg-ember-500/20' : 'bg-ink-800'}
          `}>
            {isDeleting
              ? <Loader2 className="w-3.5 h-3.5 text-ink-400 animate-spin" />
              : <FileText className={`w-3.5 h-3.5 ${isSelected ? 'text-ember-400' : 'text-ink-400'}`} />
            }
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

          {/* Right-side action buttons */}
          <div className="flex items-center gap-1 shrink-0 mt-0.5">
            {/* Trash icon — visible on hover, hidden while confirming/deleting */}
            {!isConfirming && !isDeleting && (
              <button
                onClick={(e) => { e.stopPropagation(); onRequestDelete() }}
                title="Delete document"
                className="opacity-0 group-hover:opacity-100 text-ink-600 hover:text-rose-400 transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Deselect X — only on selected card */}
            {isSelected && !isConfirming && (
              <button
                onClick={(e) => { e.stopPropagation(); onDeselect() }}
                title="Deselect — search all documents"
                className="text-ember-400/60 hover:text-ember-300 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Selected label */}
        {isSelected && !isConfirming && (
          <p className="text-[10px] text-ember-400/70 mt-1.5 pl-9">
            Searching this document only
          </p>
        )}
      </div>

      {/* Inline delete confirmation — shown below card row */}
      {isConfirming && (
        <div
          className="px-2.5 pb-2.5"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-2 flex items-center justify-between gap-2">
            <span className="text-[11px] text-rose-300 leading-tight">
              Delete <span className="font-medium truncate max-w-[100px] inline-block align-bottom" title={name}>{name}</span>?
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={onCancelDelete}
                className="text-[11px] text-ink-400 hover:text-ink-200 transition-colors px-1.5 py-0.5 rounded hover:bg-ink-800"
              >
                Cancel
              </button>
              <button
                onClick={onConfirmDelete}
                className="text-[11px] font-medium text-white bg-rose-600 hover:bg-rose-500 transition-colors px-2 py-0.5 rounded"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Inline error — shown after a failed deletion */}
      {deleteError && (
        <div className="px-2.5 pb-2.5" onClick={(e) => e.stopPropagation()}>
          <div className="rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-1.5 flex items-center gap-1.5">
            <AlertCircle className="w-3 h-3 text-rose-400 shrink-0" />
            <p className="text-[10px] text-rose-400 leading-relaxed">{deleteError}</p>
          </div>
        </div>
      )}
    </div>
  )
}