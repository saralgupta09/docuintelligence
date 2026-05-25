# DocuIntel Frontend — Phase 5

Complete React + Vite + TailwindCSS frontend for the DocuIntel RAG backend.

---

## Quick reference

| Thing            | Value                          |
|------------------|-------------------------------|
| Frontend port    | http://localhost:5173          |
| Backend port     | http://localhost:8000          |
| API proxy target | http://localhost:8000 (Vite)   |

---

## Part 1 — Backend Analysis

### APIs that work directly (zero changes needed):

| Endpoint | Method | Used for |
|---|---|---|
| `GET /health` | GET | TopBar status badge, OCR status |
| `POST /api/v1/ingest/` | POST multipart | PDF upload + ingestion |
| `POST /api/v1/ask/` | POST JSON | Chat questions |

### What was missing and why:

1. **No `GET /documents` endpoint** — frontend needs a document list for the sidebar
2. **CORS only allowed port 8501** (Streamlit) — Vite runs on 5173
3. **No `score` field in sources** — combined_score exists in `retrieved_docs` state but wasn't exposed in the ask response

---

## Part 2 — Minimal Backend Modifications

Exactly 3 files changed. No existing logic touched.

### File 1 — `backend/main.py`

Add Vite origins to CORS + register the new documents router.

**Diff summary:**
```python
# BEFORE
allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],

# AFTER
allow_origins=[
    "http://localhost:5173",    # ← added (Vite)
    "http://127.0.0.1:5173",   # ← added (Vite)
    "http://localhost:8501",
    "http://127.0.0.1:8501",
],

# Also add at the top:
from api.routes.documents import router as documents_router
app.include_router(documents_router, prefix="/api/v1")
```

Full replacement file: `backend_modifications/main.py`

---

### File 2 — `backend/api/routes/documents.py` (NEW FILE)

`GET /api/v1/documents/` — aggregates ChromaDB chunk metadata by `doc_id`.
Uses the existing `VectorStoreService.get_all_documents()` method.

Copy `backend_modifications/api/routes/documents.py` → `backend/api/routes/documents.py`

---

### File 3 — `backend/api/routes/ask.py`

Add `score: Optional[float] = None` to `SourceReference` Pydantic model.
Populate it from `retrieved_docs` combined_score by matching `chunk_id`.

Full replacement file: `backend_modifications/api/routes/ask.py`

---

## Part 3 — Frontend Folder Structure

```
frontend/
├── package.json              # Dependencies (React, Vite, Tailwind, Axios, react-markdown)
├── vite.config.js            # Dev server + proxy to localhost:8000
├── tailwind.config.js        # Custom design tokens (ink palette, ember accent)
├── postcss.config.js
├── index.html                # DM Sans + Syne + JetBrains Mono fonts
└── src/
    ├── main.jsx              # ReactDOM entry point
    ├── App.jsx               # Root layout — wires all hooks + components
    ├── index.css             # Tailwind directives + prose-chat utility class
    │
    ├── api/
    │   └── client.js         # Axios instance + all API functions + error normalisation
    │
    ├── components/
    │   ├── TopBar.jsx        # Backend status · session ID · doc count · new chat
    │   ├── Sidebar.jsx       # Left sidebar wrapper
    │   ├── UploadSection.jsx # Drag-drop PDF upload + progress + result banner
    │   ├── DocumentList.jsx  # Ingested documents with OCR badge
    │   ├── ChatArea.jsx      # Message list + empty state + suggestions
    │   ├── MessageBubble.jsx # User / AI / error message bubbles with Markdown
    │   ├── SourceCard.jsx    # Collapsible source references with confidence
    │   ├── ChatInput.jsx     # Auto-resize textarea, Enter to send
    │   └── LoadingAnimation.jsx  # Three-dot bounce
    │
    ├── hooks/
    │   ├── useBackendStatus.js   # Polls /health every 30s
    │   ├── useDocuments.js       # Fetches /documents, optimistic add
    │   └── useChat.js            # Session + message state + send()
    │
    └── utils/
        └── helpers.js            # shortSession, formatTime, formatScore, etc.
```

---

## Part 5 — Installation Commands

### Step 1 — Apply backend modifications

```bash
# From your project root (where backend/ lives):
cp frontend/backend_modifications/main.py backend/main.py
cp frontend/backend_modifications/api/routes/ask.py backend/api/routes/ask.py
cp frontend/backend_modifications/api/routes/documents.py backend/api/routes/documents.py
```

### Step 2 — Install frontend dependencies

```bash
cd frontend
npm install
```

That's it. All dependencies are standard npm packages.

---

## Part 6 — Running Frontend Locally

### Terminal 1 — start the backend (unchanged command):

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### Terminal 2 — start the frontend:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser.

> The Vite dev server proxies `/api` and `/health` to `http://localhost:8000`
> so you never have to think about CORS during development.

---

## Part 7 — How Frontend Communicates With Backend

```
Browser (localhost:5173)
        │
        │  All requests go to same origin (5173)
        ▼
Vite Dev Server (proxy)
        │
        │  /api/**  and  /health  →  http://localhost:8000
        ▼
FastAPI Backend (localhost:8000)
        │
        ├── GET  /health              → backend status
        ├── GET  /api/v1/documents/   → document list
        ├── POST /api/v1/ingest/      → PDF upload
        └── POST /api/v1/ask/         → chat question
```

### Data flows

**Health check (every 30s)**
```
useBackendStatus → fetchHealth() → GET /health
→ status badge, OCR badge, doc counts
```

**PDF Upload**
```
UploadSection drag/click
→ uploadPDF(file, onProgress) via FormData
→ POST /api/v1/ingest/  (multipart)
→ IngestResponse { status, filename, total_pages, ocr_applied, chunks_stored }
→ optimistically added to document list
→ useDocuments.refresh() after 1.5s for server-side data
```

**Document list**
```
useDocuments → fetchDocuments() → GET /api/v1/documents/
→ { documents: [{ doc_id, filename, total_pages, chunk_count, ocr_applied }] }
→ Shown in sidebar with OCR badge
```

**Chat**
```
ChatInput (Enter key or button click)
→ useChat.send(question)
→ askQuestion(question, sessionId) → POST /api/v1/ask/
  body: { question, session_id }
→ AskResponse {
    answer,
    sources: [{ filename, page, chunk_id, excerpt, score }],
    session_id,
    rewritten_query,
    processing_time_ms
  }
→ MessageBubble renders Markdown answer
→ SourceCard renders collapsed source pills (click to expand excerpts)
→ session_id saved to localStorage for persistence across refreshes
```

### Error handling matrix

| Error | User-visible message |
|---|---|
| Backend unavailable (network) | "Cannot reach the backend. Is it running on port 8000?" |
| 503 + GEMINI_API_KEY | "Gemini API key is not configured…" |
| 503 other | "Service unavailable: …" |
| 429 quota | "Gemini quota exhausted. Free tier ~1,500/day. Try tomorrow." |
| 422 validation | "Validation error: …" |
| 400 bad file | "Only PDF files are accepted." |
| Upload: non-PDF | Caught client-side before sending |
| Empty answer | AI bubble still rendered with empty content |
| OCR failure | Reported in IngestResponse warning banner |
