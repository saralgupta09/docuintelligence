/**
 * App.jsx
 * --------
 * Root component.  Composes the full layout:
 *   TopBar (full width)
 *   └── Sidebar (left) + ChatArea (right)
 *
 * Wires hooks:
 *   useBackendStatus → TopBar + Sidebar + ChatArea
 *   useDocuments     → Sidebar + TopBar doc count
 *   useChat          → ChatArea + TopBar session
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
    // Full refresh after a short delay to get server-side data
    setTimeout(() => documents.refresh(), 1500)
  }

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
          onSend={chat.send}
          backendStatus={backendStatus}
          hasDocuments={documents.total > 0}
        />
      </div>
    </div>
  )
}
