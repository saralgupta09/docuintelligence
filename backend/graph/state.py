"""
graph/state.py
--------------
Defines the GraphState TypedDict that flows through the LangGraph pipeline.

LangGraph passes one state dict between all nodes.
Each node reads from state and returns a dict of only the fields it changed.
LangGraph merges those updates back automatically.

Phase 3 adds:
  retrieval_query  — the search-optimised query produced by the rewrite node.
                     Differs from 'question' when rewriting is active.
  chat_history     — prior conversation turns injected by the API route.
                     Consumed by the generate node to maintain context.
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
      retrieved_docs   → set by the retrieve node
      context          → set by the retrieve node (formatted string for LLM)
      sources          → set by the retrieve node (for API response)
      answer           → set by the generate node
      error            → set by any node that catches an exception

    Key invariant:
      'question' is what the user typed.  'retrieval_query' is what gets
      passed to the vector + BM25 search.  The generate node always uses
      'question' so the LLM answers what the user actually asked.
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
