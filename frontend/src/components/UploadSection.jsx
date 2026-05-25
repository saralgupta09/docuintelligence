/**
 * components/UploadSection.jsx
 * -----------------------------
 * PDF upload with:
 *  - Drag-and-drop zone
 *  - Click-to-browse
 *  - Upload progress bar
 *  - Success / error / warning feedback
 *  - Triggers onUploaded(ingestResponse) on success
 */

import React, { useState, useRef, useCallback } from 'react'
import { UploadCloud, CheckCircle2, AlertTriangle, XCircle, FileText, Loader2 } from 'lucide-react'
import { uploadPDF } from '../api/client'
import { formatSize } from '../utils/helpers'

export default function UploadSection({ onUploaded, backendOnline }) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState(null) // { type: 'success'|'warning'|'error', message, data }
  const [selectedFile, setSelectedFile] = useState(null)
  const inputRef = useRef(null)

  const processFile = useCallback(
    async (file) => {
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        setResult({ type: 'error', message: 'Only PDF files are accepted.' })
        return
      }

      setSelectedFile(file)
      setUploading(true)
      setProgress(0)
      setResult(null)

      try {
        const data = await uploadPDF(file, setProgress)

        if (data.status === 'success') {
          setResult({
            type: 'success',
            message: data.message,
            data,
          })
          onUploaded?.(data)
        } else if (data.status === 'warning') {
          setResult({ type: 'warning', message: data.message, data })
        } else {
          setResult({ type: 'error', message: data.message || 'Upload failed.' })
        }
      } catch (err) {
        setResult({ type: 'error', message: err.userMessage || 'Upload failed.' })
      } finally {
        setUploading(false)
        setProgress(0)
        // Reset input so the same file can be re-uploaded
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [onUploaded],
  )

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files?.[0]
      processFile(file)
    },
    [processFile],
  )

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = () => setIsDragging(false)
  const handleInputChange = (e) => processFile(e.target.files?.[0])
  const handleClick = () => {
    if (!uploading && backendOnline) inputRef.current?.click()
  }

  return (
    <div className="px-3 pt-1 pb-3">
      <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-500 mb-2 px-1">
        Upload PDF
      </p>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
        className={`
          relative rounded-xl border-2 border-dashed p-4 flex flex-col items-center justify-center gap-2
          transition-all duration-200 min-h-[110px]
          ${!backendOnline
            ? 'opacity-40 cursor-not-allowed border-ink-800'
            : uploading
              ? 'cursor-wait border-ember-500/50 bg-ember-500/5'
              : isDragging
                ? 'border-ember-400 bg-ember-400/10 scale-[0.99] cursor-copy'
                : 'border-ink-700 hover:border-ink-600 hover:bg-ink-800/40 cursor-pointer bg-ink-900/30'
          }
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={handleInputChange}
          disabled={uploading || !backendOnline}
        />

        {uploading ? (
          <UploadingState file={selectedFile} progress={progress} />
        ) : (
          <IdleState isDragging={isDragging} backendOnline={backendOnline} />
        )}
      </div>

      {/* Result feedback */}
      {result && !uploading && (
        <ResultBanner result={result} onDismiss={() => setResult(null)} />
      )}

      {!backendOnline && (
        <p className="text-[11px] text-ink-600 text-center mt-1.5">
          Backend offline — upload unavailable
        </p>
      )}
    </div>
  )
}

function IdleState({ isDragging, backendOnline }) {
  return (
    <>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${isDragging ? 'bg-ember-500/20 text-ember-400' : 'bg-ink-800 text-ink-400'}`}>
        <UploadCloud className="w-5 h-5" />
      </div>
      <div className="text-center">
        <p className={`text-xs font-medium ${isDragging ? 'text-ember-400' : 'text-ink-300'}`}>
          {isDragging ? 'Drop to upload' : 'Drag & drop PDF'}
        </p>
        <p className="text-[11px] text-ink-600 mt-0.5">or click to browse</p>
      </div>
    </>
  )
}

function UploadingState({ file, progress }) {
  return (
    <div className="w-full space-y-2.5 px-1">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-md bg-ink-800 flex items-center justify-center shrink-0">
          <FileText className="w-4 h-4 text-ink-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-ink-300 truncate font-medium">{file?.name || 'Uploading…'}</p>
          <p className="text-[11px] text-ink-500">{formatSize(file?.size)}</p>
        </div>
        <Loader2 className="w-4 h-4 text-ember-400 animate-spin shrink-0" />
      </div>

      {/* Progress bar */}
      <div className="w-full bg-ink-800 rounded-full h-1.5 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-ember-500 to-ember-400 rounded-full transition-all duration-200"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-[11px] text-ink-500 text-center">
        {progress < 100 ? `Uploading… ${progress}%` : 'Processing (OCR + embeddings)…'}
      </p>
    </div>
  )
}

function ResultBanner({ result, onDismiss }) {
  const styles = {
    success: {
      bg: 'bg-jade-500/10 border-jade-500/30',
      text: 'text-jade-400',
      icon: <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />,
    },
    warning: {
      bg: 'bg-ember-500/10 border-ember-500/30',
      text: 'text-ember-400',
      icon: <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />,
    },
    error: {
      bg: 'bg-rose-500/10 border-rose-500/30',
      text: 'text-rose-400',
      icon: <XCircle className="w-4 h-4 shrink-0 mt-0.5" />,
    },
  }

  const s = styles[result.type] || styles.error

  return (
    <div className={`mt-2 rounded-lg border p-2.5 flex items-start gap-2 animate-fade-in ${s.bg} ${s.text}`}>
      {s.icon}
      <p className="text-[11px] leading-relaxed flex-1">{result.message}</p>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100 transition-opacity shrink-0 mt-0.5">
        <XCircle className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
