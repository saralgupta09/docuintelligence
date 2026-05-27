/**
 * components/ChatInput.jsx
 * -------------------------
 * Feature 1 change: when selectedDoc is provided, the placeholder text
 * changes to mention the document name so the user knows context is active.
 *
 * All other logic — auto-resize, Enter/Shift+Enter, char counter,
 * disabled states — is completely unchanged.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Loader2 } from 'lucide-react'

const MAX_CHARS = 2000

export default function ChatInput({
  onSend,
  isLoading,
  backendOnline,
  disabled,
  selectedDoc,        // Feature 1: currently selected doc object (or null)
}) {
  const [text, setText] = useState('')
  const textareaRef = useRef(null)
  const isDisabled = isLoading || !backendOnline || disabled

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }, [text])

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || isDisabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, isDisabled, onSend])

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleChange = (e) => {
    if (e.target.value.length <= MAX_CHARS) {
      setText(e.target.value)
    }
  }

  const charCount = text.length
  const nearLimit = charCount > MAX_CHARS * 0.8

  // Feature 1: contextual placeholder text
  const placeholder = !backendOnline
    ? 'Backend offline — cannot send messages'
    : isLoading
      ? 'AI is responding…'
      : selectedDoc
        ? `Ask about ${selectedDoc.filename}…`
        : 'Ask a question about your documents…'

  return (
    <div className="border-t border-ink-800 bg-ink-950/80 backdrop-blur-sm p-4">
      <div
        className={`
          flex items-end gap-3 rounded-xl border bg-ink-900 transition-colors
          ${isDisabled
            ? 'border-ink-800 opacity-60'
            : 'border-ink-700 focus-within:border-ink-600 focus-within:bg-ink-850'
          }
          px-4 py-3
        `}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          rows={1}
          placeholder={placeholder}
          className="
            flex-1 bg-transparent resize-none outline-none text-sm text-ink-100
            placeholder:text-ink-600 leading-relaxed min-h-[24px]
            disabled:cursor-not-allowed
          "
          style={{ maxHeight: '200px' }}
          aria-label="Message input"
        />

        <div className="flex items-center gap-2 shrink-0 self-end">
          {nearLimit && (
            <span className={`text-[10px] font-mono ${charCount >= MAX_CHARS ? 'text-rose-400' : 'text-ink-500'}`}>
              {MAX_CHARS - charCount}
            </span>
          )}

          <button
            onClick={handleSend}
            disabled={isDisabled || !text.trim()}
            className={`
              w-8 h-8 rounded-lg flex items-center justify-center transition-all
              ${text.trim() && !isDisabled
                ? 'bg-ember-600 hover:bg-ember-500 text-white shadow-lg shadow-ember-900/30 hover:scale-105'
                : 'bg-ink-800 text-ink-600 cursor-not-allowed'
              }
            `}
            aria-label="Send message"
          >
            {isLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {!isDisabled && (
        <p className="text-[10px] text-ink-700 text-center mt-1.5">
          Enter to send · Shift+Enter for new line
        </p>
      )}
    </div>
  )
}
