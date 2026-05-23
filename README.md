# DocuIntel — Multimodal AI Document Intelligence System

> **Phase 1:** PDF Ingestion Core  
> Upload PDFs → Extract Text → Chunk → Embed → Store in ChromaDB

---

## Project Overview

DocuIntel is a production-style multimodal AI document intelligence system built with:
- **LangGraph** workflow orchestration
- **BGE embeddings** (free, local, high quality)
- **ChromaDB** persistent vector storage
- **FastAPI** backend + **Streamlit** frontend (Phase 5)

This README covers **Phase 1 only** — the ingestion foundation everything else builds on.

---

## Phase 1 Architecture

```
PDF Upload (POST /api/v1/ingest/)
       │
       ▼
[pdf_processor.py]     PyMuPDF → text per page + page numbers
       │
       ▼
[chunker.py]           RecursiveCharacterTextSplitter → overlapping chunks + metadata
       │
       ▼
[embedding_service.py] BAAI/bge-small-en-v1.5 → 384-dim vectors (local, free)
       │
       ▼
[vector_store.py]      ChromaDB (persistent) → stores text + vectors + metadata
       │
       ▼
[IngestResponse]       Returns: chunks stored, page stats, timing
```

---

## Project Structure

```
docuintel/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings (pydantic BaseSettings + .env)
│   ├── api/
│   │   └── routes/
│   │       └── ingest.py        # POST /api/v1/ingest/
│   ├── ingestion/
│   │   ├── pdf_processor.py     # PyMuPDF text extraction
│   │   └── chunker.py           # Text splitting + metadata
│   ├── services/
│   │   ├── embedding_service.py # BGE-small embeddings
│   │   └── vector_store.py      # ChromaDB wrapper
│   └── utils/
│       └── logger.py            # JSON structured logging
├── data/
│   ├── uploads/                 # Uploaded PDFs (auto-created)
│   └── chroma_db/               # ChromaDB persistence (auto-created)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Installation

### Prerequisites
- Python 3.10 or higher
- ~1.5 GB free disk space (for PyTorch + BGE model download)

### Step 1: Clone and enter the project
```bash
git clone <your-repo>
cd docuintel
```

### Step 2: Create a virtual environment
```bash
python -m venv venv

# Activate:
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### Step 3: Install dependencies
```bash
pip install -r requirements.txt
```
> ⏱ First install takes 5–10 minutes (PyTorch ~800MB, sentence-transformers ~200MB)

### Step 4: Set up environment
```bash
cp .env.example .env
# Edit .env if needed (defaults work fine for Phase 1)
```

### Step 5: Run the server
```bash
cd backend
uvicorn main:app --reload --port 8000
```

You should see:
```
{"timestamp": "...", "level": "INFO", "message": "Starting DocuIntel backend", ...}
{"timestamp": "...", "level": "INFO", "message": "DocuIntel Phase 1 ready — waiting for requests"}
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## Testing Phase 1

### Test 1: Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "app": "DocuIntel",
  "version": "0.1.0",
  "phase": "1 - Ingestion Core",
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "vector_db": {
    "status": "ok",
    "collection_name": "documents",
    "total_chunks": 0
  }
}
```

---

### Test 2: Ingest a PDF

**Using curl:**
```bash
curl -X POST http://localhost:8000/api/v1/ingest/ \
  -F "file=@/path/to/your/document.pdf"
```

**Using Python:**
```python
import requests

with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/ingest/",
        files={"file": ("document.pdf", f, "application/pdf")}
    )

print(response.json())
```

**Expected response:**
```json
{
  "status": "success",
  "message": "Successfully ingested 'document.pdf' — 47 chunks stored.",
  "filename": "document.pdf",
  "doc_id": "document_pdf",
  "total_pages": 12,
  "extractable_pages": 12,
  "total_chunks": 47,
  "chunks_stored": 47,
  "needs_ocr": false,
  "upload_timestamp": "2025-01-15T10:30:00.000Z",
  "processing_time_ms": 3241,
  "vector_store_total": 47,
  "page_stats": [
    {"page_num": 1, "char_count": 1842, "is_empty": false},
    ...
  ]
}
```

---

### Test 3: Verify Storage via Swagger UI
Open http://localhost:8000/docs in your browser.
Click `GET /health` → Execute → check `total_chunks` increased.

