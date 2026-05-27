import React from 'react'
import UploadSection from './UploadSection'
import DocumentList from './DocumentList'
import ChatHistory from './ChatHistory'

export default function Sidebar({
  backendStatus,
  documents,
  onUploaded,
  chatHistory,
}) {
  return (
    <aside className="w-64 shrink-0 flex flex-col bg-ink-950 border-r border-ink-800 h-full overflow-hidden">
      <div className="px-4 py-3 border-b border-ink-800">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-ink-500">
          Workspace
        </h2>
      </div>

      <ChatHistory
        conversations={chatHistory.conversations}
        activeSessionId={chatHistory.activeSessionId}
        loading={chatHistory.loading}
        error={chatHistory.error}
        onNewChat={chatHistory.onNewChat}
        onSelectChat={chatHistory.onSelectChat}
        onDeleteChat={chatHistory.onDeleteChat}
      />

      <UploadSection
        onUploaded={onUploaded}
        backendOnline={backendStatus.isOnline}
      />

      <div className="mx-3 border-t border-ink-800 mb-3" />

      <DocumentList
        documents={documents.documents}
        loading={documents.loading}
        error={documents.error}
        onRefresh={documents.refresh}
        selectedDocId={documents.selectedDocId}
        onSelectDoc={documents.selectDoc}
        onClearSelection={documents.clearSelection}
        onOpenPreview={documents.openPreview}
        onDeleteDoc={documents.removeDocument}
      />
    </aside>
  )
}