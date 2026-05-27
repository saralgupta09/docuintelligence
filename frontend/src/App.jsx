/**
 * App.jsx
 * --------
 * Root component.
 *
 * Feature 1 changes:
 *   - Destructures selectedDocId, selectDoc, clearSelection from useDocuments()
 *   - Wraps chat.send() so it automatically includes selectedDocId
 *   - Passes selectDoc / selectedDocId down to Sidebar → DocumentList
 *   - Passes selectedDoc object down to ChatArea for the "Searching: X" label
 *
 * All other wiring (TopBar, backendStatus, upload flow) is unchanged.
 */

import React from 'react'
import TopBar from './components/TopBar'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import { useBackendStatus } from './hooks/useBackendStatus'
import { useDocuments } from './hooks/useDocuments'
import { useChat } from './hooks/useChat'

export default function App() {
  const backendStatus = useBackendStatus()
  const documents = useDocuments()
  const chat = useChat()

  // When a new document is uploaded: add it optimistically + refresh list
  const handleUploaded = (ingestResponse) => {
    documents.addDocument(ingestResponse)
    setTimeout(() => documents.refresh(), 1500)
  }

  // Feature 1: wrap send() to inject the currently selected doc_id
  const handleSend = (question) => {
    chat.send(question, documents.selectedDocId)
  }

  // Feature 1: find the full doc object for the selected doc (for the label)
  const selectedDoc = documents.selectedDocId
    ? documents.documents.find((d) => d.doc_id === documents.selectedDocId) ?? null
    : null

  return (
    <div className="h-screen flex flex-col bg-ink-950 text-ink-50 overflow-hidden">
      {/* Top bar */}
      <TopBar
        backendStatus={backendStatus}
        sessionId={chat.sessionId}
        docCount={documents.total}
        onNewChat={chat.clearSession}
        onRefreshStatus={backendStatus.refresh}
      />

      {/* Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left sidebar */}
        <Sidebar
          backendStatus={backendStatus}
          documents={documents}
          onUploaded={handleUploaded}
        />

        {/* Main chat */}
        <ChatArea
          messages={chat.messages}
          isLoading={chat.isLoading}
          onSend={handleSend}
          backendStatus={backendStatus}
          hasDocuments={documents.total > 0}
          selectedDoc={selectedDoc}
        />
      </div>
    </div>
  )
}
