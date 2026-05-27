"""
graph/state.py
--------------
Defines the GraphState TypedDict that flows through the LangGraph pipeline.

Feature 1 addition: doc_id (Optional[str])
  When set, the retrieve node passes it to HybridRetrievalService which
  applies a ChromaDB metadata filter so only chunks from that document
  are searched. None means "search all documents" (existing behaviour).
"""

from typing import TypedDict, List, Optional


class RetrievedSource(TypedDict):
    """
    One retrieved chunk's source information.
    Used to build the 'sources' list in the API response.
    """
    filename: str       # e.g. "annual_report.pdf"
    page: int           # 1-based page number
    chunk_id: str       # e.g. "annual_report_pdf_14"
    excerpt: str        # First 200 chars of the chunk text


class GraphState(TypedDict):
    """
    The complete state dictionary passed between LangGraph nodes.

    Field lifecycle:
      question         → set by the API route before graph runs; NEVER changed
      retrieval_query  → set by rewrite node; equals question if rewriting off
      chat_history     → set by API route; list of {"role", "content"} dicts
      doc_id           → set by API route; None = all docs, str = one doc filter
      retrieved_docs   → set by the retrieve node
      context          → set by the retrieve node (formatted string for LLM)
      sources          → set by the retrieve node (for API response)
      answer           → set by the generate node
      error            → set by any node that catches an exception
    """
    # ── Phase 2 (preserved unchanged) ─────────────────────────────────────────
    question: str
    retrieved_docs: List[dict]
    context: str
    sources: List[RetrievedSource]
    answer: str
    error: Optional[str]

    # ── Phase 3 additions ──────────────────────────────────────────────────────
    retrieval_query: str            # Search-optimised query (rewrite node output)
    chat_history: List[dict]        # [{"role": "user"|"assistant", "content": str}, ...]

    # ── Feature 1 addition ────────────────────────────────────────────────────
    doc_id: Optional[str]           # Filter retrieval to one doc; None = all docs
