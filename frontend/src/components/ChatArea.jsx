/**
 * components/ChatArea.jsx
 * ------------------------
 * Main chat interface:
 *  - Scrollable message list with auto-scroll to bottom
 *  - Empty state with suggestions
 *  - Loading indicator
 *  - ChatInput at the bottom
 */

import React, { useEffect, useRef, useCallback } from 'react'
import { MessageSquare, Cpu, FileSearch, Layers, ArrowDown } from 'lucide-react'
import MessageBubble from './MessageBubble'
import LoadingAnimation from './LoadingAnimation'
import ChatInput from './ChatInput'

const SUGGESTIONS = [
  { icon: FileSearch, text: 'Summarise the main findings of this document' },
  { icon: Layers, text: 'What are the key topics covered?' },
  { icon: MessageSquare, text: 'Explain the methodology section' },
  { icon: Cpu, text: 'List all technical terms and their definitions' },
]

export default function ChatArea({
  messages,
  isLoading,
  onSend,
  backendStatus,
  hasDocuments,
}) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  const [showScrollButton, setShowScrollButton] = React.useState(false)

  // Auto-scroll when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Show scroll-to-bottom button when user has scrolled up
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollButton(distFromBottom > 200)
  }, [])

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden relative">
      {/* Messages */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-6 py-6 space-y-5"
      >
        {isEmpty ? (
          <EmptyState
            backendOnline={backendStatus.isOnline}
            hasDocuments={hasDocuments}
            onSuggestion={onSend}
          />
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isLoading && <LoadingAnimation />}
            <div ref={bottomRef} className="h-1" />
          </>
        )}
      </div>

      {/* Scroll-to-bottom button */}
      {showScrollButton && !isEmpty && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-24 right-6 z-10 w-8 h-8 rounded-full bg-ink-800 border border-ink-700 flex items-center justify-center text-ink-400 hover:text-ink-200 hover:bg-ink-700 shadow-lg transition-all animate-fade-in"
          aria-label="Scroll to bottom"
        >
          <ArrowDown className="w-3.5 h-3.5" />
        </button>
      )}

      {/* Input */}
      <ChatInput
        onSend={onSend}
        isLoading={isLoading}
        backendOnline={backendStatus.isOnline}
        disabled={!hasDocuments && messages.length === 0}
      />
    </div>
  )
}

function EmptyState({ backendOnline, hasDocuments, onSuggestion }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-full gap-8 py-12">
      {/* Logo mark */}
      <div className="flex flex-col items-center gap-4">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-ember-400/20 to-ember-600/20 border border-ember-500/20 flex items-center justify-center">
          <Cpu className="w-8 h-8 text-ember-400" />
        </div>
        <div className="text-center">
          <h2 className="font-display font-bold text-xl text-white">DocuIntel</h2>
          <p className="text-ink-500 text-sm mt-1">
            {!backendOnline
              ? 'Backend is offline — start the server first'
              : !hasDocuments
                ? 'Upload a PDF on the left to start chatting'
                : 'Ask anything about your documents'}
          </p>
        </div>
      </div>

      {/* Suggestions — only show when ready */}
      {backendOnline && hasDocuments && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
          {SUGGESTIONS.map((s, i) => (
            <SuggestionCard
              key={i}
              icon={s.icon}
              text={s.text}
              onClick={() => onSuggestion(s.text)}
            />
          ))}
        </div>
      )}

      {/* Backend offline warning */}
      {!backendOnline && (
        <div className="bg-rose-500/10 border border-rose-500/20 rounded-xl px-5 py-4 max-w-sm text-center">
          <p className="text-rose-300 text-sm font-medium mb-1">Backend Not Running</p>
          <p className="text-rose-400/70 text-xs font-mono">
            uvicorn main:app --reload --port 8000
          </p>
        </div>
      )}
    </div>
  )
}

function SuggestionCard({ icon: Icon, text, onClick }) {
  return (
    <button
      onClick={() => onClick(text)}
      className="
        group flex items-start gap-3 text-left rounded-xl border border-ink-800
        bg-ink-900/50 hover:bg-ink-800 hover:border-ink-700 p-3.5
        transition-all text-sm text-ink-400 hover:text-ink-200
      "
    >
      <Icon className="w-4 h-4 text-ink-600 group-hover:text-ember-400 shrink-0 mt-0.5 transition-colors" />
      <span className="leading-snug">{text}</span>
    </button>
  )
}
