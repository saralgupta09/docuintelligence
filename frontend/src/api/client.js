/**
 * api/client.js
 * -------------
 * Central Axios instance and all backend API call functions.
 *
 * Feature 2 addition: getDocumentFileUrl(docId)
 *   Returns the URL string for streaming a document's PDF file.
 *   Used as the `file` prop for react-pdf's <Document> component.
 *   Not an async call — just builds the URL string.
 *   The actual HTTP request is made by react-pdf when it renders.
 *
 * All existing functions are unchanged.
 */

import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 120_000,
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
}

// ── Document list ────────────────────────────────────────────────────────────
export async function fetchDocuments() {
  const { data } = await api.get('/api/v1/documents/')
  return data
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
}

// ── Ask a question ──────────────────────────────────────────────────────────
export async function askQuestion(question, sessionId, docId = null) {
  const body = {
    question,
    session_id: sessionId || undefined,
  }
  if (docId) {
    body.doc_id = docId
  }
  const { data } = await api.post('/api/v1/ask/', body)
  return data
}

// ── Feature 2: PDF file URL ──────────────────────────────────────────────────
/**
 * Returns the URL to stream a document's PDF file from the backend.
 * Pass this string directly as the `file` prop to react-pdf's <Document>.
 *
 * @param {string} docId  The doc_id of the document.
 * @returns {string}      Absolute URL like "http://localhost:8000/api/v1/documents/my_pdf/file"
 */
export function getDocumentFileUrl(docId) {
  // Use absolute URL so react-pdf (which runs in a Web Worker context) can
  // resolve it correctly regardless of the current page path.
  return `http://localhost:8000/api/v1/documents/${encodeURIComponent(docId)}/file`
}

export default api
