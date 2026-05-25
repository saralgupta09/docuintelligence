/**
 * components/LoadingAnimation.jsx
 * --------------------------------
 * Three-dot bounce animation shown while AI is generating.
 */

import React from 'react'

export default function LoadingAnimation() {
  return (
    <div className="flex items-center gap-3 py-2 animate-fade-in">
      {/* Avatar */}
      <div className="w-7 h-7 rounded-lg bg-ink-800 border border-ink-700 flex items-center justify-center shrink-0">
        <span className="text-xs font-display font-bold text-ember-400">AI</span>
      </div>

      {/* Bubble with bouncing dots */}
      <div className="bg-ink-800 border border-ink-700 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
        <span
          className="w-1.5 h-1.5 rounded-full bg-ink-400 inline-block animate-dot1"
          aria-hidden="true"
        />
        <span
          className="w-1.5 h-1.5 rounded-full bg-ink-400 inline-block animate-dot2"
          aria-hidden="true"
        />
        <span
          className="w-1.5 h-1.5 rounded-full bg-ink-400 inline-block animate-dot3"
          aria-hidden="true"
        />
        <span className="sr-only">AI is thinking…</span>
      </div>
    </div>
  )
}
