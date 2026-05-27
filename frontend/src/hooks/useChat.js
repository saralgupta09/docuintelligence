/**
 * hooks/useChat.js
 * ----------------
 * Manages the full chat lifecycle.
 *
 * Feature 1 change: send() now accepts an optional second argument selectedDocId.
 * When provided it is forwarded to askQuestion() so the backend scopes
 * retrieval to that document. When null/undefined, all documents are searched.
 *
 * Everything else — session persistence, message array, localStorage, error
 * handling, clearSession — is completely unchanged.
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
   * @param {string} question       The user's question text.
   * @param {string|null} selectedDocId  Feature 1: doc_id to filter by, or null for all docs.
   */
  const send = useCallback(
    async (question, selectedDocId = null) => {
      if (!question.trim() || isLoading) return

      setError(null)
      addMessage({ role: 'user', content: question })
      setIsLoading(true)

      try {
        // Feature 1: pass selectedDocId (null is fine — API treats it as "all docs")
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
          // Feature 1: store which doc was filtered (for display in messages if desired)
          docIdFilter: data.doc_id_filter,
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
