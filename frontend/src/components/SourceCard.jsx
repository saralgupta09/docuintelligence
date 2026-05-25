/**
 * components/SourceCard.jsx
 * --------------------------
 * Displays retrieved source references below an AI answer.
 * Shows: filename, page number, optional confidence score, and excerpt.
 */

import React, { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, FileText } from 'lucide-react'
import { formatScore } from '../utils/helpers'

export default function SourceCard({ sources }) {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-3 border-t border-ink-700/60 pt-3">
      {/* Header toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-[11px] text-ink-500 hover:text-ink-300 transition-colors font-medium w-full text-left"
      >
        <BookOpen className="w-3.5 h-3.5" />
        <span>
          {sources.length} source{sources.length !== 1 ? 's' : ''} retrieved
        </span>
        {expanded ? (
          <ChevronUp className="w-3 h-3 ml-auto" />
        ) : (
          <ChevronDown className="w-3 h-3 ml-auto" />
        )}
      </button>

      {/* Source pills (always visible) */}
      <div className="flex flex-wrap gap-1.5 mt-2">
        {sources.map((src, i) => (
          <SourcePill key={i} source={src} />
        ))}
      </div>

      {/* Expanded excerpts */}
      {expanded && (
        <div className="mt-3 space-y-2 animate-fade-in">
          {sources.map((src, i) => (
            <ExcerptCard key={i} source={src} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function SourcePill({ source }) {
  const score = source.score ?? null
  const hasScore = score != null

  return (
    <div className="inline-flex items-center gap-1 bg-ink-900 border border-ink-700 rounded-full px-2 py-0.5 text-[11px] font-mono">
      <FileText className="w-2.5 h-2.5 text-ink-500 shrink-0" />
      <span className="text-ink-400 truncate max-w-[100px]" title={source.filename}>
        {source.filename}
      </span>
      <span className="text-ink-600">·</span>
      <span className="text-ember-400">p{source.page}</span>
      {hasScore && (
        <>
          <span className="text-ink-600">·</span>
          <span className="text-jade-400">{formatScore(score)}</span>
        </>
      )}
    </div>
  )
}

function ExcerptCard({ source, index }) {
  const score = source.score ?? null

  return (
    <div className="rounded-lg bg-ink-900/60 border border-ink-800 p-3 text-xs space-y-1.5">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-mono text-ink-600 shrink-0">#{index}</span>
          <span className="font-medium text-ink-300 truncate" title={source.filename}>
            {source.filename}
          </span>
          <span className="text-ink-600 shrink-0">Page {source.page}</span>
        </div>
        {score != null && (
          <span className="text-[10px] font-mono text-jade-400 bg-jade-500/10 px-1.5 py-0.5 rounded shrink-0">
            {formatScore(score)}
          </span>
        )}
      </div>

      {/* Excerpt */}
      {source.excerpt && (
        <p className="text-ink-500 leading-relaxed line-clamp-3 font-mono text-[11px]">
          "{source.excerpt}"
        </p>
      )}
    </div>
  )
}
