/**
 * hooks/useChat.js
 * ----------------
 * Highlight feature change (additive only):
 *
 *   addMessage() for the assistant role now also stores:
 *     retrievedChunks: data.retrieved_chunks ?? []
 *
 *   This is the array of { chunk_id, text, page_num, filename, score }
 *   objects returned by the updated ask.py.  App.jsx reads this field
 *   from the most-recent assistant message to derive highlights for
 *   PdfPreviewPanel.
 *
 * Nothing else changes: session persistence, send(), clearSession(),
 * error handling, doc_id filter forwarding (Feature 1) are all untouched.
 */

import { useState, useCallback, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { askQuestion } from '../api/client'

const SESSION_KEY = 'docuintel_session_id'
const MESSAGES_KEY = 'docuintel_messages'

function loadSession() {
  try {
    return localStorage.getItem(SESSION_KEY) || uuidv4()
  } catch {
    return uuidv4()
  }
}

function saveSession(id) {
  try { localStorage.setItem(SESSION_KEY, id) } catch {}
}

function loadMessages() {
  try {
    const raw = localStorage.getItem(MESSAGES_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveMessages(msgs) {
  try {
    const trimmed = msgs.slice(-100)
    localStorage.setItem(MESSAGES_KEY, JSON.stringify(trimmed))
  } catch {}
}

export function useChat() {
  const [sessionId, setSessionId] = useState(() => {
    const id = loadSession()
    saveSession(id)
    return id
  })

  const [messages, setMessages] = useState(() => loadMessages())
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const addMessage = useCallback((msg) => {
    setMessages((prev) => {
      const next = [...prev, { id: uuidv4(), timestamp: new Date().toISOString(), ...msg }]
      saveMessages(next)
      return next
    })
  }, [])

  /**
   * Send a question to the backend.
   *
   * @param {string} question         The user's question text.
   * @param {string|null} selectedDocId  Feature 1: doc_id to filter by, or null for all docs.
   */
  const send = useCallback(
    async (question, selectedDocId = null) => {
      if (!question.trim() || isLoading) return

      setError(null)
      addMessage({ role: 'user', content: question })
      setIsLoading(true)

      try {
        const data = await askQuestion(question, sessionId, selectedDocId)

        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id)
          saveSession(data.session_id)
        }

        addMessage({
          role: 'assistant',
          content: data.answer,
          sources: data.sources ?? [],
          rewrittenQuery: data.rewritten_query,
          processingMs: data.processing_time_ms,
          chunksRetrieved: data.chunks_retrieved,
          docIdFilter: data.doc_id_filter,
          // ── Highlight feature ──────────────────────────────────────────────
          // Full chunk objects: [{ chunk_id, text, page_num, filename, score }]
          // App.jsx reads this from the last assistant message and filters by
          // the currently previewed document's filename.
          retrievedChunks: data.retrieved_chunks ?? [],
        })
      } catch (err) {
        const msg = err.userMessage || 'Something went wrong. Please try again.'
        setError(msg)
        addMessage({ role: 'error', content: msg })
      } finally {
        setIsLoading(false)
      }
    },
    [sessionId, isLoading, addMessage],
  )

  const clearSession = useCallback(() => {
    const newId = uuidv4()
    setSessionId(newId)
    saveSession(newId)
    setMessages([])
    saveMessages([])
    setError(null)
  }, [])

  return {
    sessionId,
    messages,
    isLoading,
    error,
    send,
    clearSession,
    hasMessages: messages.length > 0,
  }
}
