/**
 * hooks/useDocuments.js
 * ---------------------
 * Deletion feature addition: removeDocument(docId)
 *
 *   Calls the DELETE endpoint, then updates local state in a single pass:
 *   - Filters the document out of the documents array.
 *   - Clears selectedDocId if it matched the deleted doc.
 *   - Clears previewDocId if it matched the deleted doc.
 *
 *   Uses functional setState so none of the current state values need to
 *   appear in the useCallback dependency array, avoiding stale-closure bugs.
 *
 *   Throws on API failure so the caller (DocumentList) can display the error.
 *
 * All Feature 1 (selectedDocId / selectDoc / clearSelection) and
 * Feature 2 (previewDocId / openPreview / closePreview) fields are unchanged.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchDocuments, deleteDocument } from '../api/client'

export function useDocuments() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Feature 1: selected document state (for chat filtering)
  const [selectedDocId, setSelectedDocId] = useState(null)

  // Feature 2: preview document state (for PDF preview panel)
  const [previewDocId, setPreviewDocId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDocuments()
      setDocuments(data.documents ?? [])
    } catch (err) {
      if (err.response?.status === 404) {
        setDocuments([])
      } else {
        setError(err.userMessage || 'Failed to load documents.')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const addDocument = useCallback((ingestResponse) => {
    const newDoc = {
      doc_id: ingestResponse.doc_id,
      filename: ingestResponse.filename,
      total_pages: ingestResponse.total_pages,
      chunk_count: ingestResponse.chunks_stored,
      ocr_applied: ingestResponse.ocr_applied,
      ocr_pages_count: ingestResponse.ocr_pages_count,
      upload_timestamp: ingestResponse.upload_timestamp,
    }
    setDocuments((prev) => {
      const exists = prev.some((d) => d.doc_id === newDoc.doc_id)
      if (exists) return prev
      return [newDoc, ...prev]
    })
  }, [])

  // Deletion feature:
  // Uses functional updaters so this callback never goes stale — it does not
  // close over selectedDocId or previewDocId directly.
  const removeDocument = useCallback(async (docId) => {
    // API call first — if it throws, state is left untouched.
    await deleteDocument(docId)

    // Remove the doc from the list.
    setDocuments((prev) => prev.filter((d) => d.doc_id !== docId))

    // Clear selection if the deleted doc was selected.
    setSelectedDocId((prev) => (prev === docId ? null : prev))

    // Close preview panel if the deleted doc was being previewed.
    setPreviewDocId((prev) => (prev === docId ? null : prev))
  }, []) // empty deps — all updates use functional form

  // Feature 1
  const selectDoc = useCallback((docId) => {
    setSelectedDocId(docId)
  }, [])

  const clearSelection = useCallback(() => {
    setSelectedDocId(null)
  }, [])

  // Feature 2
  const openPreview = useCallback((docId) => {
    setPreviewDocId(docId)
  }, [])

  const closePreview = useCallback(() => {
    setPreviewDocId(null)
  }, [])

  return {
    documents,
    loading,
    error,
    refresh: load,
    addDocument,
    total: documents.length,
    // Feature 1
    selectedDocId,
    selectDoc,
    clearSelection,
    // Feature 2
    previewDocId,
    openPreview,
    closePreview,
    // Deletion feature
    removeDocument,
  }
}