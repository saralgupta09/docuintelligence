/**
 * hooks/useDocuments.js
 * ---------------------
 * Fetches and manages the list of ingested documents.
 * Exposes a refresh() so the upload section can trigger a reload.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchDocuments } from '../api/client'

export function useDocuments() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchDocuments()
      setDocuments(data.documents ?? [])
    } catch (err) {
      // If the endpoint isn't available yet (404), fall back to empty list silently
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
      // Avoid duplicates by doc_id
      const exists = prev.some((d) => d.doc_id === newDoc.doc_id)
      if (exists) return prev
      return [newDoc, ...prev]
    })
  }, [])

  return {
    documents,
    loading,
    error,
    refresh: load,
    addDocument,
    total: documents.length,
  }
}
