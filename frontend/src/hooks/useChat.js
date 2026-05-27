import { useState, useCallback, useEffect, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import {
  askQuestion,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  saveConversation,
} from '../api/client'

const SESSION_KEY = 'docuintel_session_id'
const MESSAGES_KEY = 'docuintel_messages'
const CONVERSATIONS_KEY = 'docuintel_conversations'

function safeJsonParse(raw, fallback) {
  try {
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

function loadSession() {
  try {
    return localStorage.getItem(SESSION_KEY) || uuidv4()
  } catch {
    return uuidv4()
  }
}

function saveSession(id) {
  try {
    localStorage.setItem(SESSION_KEY, id)
  } catch {}
}

function loadMessages() {
  try {
    return safeJsonParse(localStorage.getItem(MESSAGES_KEY), [])
  } catch {
    return []
  }
}

function saveMessages(msgs) {
  try {
    localStorage.setItem(MESSAGES_KEY, JSON.stringify(msgs.slice(-100)))
  } catch {}
}

function loadConversationSummaries() {
  try {
    return safeJsonParse(localStorage.getItem(CONVERSATIONS_KEY), [])
  } catch {
    return []
  }
}

function saveConversationSummaries(conversations) {
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations))
  } catch {}
}

function getTitleFromMessages(messages) {
  const firstUserMessage = messages.find((msg) => msg.role === 'user' && msg.content)
  if (!firstUserMessage) return 'New chat'

  const title = firstUserMessage.content.trim()
  return title.length > 48 ? `${title.slice(0, 48)}...` : title
}

function buildSummary(conversation) {
  const selectedDocument = conversation.selected_document || conversation.selectedDocument || null

  return {
    session_id: conversation.session_id,
    title: conversation.title || getTitleFromMessages(conversation.messages || []),
    created_at: conversation.created_at || conversation.createdAt || new Date().toISOString(),
    updated_at: conversation.updated_at || conversation.updatedAt || new Date().toISOString(),
    message_count: conversation.message_count || conversation.messages?.length || 0,
    selected_document: selectedDocument,
    selected_document_name: selectedDocument?.filename || null,
  }
}

function mergeSummary(prev, summary) {
  const next = [summary, ...prev.filter((item) => item.session_id !== summary.session_id)]
  next.sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
  return next
}

export function useChat() {
  const [sessionId, setSessionId] = useState(() => {
    const id = loadSession()
    saveSession(id)
    return id
  })

  const [messages, setMessages] = useState(() => loadMessages())
  const [conversations, setConversations] = useState(() => loadConversationSummaries())
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const snapshotRef = useRef(null)

  const updateConversationList = useCallback((summary) => {
    setConversations((prev) => {
      const next = mergeSummary(prev, summary)
      saveConversationSummaries(next)
      return next
    })
  }, [])

  const refreshConversations = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError(null)

    try {
      const data = await fetchConversations()
      const next = data.conversations ?? []
      setConversations(next)
      saveConversationSummaries(next)
    } catch (err) {
      setHistoryError(err.userMessage || 'Failed to load chat history.')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  const persistSnapshot = useCallback(
    async (snapshot = snapshotRef.current) => {
      if (!snapshot?.session_id) return

      const summary = buildSummary(snapshot)
      updateConversationList(summary)

      try {
        await saveConversation(snapshot.session_id, snapshot)
      } catch {
        // Local persistence still keeps the UI usable if backend is briefly offline.
      }
    },
    [updateConversationList],
  )

  const saveCurrentConversation = useCallback(
    (extra = {}) => {
      const snapshot = {
        session_id: sessionId,
        title: getTitleFromMessages(messages),
        messages,
        selected_document: extra.selectedDocument ?? null,
        preview_document: extra.previewDocument ?? null,
        retrieved_sources: extra.retrievedSources ?? [],
        highlights: extra.highlights ?? [],
      }

      snapshotRef.current = snapshot

      if (messages.length > 0) {
        persistSnapshot(snapshot)
      }
    },
    [sessionId, messages, persistSnapshot],
  )

  const addMessage = useCallback((msg) => {
    const nextMessage = {
      id: uuidv4(),
      timestamp: new Date().toISOString(),
      ...msg,
    }

    setMessages((prev) => {
      const next = [...prev, nextMessage]
      saveMessages(next)
      return next
    })

    return nextMessage
  }, [])

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
    snapshotRef.current = null
  }, [])

  const selectConversation = useCallback(
    async (targetSessionId) => {
      setHistoryError(null)

      try {
        const conversation = await fetchConversation(targetSessionId)

        setSessionId(conversation.session_id)
        saveSession(conversation.session_id)

        setMessages(conversation.messages ?? [])
        saveMessages(conversation.messages ?? [])

        updateConversationList(buildSummary(conversation))
        snapshotRef.current = conversation

        return conversation
      } catch (err) {
        setHistoryError(err.userMessage || 'Failed to restore chat.')
        return null
      }
    },
    [updateConversationList],
  )

  const removeConversation = useCallback(
    async (targetSessionId) => {
      await deleteConversation(targetSessionId)

      setConversations((prev) => {
        const next = prev.filter((item) => item.session_id !== targetSessionId)
        saveConversationSummaries(next)
        return next
      })

      if (targetSessionId === sessionId) {
        clearSession()
      }
    },
    [sessionId, clearSession],
  )

  return {
    sessionId,
    messages,
    conversations,
    historyLoading,
    historyError,
    isLoading,
    error,

    send,
    clearSession,
    selectConversation,
    removeConversation,
    refreshConversations,
    saveCurrentConversation,

    hasMessages: messages.length > 0,
  }
}