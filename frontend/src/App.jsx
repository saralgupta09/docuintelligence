/**
 * App.jsx
 * --------
 * Feature 2 changes:
 *   - Imports PdfPreviewPanel
 *   - Reads previewDocId, closePreview from useDocuments()
 *   - Renders PdfPreviewPanel between Sidebar and ChatArea when a doc is previewed
 *   - The panel is conditionally mounted so it unmounts fully when closed,
 *     which resets react-pdf state cleanly
 *
 * Feature 1 wiring (selectedDocId, handleSend, selectedDoc) is unchanged.
 */

import React from 'react'
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

  // Feature 1: wrap send() to inject the currently selected doc_id
  const handleSend = (question) => {
    chat.send(question, documents.selectedDocId)
  }

  // Feature 1: full doc object for the "Searching: X" label in ChatArea
  const selectedDoc = documents.selectedDocId
    ? documents.documents.find((d) => d.doc_id === documents.selectedDocId) ?? null
    : null

  // Feature 2: full doc object for the preview panel
  const previewDoc = documents.previewDocId
    ? documents.documents.find((d) => d.doc_id === documents.previewDocId) ?? null
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

        {/* Feature 2: PDF preview panel — only mounted when a doc is previewed */}
        {previewDoc && (
          <PdfPreviewPanel
            doc={previewDoc}
            onClose={documents.closePreview}
          />
        )}
      </div>
    </div>
  )
}
