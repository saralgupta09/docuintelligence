/**
 * components/MessageBubble.jsx
 * -----------------------------
 * Renders a single chat message.
 * User messages: right-aligned blue bubble.
 * AI messages: left-aligned with markdown rendering + sources.
 * Error messages: red warning bubble.
 */

import React, { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, AlertCircle, Info } from 'lucide-react'
import { formatTime } from '../utils/helpers'
import SourceCard from './SourceCard'

const MessageBubble = memo(function MessageBubble({ message }) {
  const { role, content, sources, rewrittenQuery, processingMs, timestamp } = message

  if (role === 'user') {
    return (
      <div className="flex justify-end gap-3 animate-fade-in">
        <div className="max-w-[75%] flex flex-col items-end gap-1">
          <div className="bg-ember-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 shadow-lg shadow-ember-900/20">
            <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{content}</p>
          </div>
          {timestamp && (
            <span className="text-[10px] text-ink-700 font-mono">{formatTime(timestamp)}</span>
          )}
        </div>
        {/* Avatar */}
        <div className="w-7 h-7 rounded-lg bg-ember-700 flex items-center justify-center shrink-0 mt-0.5 shadow-sm">
          <User className="w-3.5 h-3.5 text-white" />
        </div>
      </div>
    )
  }

  if (role === 'error') {
    return (
      <div className="flex items-start gap-3 animate-fade-in">
        <div className="w-7 h-7 rounded-lg bg-rose-500/20 border border-rose-500/30 flex items-center justify-center shrink-0 mt-0.5">
          <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
        </div>
        <div className="max-w-[80%] bg-rose-500/10 border border-rose-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
          <p className="text-sm text-rose-300 leading-relaxed">{content}</p>
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex items-start gap-3 animate-fade-in">
      {/* AI avatar */}
      <div className="w-7 h-7 rounded-lg bg-ink-800 border border-ink-700 flex items-center justify-center shrink-0 mt-0.5">
        <span className="text-[10px] font-display font-bold text-ember-400">AI</span>
      </div>

      <div className="flex-1 min-w-0 max-w-[82%]">
        {/* Answer bubble */}
        <div className="bg-ink-800 border border-ink-700 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
          <div className="prose-chat">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>

          {/* Sources */}
          <SourceCard sources={sources} />
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 mt-1.5 px-1">
          {timestamp && (
            <span className="text-[10px] text-ink-700 font-mono">{formatTime(timestamp)}</span>
          )}
          {processingMs != null && (
            <span className="text-[10px] text-ink-700 font-mono">
              {processingMs < 1000
                ? `${processingMs}ms`
                : `${(processingMs / 1000).toFixed(1)}s`}
            </span>
          )}
          {rewrittenQuery && rewrittenQuery !== message.content && (
            <RewrittenBadge query={rewrittenQuery} />
          )}
        </div>
      </div>
    </div>
  )
})

export default MessageBubble

function RewrittenBadge({ query }) {
  const [show, setShow] = React.useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setShow((v) => !v)}
        className="flex items-center gap-1 text-[10px] text-ink-600 hover:text-ink-400 transition-colors font-mono"
      >
        <Info className="w-3 h-3" />
        rewritten query
      </button>
      {show && (
        <div className="absolute bottom-full left-0 mb-1 z-10 bg-ink-800 border border-ink-700 rounded-lg p-2.5 shadow-xl max-w-xs animate-fade-in">
          <p className="text-[11px] text-ink-400 font-mono break-words">{query}</p>
        </div>
      )}
    </div>
  )
}
