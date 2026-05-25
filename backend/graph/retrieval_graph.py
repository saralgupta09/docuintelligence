"""
graph/retrieval_graph.py
-------------------------
Defines and compiles the Phase 3 LangGraph retrieval workflow.

Phase 3 graph structure:
  START → rewrite → retrieve → generate → END

  rewrite:  Converts the user's question into a search-optimised standalone
            query using conversation history.  Falls back to original question
            if Gemini fails or rewriting is disabled.
  retrieve: Runs hybrid BM25 + vector search using the rewritten query.
  generate: Injects chat history into the LLM prompt and produces the answer.

Backward compatibility:
  create_initial_state() now accepts an optional chat_history parameter.
  Callers that don't pass it (Phase 2 tests) get [] by default.
  All state fields have defaults so no existing node code breaks.
"""

from functools import lru_cache

from langgraph.graph import StateGraph, START, END

from graph.state import GraphState
from graph.nodes.rewrite import rewrite
from graph.nodes.retrieve import retrieve
from graph.nodes.generate import generate
from utils.logger import get_logger

logger = get_logger(__name__)


def build_retrieval_graph():
    """
    Builds and compiles the retrieval LangGraph.

    Build steps:
    1. Create a StateGraph typed with GraphState
    2. Register each node (name + function)
    3. Define edges (the execution order)
    4. Compile (validates the graph, returns a runnable)
    """
    logger.info("Building retrieval graph (Phase 3)")

    # ── 1. Create the graph ───────────────────────────────────────────────────
    workflow = StateGraph(GraphState)

    # ── 2. Register nodes ─────────────────────────────────────────────────────
    workflow.add_node("rewrite", rewrite)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    # ── 3. Define edges ───────────────────────────────────────────────────────
    workflow.add_edge(START, "rewrite")      # Phase 3: rewrite is the entry point
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    # ── 4. Compile ────────────────────────────────────────────────────────────
    compiled = workflow.compile()

    logger.info(
        "Retrieval graph compiled",
        extra={
            "nodes": ["rewrite", "retrieve", "generate"],
            "flow": "START→rewrite→retrieve→generate→END",
        },
    )

    return compiled


@lru_cache(maxsize=1)
def get_retrieval_graph():
    """
    Returns the compiled retrieval graph.
    Uses @lru_cache so the graph is built only once per process.
    """
    return build_retrieval_graph()


def create_initial_state(
    question: str,
    chat_history: list | None = None,
) -> GraphState:
    """
    Creates the initial state dict to pass into graph.invoke().

    All fields must be present — LangGraph requires the TypedDict to be fully
    initialised before the first node runs.

    Args:
        question:     The user's question string.
        chat_history: List of {"role": str, "content": str} dicts from
                      ConversationManager.  Pass None (or omit) for Phase 2
                      backward compatibility.

    Returns:
        A fully-initialised GraphState.
    """
    return GraphState(
        # Phase 2 fields (unchanged)
        question=question,
        retrieved_docs=[],
        context="",
        sources=[],
        answer="",
        error=None,
        # Phase 3 fields
        retrieval_query=question,       # Default: same as question; rewrite node overrides
        chat_history=chat_history or [],
    )
