/**
 * App.jsx
 * --------
 * Highlight feature change (additive only):
 *
 *   Derives a `highlights` array from the most-recent assistant message's
 *   `retrievedChunks`, filtered to only the chunks that belong to the
 *   currently previewed document (matched by filename).
 *
 *   Passes `highlights` as a new prop to PdfPreviewPanel.
 *
 * All other wiring — Feature 1 (selectedDocId / handleSend), Feature 2
 * (previewDocId / openPreview / closePreview), upload handling, Sidebar,
 * ChatArea, TopBar — is completely unchanged.
 */

import React, { useMemo } from 'react'
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

  // ── Highlight feature ────────────────────────────────────────────────────
  // Find the most-recent assistant message that has retrieved chunks.
  // Filter those chunks to only the ones from the currently previewed doc
  // (matched by filename — the timestamped filename stored in ChromaDB metadata
  //  is the same string used in both chunk.filename and previewDoc.filename).
  //
  // Result shape: Array<{ chunk_id, text, page_num, filename, score }>
  // PdfPreviewPanel uses this to drive customTextRenderer highlighting.
  const highlights = useMemo(() => {
    if (!previewDoc) return []

    // Walk backwards through messages to find the last assistant message
    // that actually has retrieved chunks (not every message will have them
    // if the answer was an error or the collection was empty).
    for (let i = chat.messages.length - 1; i >= 0; i--) {
      const msg = chat.messages[i]
      if (msg.role === 'assistant' && Array.isArray(msg.retrievedChunks) && msg.retrievedChunks.length > 0) {
        // Filter to chunks from the previewed document
        return msg.retrievedChunks.filter(
          (chunk) => chunk.filename === previewDoc.filename
        )
      }
    }
    return []
  }, [previewDoc, chat.messages])

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
            highlights={highlights}
          />
        )}
      </div>
    </div>
  )
}
