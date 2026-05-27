import React, { useCallback, useEffect, useMemo } from 'react'
import TopBar from './components/TopBar'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import PdfPreviewPanel from './components/PdfPreviewPanel'
import { useBackendStatus } from './hooks/useBackendStatus'
import { useDocuments } from './hooks/useDocuments'
import { useChat } from './hooks/useChat'

export default function App() {
  const backendStatus = useBackendStatus()
  const documents = useDocuments()
  const chat = useChat()

  const handleUploaded = (ingestResponse) => {
    documents.addDocument(ingestResponse)
    setTimeout(() => documents.refresh(), 1500)
  }

  const handleSend = (question) => {
    chat.send(question, documents.selectedDocId)
  }

  const selectedDoc = documents.selectedDocId
    ? documents.documents.find((d) => d.doc_id === documents.selectedDocId) ?? null
    : null

  const previewDoc = documents.previewDocId
    ? documents.documents.find((d) => d.doc_id === documents.previewDocId) ?? null
    : null

  const highlights = useMemo(() => {
    if (!previewDoc) return []

    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const msg = chat.messages[i]
      if (
        msg.role === 'assistant' &&
        Array.isArray(msg.retrievedChunks) &&
        msg.retrievedChunks.length > 0
      ) {
        return msg.retrievedChunks.filter(
          (chunk) => chunk.filename === previewDoc.filename,
        )
      }
    }

    return []
  }, [previewDoc, chat.messages])

  const retrievedSources = useMemo(() => {
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const msg = chat.messages[i]
      if (msg.role === 'assistant' && Array.isArray(msg.sources)) {
        return msg.sources
      }
    }

    return []
  }, [chat.messages])

  useEffect(() => {
    chat.saveCurrentConversation({
      selectedDocument: selectedDoc,
      previewDocument: previewDoc,
      retrievedSources,
      highlights,
    })
  }, [
    chat.messages,
    selectedDoc,
    previewDoc,
    retrievedSources,
    highlights,
    chat.saveCurrentConversation,
  ])

  const handleNewChat = useCallback(() => {
    chat.clearSession()
    documents.clearSelection()
    documents.closePreview()
  }, [chat, documents])

  const handleSelectChat = useCallback(
    async (sessionId) => {
      const conversation = await chat.selectConversation(sessionId)
      if (conversation) {
        documents.restoreConversationState(conversation)
      }
    },
    [chat, documents],
  )

  const handleDeleteChat = useCallback(
    async (sessionId) => {
      await chat.removeConversation(sessionId)
    },
    [chat],
  )

  return (
    <div className="h-screen flex flex-col bg-ink-950 text-ink-50 overflow-hidden">
      <TopBar
        backendStatus={backendStatus}
        sessionId={chat.sessionId}
        docCount={documents.total}
        onNewChat={handleNewChat}
        onRefreshStatus={backendStatus.refresh}
      />

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <Sidebar
          backendStatus={backendStatus}
          documents={documents}
          onUploaded={handleUploaded}
          chatHistory={{
            conversations: chat.conversations,
            activeSessionId: chat.sessionId,
            loading: chat.historyLoading,
            error: chat.historyError,
            onNewChat: handleNewChat,
            onSelectChat: handleSelectChat,
            onDeleteChat: handleDeleteChat,
          }}
        />

        <ChatArea
          messages={chat.messages}
          isLoading={chat.isLoading}
          onSend={handleSend}
          backendStatus={backendStatus}
          hasDocuments={documents.total > 0}
          selectedDoc={selectedDoc}
        />

        {previewDoc && (
          <PdfPreviewPanel
            doc={previewDoc}
            onClose={documents.closePreview}
            highlights={highlights}
          />
        )}
      </div>
    </div>
  )
}