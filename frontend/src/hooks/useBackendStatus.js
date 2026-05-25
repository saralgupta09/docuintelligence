/**
 * hooks/useBackendStatus.js
 * -------------------------
 * Polls GET /health every 30 seconds.
 * Returns current backend status, stats, and a manual refresh function.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchHealth } from '../api/client'

const POLL_INTERVAL_MS = 30_000

export function useBackendStatus() {
  const [status, setStatus] = useState('checking') // 'checking' | 'online' | 'offline'
  const [healthData, setHealthData] = useState(null)
  const [lastChecked, setLastChecked] = useState(null)
  const [error, setError] = useState(null)

  const check = useCallback(async () => {
    try {
      const data = await fetchHealth()
      setHealthData(data)
      setStatus('online')
      setError(null)
    } catch (err) {
      setStatus('offline')
      setHealthData(null)
      setError(err.userMessage || 'Backend unavailable')
    } finally {
      setLastChecked(new Date())
    }
  }, [])

  useEffect(() => {
    check()
    const interval = setInterval(check, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [check])

  return {
    status,          // 'checking' | 'online' | 'offline'
    healthData,      // Full health response object or null
    lastChecked,     // Date object or null
    error,           // Error message string or null
    refresh: check,  // Call to force a recheck
    // Convenience accessors:
    isOnline: status === 'online',
    version: healthData?.version ?? null,
    geminiConfigured: healthData?.gemini_key_configured ?? false,
    ocrStatus: healthData?.ocr?.status ?? 'unknown',
    ocrEnabled: healthData?.ocr?.enabled ?? false,
    activeSessions: healthData?.memory?.active_sessions ?? 0,
    totalChunks: healthData?.vector_db?.total_chunks ?? 0,
    appName: healthData?.app ?? 'DocuIntel',
  }
}
