/**
 * api/client.js
 * -------------
 * Central Axios instance and all backend API call functions.
 * All requests go to the Vite proxy → http://localhost:8000.
 */

import axios from 'axios'

// Axios instance — base URL is relative so Vite proxy handles CORS
const api = axios.create({
  baseURL: '',
  timeout: 120_000, // 2 min (LLM generation can be slow)
  headers: { 'Content-Type': 'application/json' },
})

// ── Response interceptor — normalise error messages ────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK') {
      error.userMessage = 'Cannot reach the backend. Is it running on port 8000?'
    } else if (error.response) {
      const detail = error.response.data?.detail
      const status = error.response.status
      if (status === 503) {
        error.userMessage =
          detail?.includes('GEMINI_API_KEY')
            ? 'Gemini API key is not configured. Add GEMINI_API_KEY to your backend .env file.'
            : `Service unavailable: ${detail || 'Backend is down.'}`
      } else if (status === 429) {
        error.userMessage =
          'Gemini quota exhausted. Free tier allows ~1,500 requests/day. Try again tomorrow or upgrade.'
      } else if (status === 422) {
        error.userMessage = `Validation error: ${detail || 'Invalid input.'}`
      } else if (status === 400) {
        error.userMessage = detail || 'Bad request. Only PDF files are accepted.'
      } else {
        error.userMessage = detail || `Server error (${status}).`
      }
    } else {
      error.userMessage = 'Network error — backend may be unavailable.'
    }
    return Promise.reject(error)
  },
)

// ── Health check ────────────────────────────────────────────────────────────
export async function fetchHealth() {
  const { data } = await api.get('/health')
  return data
  // Returns: { status, app, version, phase, gemini_key_configured,
  //            vector_db: { total_chunks }, memory: { active_sessions },
  //            ocr: { status, enabled }, hybrid_weights, ... }
}

// ── Document list ────────────────────────────────────────────────────────────
export async function fetchDocuments() {
  const { data } = await api.get('/api/v1/documents/')
  return data
  // Returns: { documents: [{ doc_id, filename, total_pages, chunk_count,
  //                          ocr_applied, upload_timestamp }] }
}

// ── PDF upload (multipart/form-data) ────────────────────────────────────────
export async function uploadPDF(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await api.post('/api/v1/ingest/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) {
        onProgress(Math.round((evt.loaded / evt.total) * 100))
      }
    },
  })
  return data
  // Returns IngestResponse: { status, message, filename, doc_id,
  //   total_pages, chunks_stored, ocr_applied, ocr_pages_count, ... }
}

// ── Ask a question ──────────────────────────────────────────────────────────
export async function askQuestion(question, sessionId) {
  const { data } = await api.post('/api/v1/ask/', {
    question,
    session_id: sessionId || undefined,
  })
  return data
  // Returns AskResponse: { question, answer, sources, chunks_retrieved,
  //   processing_time_ms, rewritten_query, session_id }
}

export default api
