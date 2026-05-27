/**
 * components/Sidebar.jsx
 * -----------------------
 * Feature 1 change: forwards selectDoc, clearSelection, and selectedDocId
 * from the documents hook down to DocumentList.
 * Nothing else changes.
 */

import React from 'react'
import UploadSection from './UploadSection'
import DocumentList from './DocumentList'

export default function Sidebar({ backendStatus, documents, onUploaded }) {
  return (
    <aside className="w-64 shrink-0 flex flex-col bg-ink-950 border-r border-ink-800 h-full overflow-hidden">
      {/* Sidebar header */}
      <div className="px-4 py-3 border-b border-ink-800">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-ink-500">
          Workspace
        </h2>
      </div>

      {/* Upload */}
      <UploadSection
        onUploaded={onUploaded}
        backendOnline={backendStatus.isOnline}
      />

      {/* Divider */}
      <div className="mx-3 border-t border-ink-800 mb-3" />

      {/* Document list */}
      <DocumentList
        documents={documents.documents}
        loading={documents.loading}
        error={documents.error}
        onRefresh={documents.refresh}
        selectedDocId={documents.selectedDocId}
        onSelectDoc={documents.selectDoc}
        onClearSelection={documents.clearSelection}
      />
    </aside>
  )
}
