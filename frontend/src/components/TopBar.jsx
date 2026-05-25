/**
 * components/TopBar.jsx
 * ----------------------
 * Top navigation bar showing:
 *  - App branding
 *  - Backend online/offline status badge
 *  - Active session ID
 *  - Total ingested documents count
 *  - New chat button
 */

import React from 'react'
import {
  Cpu,
  RefreshCw,
  Trash2,
  Wifi,
  WifiOff,
  Loader2,
  FileText,
  Hash,
} from 'lucide-react'
import { shortSession } from '../utils/helpers'

export default function TopBar({ backendStatus, sessionId, docCount, onNewChat, onRefreshStatus }) {
  const { status, version, geminiConfigured, ocrEnabled, ocrStatus } = backendStatus

  return (
    <header className="h-14 flex items-center justify-between px-5 border-b border-ink-800 bg-ink-950/90 backdrop-blur-sm shrink-0 z-20">
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-ember-400 to-ember-600 flex items-center justify-center shadow-lg shadow-ember-500/20">
          <Cpu className="w-4 h-4 text-white" />
        </div>
        <span className="font-display font-bold text-base text-white tracking-tight">
          DocuIntel
        </span>
        {version && (
          <span className="text-[10px] font-mono text-ink-500 bg-ink-900 px-1.5 py-0.5 rounded border border-ink-800">
            v{version}
          </span>
        )}
      </div>

      {/* Centre stats */}
      <div className="hidden md:flex items-center gap-4">
        {/* Backend status */}
        <StatusPill status={status} geminiConfigured={geminiConfigured} onRefresh={onRefreshStatus} />

        {/* OCR badge */}
        {ocrEnabled && (
          <span
            className={`text-[11px] font-mono px-2 py-0.5 rounded-full border ${
              ocrStatus === 'ok'
                ? 'text-jade-400 border-jade-500/30 bg-jade-500/10'
                : 'text-ink-400 border-ink-700 bg-ink-900'
            }`}
          >
            OCR {ocrStatus === 'ok' ? 'ready' : ocrStatus}
          </span>
        )}

        {/* Doc count */}
        <div className="flex items-center gap-1.5 text-ink-400 text-xs">
          <FileText className="w-3.5 h-3.5" />
          <span>{docCount} doc{docCount !== 1 ? 's' : ''}</span>
        </div>

        {/* Session */}
        <div className="flex items-center gap-1.5 text-ink-500 text-xs font-mono">
          <Hash className="w-3 h-3" />
          <span title={sessionId}>{shortSession(sessionId)}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onRefreshStatus}
          title="Refresh backend status"
          className="w-8 h-8 rounded-lg flex items-center justify-center text-ink-500 hover:text-ink-300 hover:bg-ink-800 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onNewChat}
          title="Start new conversation"
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-ink-800 hover:bg-ink-700 text-ink-300 hover:text-white transition-colors border border-ink-700 hover:border-ink-600"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">New Chat</span>
        </button>
      </div>
    </header>
  )
}

function StatusPill({ status, geminiConfigured, onRefresh }) {
  if (status === 'checking') {
    return (
      <div className="flex items-center gap-1.5 text-ink-400 text-xs">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span>Connecting…</span>
      </div>
    )
  }

  if (status === 'offline') {
    return (
      <button
        onClick={onRefresh}
        className="flex items-center gap-1.5 text-rose-400 text-xs hover:text-rose-300 transition-colors"
      >
        <WifiOff className="w-3.5 h-3.5" />
        <span>Backend offline</span>
      </button>
    )
  }

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <div className="relative">
        <div className="w-2 h-2 rounded-full bg-jade-400" />
        <div className="absolute inset-0 w-2 h-2 rounded-full bg-jade-400 animate-ping opacity-60" />
      </div>
      <span className="text-jade-400">Online</span>
      {!geminiConfigured && (
        <span className="text-ember-400 ml-1" title="Gemini API key not configured">
          · No Gemini key
        </span>
      )}
    </div>
  )
}
