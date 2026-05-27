/**
 * hooks/useDocuments.js
 * ---------------------
 * Fetches and manages the list of ingested documents.
 *
 * Feature 1 additions:
 *   selectedDocId  — the doc_id of the currently selected document, or null
 *   selectDoc(id)  — sets selectedDocId (call with the doc_id string)
 *   clearSelection() — resets to null (search all documents)
 *
 * All existing fields (documents, loading, error, refresh, addDocument, total)
 * are completely unchanged.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchDocuments } from '../api/client'

export function useDocuments() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Feature 1: selected document state
  const [selectedDocId, setSelectedDocId] = useState(null)

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

  // Optimistically add a newly uploaded document before the next fetch
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

  // Feature 1: select a document by its doc_id
  const selectDoc = useCallback((docId) => {
    setSelectedDocId(docId)
  }, [])

  // Feature 1: clear selection → search all documents
  const clearSelection = useCallback(() => {
    setSelectedDocId(null)
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
  }
}
