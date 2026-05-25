/**
 * hooks/useChat.js
 * ----------------
 * Manages the full chat lifecycle:
 *  - Persists session_id in localStorage across page refreshes
 *  - Maintains messages array (user + assistant + sources)
 *  - Calls POST /api/v1/ask and handles streaming state
 *  - Exposes clearSession() to start a fresh conversation
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
    // Keep last 100 messages to avoid localStorage bloat
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

  const send = useCallback(
    async (question) => {
      if (!question.trim() || isLoading) return

      setError(null)
      addMessage({ role: 'user', content: question })
      setIsLoading(true)

      try {
        const data = await askQuestion(question, sessionId)

        // Backend may return a new session_id on first message
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
        })
      } catch (err) {
        const msg = err.userMessage || 'Something went wrong. Please try again.'
        setError(msg)
        addMessage({
          role: 'error',
          content: msg,
        })
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
