"""
graph/retrieval_graph.py
-------------------------
Defines and compiles the Phase 3 LangGraph retrieval workflow.

Feature 1 change: create_initial_state() now accepts an optional doc_id
parameter and passes it into GraphState. When provided, the retrieve node
uses it to filter ChromaDB results to that document only.
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
    logger.info("Building retrieval graph (Phase 3)")

    workflow = StateGraph(GraphState)

    workflow.add_node("rewrite", rewrite)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    workflow.add_edge(START, "rewrite")
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

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
    return build_retrieval_graph()


def create_initial_state(
    question: str,
    chat_history: list | None = None,
    doc_id: str | None = None,          # Feature 1: optional document filter
) -> GraphState:
    """
    Creates the initial state dict to pass into graph.invoke().

    Args:
        question:     The user's question string.
        chat_history: Prior conversation turns from ConversationManager.
        doc_id:       When provided, retrieval is scoped to this document only.
                      None (default) keeps the existing all-documents behaviour.
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
        retrieval_query=question,
        chat_history=chat_history or [],
        # Feature 1
        doc_id=doc_id,
    )
