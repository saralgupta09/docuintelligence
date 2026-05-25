"""
services/llm_service.py
------------------------
Wraps Google Gemini 2.5 Flash for answer generation and query rewriting.

SDK: google-genai (new official SDK, not deprecated google-generativeai)

Free tier (as of 2025):
  Model:              gemini-2.5-flash
  Requests/day:       500
  Tokens/min:         1,000,000
  Input token limit:  1,048,576 per request
  Output token limit: 65,536

Phase 3 note on quota:
  Each /ask call now makes up to 2 Gemini calls (rewrite + generate) when
  ENABLE_QUERY_REWRITING=True.  Effective daily capacity drops to ~250 ask
  requests on the free tier.  Set ENABLE_QUERY_REWRITING=False to halve
  API usage during heavy testing.

Get your free API key at: https://aistudio.google.com/app/apikey
No credit card required.
"""

from typing import List

from google import genai
from google.genai import types

from config import settings
from utils.logger import get_logger, Timer

logger = get_logger(__name__)

# ── System instructions ───────────────────────────────────────────────────────
GENERATE_SYSTEM_INSTRUCTION = """You are DocuIntel, an AI assistant that answers questions using document context and conversation history.

Rules:
1. Use document context as the primary source of factual information.
2. Use conversation history to resolve references, pronouns, follow-up questions, and conversational continuity.
3. If the user refers to previous answers (e.g. "the second point", "that", "it", "the earlier one"), use conversation history to determine what they mean.
4. Never fabricate facts, statistics, names, or dates.
5. If insufficient information exists in both document context and conversation history, say clearly:
"I don't have enough information in the provided documents to answer this question."
6. When referencing specific information, mention source document and page when available.
7. Be concise and direct.
8. If multiple sources support an answer, synthesize them naturally.
"""
REWRITE_SYSTEM_INSTRUCTION = """You are a search query optimizer for a document retrieval system.

Your task: Convert the user's question into a concise, self-contained search query that will \
retrieve the most relevant document chunks.

Rules:
1. Output ONLY the rewritten query. No explanation, no preamble, no quotes.
2. Resolve pronouns and references using the conversation history \
   (e.g., "it", "that", "the second one" → the specific term they refer to).
3. Make the query standalone — it should make sense without the conversation history.
4. Keep it short: 5-15 words is ideal. Preserve key terms exactly.
5. If the question is already a clear standalone query, return it unchanged.
6. NEVER answer the question — only rewrite it as a search query."""


def format_context(retrieved_docs: list) -> str:
    """
    Converts retrieved chunks into a labeled context string for the LLM.

    Format:
        [Source 1: report.pdf | Page 3]
        <chunk text>

        ---

        [Source 2: notes.pdf | Page 7]
        <chunk text>

    Args:
        retrieved_docs: List of {'text': str, 'metadata': dict, 'distance': float}

    Returns:
        Formatted context string.
    """
    if not retrieved_docs:
        return "No relevant context was found in the uploaded documents."

    parts = []
    for i, doc in enumerate(retrieved_docs, start=1):
        meta = doc.get("metadata", {})
        label = (
            f"[Source {i}: {meta.get('filename', 'unknown')} | "
            f"Page {meta.get('page_num', '?')}]"
        )
        parts.append(f"{label}\n{doc['text']}")

    return "\n\n---\n\n".join(parts)


def build_prompt(question: str, context: str, chat_history_str: str = "") -> str:
    """
    Assembles the user message: conversation history + context blocks + question.

    Context-first ordering produces more grounded answers because
    the model processes the evidence before seeing the question.

    Args:
        question:         The original user question.
        context:          Formatted retrieved chunks string.
        chat_history_str: Pre-formatted conversation history (may be empty).
    """
    parts = []

    if chat_history_str.strip():
        parts.append(
            f"CONVERSATION HISTORY (use this for conversational continuity and reference resolution):\n"
            f"{'=' * 60}\n"
            f"{chat_history_str}\n"
            f"{'=' * 60}\n"
        )

    parts.append(
        f"DOCUMENT CONTEXT:\n"
        f"{'=' * 60}\n"
        f"{context}\n"
        f"{'=' * 60}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER:"
    )

    return "\n".join(parts)


