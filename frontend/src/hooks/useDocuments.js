/**
 * hooks/useDocuments.js
 * ---------------------
 * Feature 2 additions:
 *   previewDocId  — the doc_id whose PDF is currently open in the preview panel
 *   openPreview(id)  — opens the preview for a doc_id
 *   closePreview()   — closes the preview panel
 *
 * Feature 1 fields (selectedDocId, selectDoc, clearSelection) are unchanged.
 * All other existing fields are unchanged.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchDocuments } from '../api/client'

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
  }
}
