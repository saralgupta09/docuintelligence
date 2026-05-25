"""
memory/conversation_manager.py
--------------------------------
Thread-safe in-memory session store for multi-turn conversation history.

Design:
  - Holds a dict of session_id → List[dict].
  - Each dict in the list is one "turn": {"role": "user"|"assistant", "content": str}.
  - threading.Lock guards all mutations so concurrent FastAPI requests can't
    corrupt the same session's message list.
  - MAX_MEMORY_TURNS is enforced on every add_turn() call: only the most
    recent N turns are retained, keeping memory bounded.
  - The entire internal dict is designed so it could be swapped for Redis
    calls later without touching any other file — the public API is the same.

Session lifecycle:
  1. API route generates a session_id (UUID) if the client didn't provide one.
  2. Before graph.invoke(), the route loads history via get_history().
  3. After graph.invoke(), the route saves Q&A via add_turn().
  4. The client receives session_id in the response and sends it back on the
     next request to continue the conversation.

No persistence:
  Sessions live in memory and are lost on server restart.  For production,
  swap this for a Redis backend by replacing the methods below.
"""

import threading
from typing import List, Dict, Optional

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Each turn is a dict with "role" and "content" keys
Turn = Dict[str, str]


class ConversationManager:
    """
    Thread-safe in-memory store for per-session conversation histories.

    Public methods:
      add_turn(session_id, role, content)  — append one message to a session
      get_history(session_id)              — return all stored turns
      format_for_prompt(session_id)        — return a string ready for LLM injection
      clear_session(session_id)            — delete all turns for a session
      session_count()                      — number of active sessions (diagnostics)
    """

    def __init__(self, max_turns: int = 5) -> None:
        # session_id → list of turns (each is {"role": ..., "content": ...})
        self._sessions: Dict[str, List[Turn]] = {}
        self._lock = threading.Lock()
        self._max_turns = max_turns

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        """
        Appends one message to a session's history.

        Args:
            session_id: Unique session identifier (UUID string).
            role:       "user" or "assistant".
            content:    The message text.

        After appending, trims the list so only the most recent
        (max_turns * 2) messages are kept.  Each turn consists of
        one user message + one assistant message, so max_turns turns
        = max_turns * 2 individual messages.
        """
        if role not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")

        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []

            self._sessions[session_id].append({"role": role, "content": content})

            # Trim to keep only the most recent messages (max_turns full turns)
            max_messages = self._max_turns * 2
            if len(self._sessions[session_id]) > max_messages:
                self._sessions[session_id] = self._sessions[session_id][-max_messages:]

        logger.debug(
            "Turn added to session",
            extra={
                "session_id": session_id[:8] + "...",
                "role": role,
                "session_length": len(self._sessions.get(session_id, [])),
            },
        )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_history(self, session_id: str) -> List[Turn]:
        """
        Returns all stored turns for a session.

        Returns [] if the session doesn't exist yet.
        The returned list is a shallow copy — safe to read, don't mutate it.
        """
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def format_for_prompt(self, session_id: str) -> str:
        """
        Formats conversation history as a multi-line string for LLM injection.

        Output format:
            User: What is the revenue?
            Assistant: According to report.pdf page 3, revenue was $1.2B.

            User: And the profit margin?
            Assistant: The margin was 18%, as stated on page 5.

        Returns an empty string "" if the session has no history yet.
        This lets the generate node include the block only when non-empty.
        """
        history = self.get_history(session_id)
        if not history:
            return ""

        lines = []
        for turn in history:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {turn['content']}")

        return "\n".join(lines)

    # ── Maintenance ───────────────────────────────────────────────────────────

    def clear_session(self, session_id: str) -> None:
        """Deletes all history for a session. Idempotent."""
        with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Session cleared", extra={"session_id": session_id[:8] + "..."})

    def session_count(self) -> int:
        """Returns the number of active sessions (for diagnostics / health checks)."""
        with self._lock:
            return len(self._sessions)


# ── Singleton ─────────────────────────────────────────────────────────────────
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """Returns the shared ConversationManager instance."""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager(
            max_turns=settings.MAX_MEMORY_TURNS
        )
    return _conversation_manager