def build_rewrite_prompt(question: str, chat_history: List[dict]) -> str:
    """
    Builds the prompt for the query rewriting call.

    Includes the last few turns of conversation history (up to 3 turns)
    so the model can resolve anaphoric references.

    Args:
        question:     The current user question.
        chat_history: List of {"role": str, "content": str} dicts.
    """
    # Only include the last 3 turns (6 messages) for the rewrite context
    recent = chat_history[-6:] if len(chat_history) > 6 else chat_history

    lines = []
    if recent:
        lines.append("Recent conversation:")
        for turn in recent:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"  {role_label}: {turn['content']}")
        lines.append("")

    lines.append(f"Current question: {question}")
    lines.append("\nRewritten search query:")

    return "\n".join(lines)


class LLMService:
    """
    Wraps Gemini 2.5 Flash for grounded document Q&A and query rewriting.
    Client is initialized lazily on first use.
    """

    def __init__(self) -> None:
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not settings.GEMINI_API_KEY:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. "
                    "Add it to your .env file. "
                    "Get a free key at: https://aistudio.google.com/app/apikey"
                )
            logger.info("Initializing Gemini client", extra={"model": settings.GEMINI_MODEL})
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    def generate(
        self,
        question: str,
        context: str,
        chat_history_str: str = "",
    ) -> str:
        """
        Generates a grounded answer using Gemini and the retrieved context.

        Args:
            question:         The user's original question.
            context:          Formatted context string (retrieved chunks).
            chat_history_str: Pre-formatted conversation history string.
                              Pass "" if no history (Phase 2 backward compat).

        Returns:
            LLM response text.

        Raises:
            RuntimeError: If the Gemini API key is missing or API call fails.
        """
        prompt = build_prompt(question, context, chat_history_str)

        logger.info(
            "Sending generate request to Gemini",
            extra={
                "model": settings.GEMINI_MODEL,
                "context_chars": len(context),
                "prompt_chars": len(prompt),
                "question_preview": question[:80],
                "has_history": bool(chat_history_str.strip()),
            },
        )

        try:
            with Timer() as llm_timer:
                client = self._get_client()
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=GENERATE_SYSTEM_INSTRUCTION,
                        temperature=0.1,        # Low = factual, less creative
                        max_output_tokens=1024,
                    ),
                )
        except Exception as e:
            logger.error("Gemini generate API call failed", extra={"error": str(e)})
            raise RuntimeError(f"LLM generation failed: {str(e)}") from e

        answer = response.text or ""

        if not answer.strip():
            logger.warning("Gemini returned empty response")
            answer = (
                "I was unable to generate an answer. "
                "Please try rephrasing your question."
            )

        logger.info(
            "Answer generated",
            extra={
                "answer_chars": len(answer),
                "elapsed_ms": llm_timer.elapsed_ms,
            },
        )

        return answer.strip()

    def rewrite_query(
        self,
        question: str,
        chat_history: List[dict],
    ) -> str:
        """
        Rewrites the user's question into a search-optimised standalone query.

        Uses a lightweight Gemini call with max_output_tokens=100 (the typical
        rewritten query is 5-15 tokens).  This keeps the call cheap and fast.

        Args:
            question:     The user's original question.
            chat_history: List of {"role": str, "content": str} dicts.

        Returns:
            Rewritten query string (may be identical to question if no rewrite
            was needed).

        Raises:
            RuntimeError: If the Gemini API key is missing or API call fails.
        """
        prompt = build_rewrite_prompt(question, chat_history)

        logger.info(
            "Sending rewrite request to Gemini",
            extra={
                "model": settings.GEMINI_MODEL,
                "question_preview": question[:80],
                "history_msgs": len(chat_history),
            },
        )

        try:
            with Timer() as t:
                client = self._get_client()
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=REWRITE_SYSTEM_INSTRUCTION,
                        temperature=0.0,          # Deterministic for rewriting
                        max_output_tokens=100,    # Rewritten queries are short
                    ),
                )
        except Exception as e:
            logger.error("Gemini rewrite API call failed", extra={"error": str(e)})
            raise RuntimeError(f"Query rewrite failed: {str(e)}") from e

        rewritten = (response.text or "").strip()

        logger.info(
            "Query rewrite complete",
            extra={
                "original": question[:60],
                "rewritten": rewritten[:60],
                "elapsed_ms": t.elapsed_ms,
            },
        )

        return rewritten


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Returns the shared LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
