import React, { useState } from 'react'
import { Loader2, MessageSquare, Plus, Trash2 } from 'lucide-react'
import { relativeTime, shortSession } from '../utils/helpers'

export default function ChatHistory({
  conversations,
  activeSessionId,
  loading,
  error,
  onNewChat,
  onSelectChat,
  onDeleteChat,
}) {
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)

  const handleDelete = async (event, sessionId) => {
    event.stopPropagation()
    setDeletingId(sessionId)

    try {
      await onDeleteChat(sessionId)
      setConfirmDeleteId(null)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="px-3 pb-3 border-b border-ink-800">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-500 px-1">
          Chat History
          {conversations.length > 0 && (
            <span className="ml-1.5 text-ink-600 font-mono">
              {conversations.length}
            </span>
          )}
        </p>

        <button
          onClick={onNewChat}
          title="Start new chat"
          className="w-6 h-6 rounded flex items-center justify-center text-ink-600 hover:text-ink-300 hover:bg-ink-800 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
      </div>

      {loading && conversations.length === 0 && (
        <div className="h-14 flex items-center justify-center">
          <Loader2 className="w-4 h-4 text-ink-600 animate-spin" />
        </div>
      )}

      {error && (
        <div className="rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-2 mb-2">
          <p className="text-[11px] text-rose-400 leading-relaxed">{error}</p>
        </div>
      )}

      {!loading && !error && conversations.length === 0 && (
        <div className="rounded-lg border border-ink-800 bg-ink-900 px-3 py-3">
          <p className="text-[11px] text-ink-600 text-center">
            No saved chats yet.
          </p>
        </div>
      )}

      {conversations.length > 0 && (
        <div className="space-y-1.5 max-h-56 overflow-y-auto">
          {conversations.map((chat) => {
            const isActive = chat.session_id === activeSessionId
            const isConfirming = confirmDeleteId === chat.session_id
            const isDeleting = deletingId === chat.session_id
            const title = chat.title || 'New chat'
            const documentName =
              chat.selected_document_name ||
              chat.selected_document?.filename ||
              'All documents'

            return (
              <button
                key={chat.session_id}
                type="button"
                onClick={() => {
                  if (!isConfirming && !isDeleting) {
                    onSelectChat(chat.session_id)
                  }
                }}
                className={`
                  group w-full text-left rounded-lg border p-2.5 transition-all
                  ${isDeleting ? 'opacity-50 pointer-events-none' : ''}
                  ${
                    isActive
                      ? 'bg-ember-500/10 border-ember-500/40 ring-1 ring-ember-500/20'
                      : isConfirming
                        ? 'bg-rose-500/5 border-rose-500/30'
                        : 'bg-ink-900 border-ink-800 hover:border-ink-700'
                  }
                `}
                title={title}
              >
                <div className="flex items-start gap-2">
                  <div
                    className={`
                      w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5
                      ${isActive ? 'bg-ember-500/20' : 'bg-ink-800'}
                    `}
                  >
                    {isDeleting ? (
                      <Loader2 className="w-3.5 h-3.5 text-ink-400 animate-spin" />
                    ) : (
                      <MessageSquare
                        className={`w-3.5 h-3.5 ${
                          isActive ? 'text-ember-400' : 'text-ink-400'
                        }`}
                      />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <p
                      className={`text-xs font-medium truncate leading-tight ${
                        isActive ? 'text-ember-300' : 'text-ink-200'
                      }`}
                    >
                      {title}
                    </p>

                    <p className="text-[10px] text-ink-600 truncate mt-1">
                      {documentName}
                    </p>

                    <div className="flex items-center gap-1.5 mt-0.5">
                      {chat.updated_at && (
                        <span className="text-[10px] text-ink-700">
                          {relativeTime(chat.updated_at)}
                        </span>
                      )}

                      <span className="text-[10px] text-ink-700 font-mono">
                        {shortSession(chat.session_id)}
                      </span>
                    </div>
                  </div>

                  {!isConfirming && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        setConfirmDeleteId(chat.session_id)
                      }}
                      title="Delete chat"
                      className="opacity-0 group-hover:opacity-100 text-ink-600 hover:text-rose-400 transition-all shrink-0"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {isConfirming && (
                  <div
                    className="mt-2 rounded-md bg-rose-500/10 border border-rose-500/20 px-2.5 py-2 flex items-center justify-between gap-2"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <span className="text-[11px] text-rose-300">
                      Delete chat?
                    </span>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          setConfirmDeleteId(null)
                        }}
                        className="text-[11px] text-ink-400 hover:text-ink-200 transition-colors px-1.5 py-0.5 rounded hover:bg-ink-800"
                      >
                        Cancel
                      </button>

                      <button
                        type="button"
                        onClick={(event) => handleDelete(event, chat.session_id)}
                        className="text-[11px] font-medium text-white bg-rose-600 hover:bg-rose-500 transition-colors px-2 py-0.5 rounded"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}