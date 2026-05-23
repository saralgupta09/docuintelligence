"""
graph/retrieval_graph.py
-------------------------
Defines and compiles the Phase 2 LangGraph retrieval workflow.

Graph structure:
  START → retrieve → generate → END

  That's it. No loops, no conditionals, no agents.
  Simple sequential pipeline — exactly what Phase 2 needs.

Why LangGraph for a simple 2-step pipeline?
  1. It makes the pipeline inspectable (you can print the graph structure)
  2. Phase 4+ adds conditional routing (reranking, hybrid retrieval)
     without restructuring any existing code — just add new nodes
  3. State management is explicit (every field is typed and tracked)
  4. Each node is testable in isolation

How to use this module:
  from graph.retrieval_graph import get_retrieval_graph, create_initial_state

  graph = get_retrieval_graph()
  result = graph.invoke(create_initial_state("What is the revenue?"))

  print(result["answer"])
  print(result["sources"])
"""

from functools import lru_cache

from langgraph.graph import StateGraph, START, END

from graph.state import GraphState
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

    The compiled graph is a standard Python callable:
      result = compiled_graph.invoke(initial_state)
    """
    logger.info("Building retrieval graph")

    # ── 1. Create the graph ───────────────────────────────────────────────────
    # StateGraph(GraphState) tells LangGraph which TypedDict to use for state.
    # LangGraph validates that nodes return keys defined in GraphState.
    workflow = StateGraph(GraphState)

    # ── 2. Register nodes ─────────────────────────────────────────────────────
    # add_node("name", function)
    # The function signature must be: func(state: GraphState) -> dict
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    # ── 3. Define edges (execution order) ─────────────────────────────────────
    # START is a special built-in entry point marker
    # END is a special built-in exit point marker

    workflow.add_edge(START, "retrieve")   # First node to run
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)     # Last node to run

    # ── 4. Compile ────────────────────────────────────────────────────────────
    # compile() validates the graph structure and returns a CompiledStateGraph
    # The compiled graph can be invoked like a regular function
    compiled = workflow.compile()

    logger.info(
        "Retrieval graph compiled",
        extra={"nodes": ["retrieve", "generate"], "flow": "START→retrieve→generate→END"},
    )

    return compiled


@lru_cache(maxsize=1)
def get_retrieval_graph():
    """
    Returns the compiled retrieval graph.
    Uses @lru_cache so the graph is built only once per process.
    Building the graph is cheap, but caching it is clean practice.
    """
    return build_retrieval_graph()


def create_initial_state(question: str) -> GraphState:
    """
    Creates the initial state dict to pass into graph.invoke().

    All fields must be present in the initial state — LangGraph
    requires the TypedDict to be fully initialized before the first node runs.

    Args:
        question: The user's question string.

    Returns:
        A fully-initialized GraphState with empty/default values for all fields
        except 'question', which is set to the provided value.
    """
    return GraphState(
        question=question,
        retrieved_docs=[],
        context="",
        sources=[],
        answer="",
        error=None,
    )
