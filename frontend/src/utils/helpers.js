/**
 * utils/helpers.js
 * ----------------
 * Shared utility functions.
 */

/**
 * Truncate a session UUID for display: show first 8 chars + "…"
 */
export function shortSession(sessionId) {
  if (!sessionId) return '—'
  return sessionId.slice(0, 8) + '…'
}

/**
 * Format an ISO timestamp to a friendly local time string.
 */
export function formatTime(isoString) {
  if (!isoString) return ''
  try {
    const d = new Date(isoString)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

/**
 * Format bytes to human-readable size (KB, MB).
 */
export function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Format a confidence score (0–1) as a percentage string.
 */
export function formatScore(score) {
  if (score == null) return null
  return `${(score * 100).toFixed(0)}%`
}

/**
 * Format an ISO timestamp to a relative label ("2 hours ago", "just now").
 */
export function relativeTime(isoString) {
  if (!isoString) return ''
  try {
    const now = Date.now()
    const then = new Date(isoString).getTime()
    const diffSec = Math.floor((now - then) / 1000)

    if (diffSec < 60) return 'just now'
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
    return `${Math.floor(diffSec / 86400)}d ago`
  } catch {
    return ''
  }
}

/**
 * Clamp a number between min and max.
 */
export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

/**
 * Return unique sources by filename+page from a sources array.
 */
export function deduplicateSources(sources) {
  const seen = new Set()
  return (sources ?? []).filter((s) => {
    const key = `${s.filename}:${s.page}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}