---

### Test 4: Verify via Python (direct ChromaDB inspection)
```python
import chromadb

client = chromadb.PersistentClient(path="./data/chroma_db")
collection = client.get_collection("documents")

print(f"Total chunks: {collection.count()}")

# Peek at first 3 stored chunks
sample = collection.peek(limit=3)
for i, (doc_id, text, meta) in enumerate(zip(
    sample["ids"], sample["documents"], sample["metadatas"]
)):
    print(f"\n--- Chunk {i+1} ---")
    print(f"ID:       {doc_id}")
    print(f"File:     {meta['filename']}, Page {meta['page_num']}")
    print(f"Text:     {text[:150]}...")
```

---

## API Reference

### POST /api/v1/ingest/
Upload and ingest a PDF file.

**Request:** `multipart/form-data`
| Field | Type | Description |
|-------|------|-------------|
| file | File | PDF file to ingest |

**Response:** `IngestResponse`
| Field | Type | Description |
|-------|------|-------------|
| status | string | "success" or "warning" |
| filename | string | Original filename |
| doc_id | string | Unique document identifier |
| total_pages | int | Total PDF pages |
| extractable_pages | int | Pages with text content |
| total_chunks | int | Number of chunks created |
| chunks_stored | int | Number of chunks stored in ChromaDB |
| needs_ocr | bool | True if PDF appears to be scanned |
| processing_time_ms | int | Total processing time |
| vector_store_total | int | Total chunks in ChromaDB |

### GET /health
Returns system status and ChromaDB statistics.

---

## Common Issues and Fixes

### Issue: `ModuleNotFoundError: No module named 'fitz'`
```bash
pip install PyMuPDF
```
Note: The package is `PyMuPDF` but imports as `fitz`.

---

### Issue: `torch` not found / slow install
```bash
# CPU-only torch (faster install, ~800MB):
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Then install the rest:
pip install -r requirements.txt
```

---

### Issue: First embedding takes 30+ seconds
This is normal — BGE model (~130MB) downloads from HuggingFace on first use.
Subsequent runs use the local cache at `~/.cache/huggingface/`.

---

### Issue: `pydantic_settings` not found
```bash
pip install pydantic-settings
```
Note: In Pydantic v2, `BaseSettings` moved to a separate package.

---

### Issue: `422 Unprocessable Entity` on ingest
- Check the file is a valid PDF (not renamed from another format)
- Check Content-Type header: must be `multipart/form-data`
- Check field name is `file` (not `pdf`, not `document`)

---

### Issue: `total_chunks: 0` in health response
The ChromaDB collection is empty. Ingest a PDF first.
Or check that `CHROMA_PERSIST_DIR` in `.env` points to the correct directory.

---

### Issue: Same PDF ingested twice shows duplicate chunks
This is prevented — `upsert` (not `insert`) is used in ChromaDB.
The same chunk_id will overwrite itself, not create a duplicate.

---

### Issue: `needs_ocr: true` for a normal PDF
Some PDFs have minimal text (e.g., cover page only, mostly tables/images).
The threshold is 50+ characters per page. If your PDF is legitimate text but
returns `needs_ocr: true`, check `page_stats` in the response to see which
pages have low character counts.

---

## Free Model Notes

### BAAI/bge-small-en-v1.5
- **Cost:** Free forever (runs locally)
- **Size:** ~130MB (downloaded once to `~/.cache/huggingface/`)
- **Dimensions:** 384 (compact and fast)
- **Quality:** Excellent for retrieval on English text
- **Upgrade path:** Phase 4+ can switch to `bge-large-en-v1.5` (1024 dims, better quality)

### ChromaDB
- **Cost:** Free forever (open source)
- **Storage:** Local SQLite + HNSW index on disk
- **Limits:** No hard limits for local usage (millions of documents feasible)

---

## What's Coming in Future Phases

| Phase | Feature |
|-------|---------|
| 2 | LangGraph + basic RAG (question → retrieve → answer via Gemini free tier) |
| 3 | OCR support for scanned PDFs and images (Gemini Vision free tier) |
| 4 | Hybrid retrieval: BM25 + vector + reranking |
| 5 | Streamlit UI with streaming responses and citation display |
| 6 | Debug panel, timing metrics, retrieval visualization |
