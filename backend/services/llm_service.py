"""
services/llm_service.py
------------------------
Wraps Google Gemini 2.5 Flash for answer generation.

SDK: google-genai (new official SDK, not deprecated google-generativeai)

Free tier (as of 2025):
  Model:              gemini-2.5-flash
  Requests/day:       500
  Tokens/min:         1,000,000
  Input token limit:  1,048,576 per request
  Output token limit: 65,536

Get your free API key at: https://aistudio.google.com/app/apikey
No credit card required.

If you hit the 500 req/day limit during heavy testing, set in .env:
  GEMINI_MODEL=gemini-1.5-flash   (also free, very capable)
"""

from google import genai
from google.genai import types

from config import settings
from utils.logger import get_logger, Timer

logger = get_logger(__name__)

# System instruction: defines the model's role and grounding rules.
SYSTEM_INSTRUCTION = """You are DocuIntel, an AI assistant that answers questions \
strictly based on the provided document context.

Rules:
1. Answer ONLY using information present in the context blocks below.
2. If the context does not contain enough information, say clearly: \
"I don't have enough information in the provided documents to answer this question."
3. Never fabricate facts, statistics, names, or dates.
4. When referencing specific information, mention the source document and page \
(e.g., "According to report.pdf, page 3...").
5. Be concise and direct.
6. If multiple sources support the answer, synthesize them into a unified response."""


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


def build_prompt(question: str, context: str) -> str:
    """
    Assembles the user message: context blocks + question.

    Context-first ordering produces more grounded answers because
    the model processes the evidence before seeing the question.
    """
    return (
        f"DOCUMENT CONTEXT:\n"
        f"{'=' * 60}\n"
        f"{context}\n"
        f"{'=' * 60}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER:"
    )


class LLMService:
    """
    Wraps Gemini 2.5 Flash for grounded document question-answering.
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
    ) -> str:
        """
        Generates a grounded answer using Gemini and the retrieved context.

        Args:
            question: The user's question.
            context:  Formatted context string (retrieved chunks).

        Returns:
            LLM response text.

        Raises:
            RuntimeError: If the Gemini API key is missing or API call fails.
        """
        prompt = build_prompt(question, context)

        logger.info(
            "Sending request to Gemini",
            extra={
                "model": settings.GEMINI_MODEL,
                "context_chars": len(context),
                "prompt_chars": len(prompt),
                "question_preview": question[:80],
            },
        )

        try:
            with Timer() as llm_timer:
                client = self._get_client()
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.1,        # Low = factual, less creative
                        max_output_tokens=1024,
                    ),
                )
        except Exception as e:
            logger.error("Gemini API call failed", extra={"error": str(e)})
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


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Returns the shared LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
