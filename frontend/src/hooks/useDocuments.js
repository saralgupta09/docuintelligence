import { useState, useEffect, useCallback } from 'react'
import { fetchDocuments, deleteDocument } from '../api/client'

export function useDocuments() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [selectedDocId, setSelectedDocId] = useState(null)
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

  const removeDocument = useCallback(async (docId) => {
    await deleteDocument(docId)

    setDocuments((prev) => prev.filter((d) => d.doc_id !== docId))
    setSelectedDocId((prev) => (prev === docId ? null : prev))
    setPreviewDocId((prev) => (prev === docId ? null : prev))
  }, [])

  const selectDoc = useCallback((docId) => {
    setSelectedDocId(docId)
  }, [])

  const clearSelection = useCallback(() => {
    setSelectedDocId(null)
  }, [])

  const openPreview = useCallback((docId) => {
    setPreviewDocId(docId)
  }, [])

  const closePreview = useCallback(() => {
    setPreviewDocId(null)
  }, [])

  const restoreConversationState = useCallback((conversation) => {
    const selectedDocId =
      conversation?.selected_document?.doc_id ||
      conversation?.selectedDocument?.doc_id ||
      null

    const previewDocId =
      conversation?.preview_document?.doc_id ||
      conversation?.previewDocument?.doc_id ||
      selectedDocId ||
      null

    setSelectedDocId(selectedDocId)
    setPreviewDocId(previewDocId)
  }, [])

  return {
    documents,
    loading,
    error,
    refresh: load,
    addDocument,
    total: documents.length,

    selectedDocId,
    selectDoc,
    clearSelection,

    previewDocId,
    openPreview,
    closePreview,
    restoreConversationState,

    removeDocument,
  }
}