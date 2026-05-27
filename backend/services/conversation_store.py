import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, file_path: str) -> None:
        self._file_path = Path(file_path)
        self._lock = threading.Lock()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read()
            conversations = list(data.values())

        conversations.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return [self._summary(item) for item in conversations]

    def get_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._read()
            conversation = data.get(session_id)

        return deepcopy(conversation) if conversation else None

    def upsert_conversation(
        self,
        session_id: str,
        *,
        title: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        selected_document: Optional[Dict[str, Any]] = None,
        preview_document: Optional[Dict[str, Any]] = None,
        retrieved_sources: Optional[List[Dict[str, Any]]] = None,
        highlights: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()

        with self._lock:
            data = self._read()
            existing = data.get(session_id, {})

            conversation = {
                "session_id": session_id,
                "title": title or existing.get("title") or self._derive_title(messages),
                "created_at": existing.get("created_at") or now,
                "updated_at": now,
                "messages": messages if messages is not None else existing.get("messages", []),
                "selected_document": (
                    selected_document
                    if selected_document is not None
                    else existing.get("selected_document")
                ),
                "preview_document": (
                    preview_document
                    if preview_document is not None
                    else existing.get("preview_document")
                ),
                "retrieved_sources": (
                    retrieved_sources
                    if retrieved_sources is not None
                    else existing.get("retrieved_sources", [])
                ),
                "highlights": (
                    highlights
                    if highlights is not None
                    else existing.get("highlights", [])
                ),
            }

            data[session_id] = conversation
            self._write(data)

        return deepcopy(conversation)

    def append_turn(
        self,
        session_id: str,
        *,
        user_message: Dict[str, Any],
        assistant_message: Dict[str, Any],
        selected_document: Optional[Dict[str, Any]] = None,
        preview_document: Optional[Dict[str, Any]] = None,
        retrieved_sources: Optional[List[Dict[str, Any]]] = None,
        highlights: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()

        with self._lock:
            data = self._read()
            existing = data.get(session_id, {})

            messages = list(existing.get("messages", []))
            messages.extend([user_message, assistant_message])

            conversation = {
                "session_id": session_id,
                "title": existing.get("title") or self._derive_title(messages),
                "created_at": existing.get("created_at") or now,
                "updated_at": now,
                "messages": messages,
                "selected_document": (
                    selected_document
                    if selected_document is not None
                    else existing.get("selected_document")
                ),
                "preview_document": (
                    preview_document
                    if preview_document is not None
                    else existing.get("preview_document")
                ),
                "retrieved_sources": (
                    retrieved_sources
                    if retrieved_sources is not None
                    else existing.get("retrieved_sources", [])
                ),
                "highlights": (
                    highlights
                    if highlights is not None
                    else existing.get("highlights", [])
                ),
            }

            data[session_id] = conversation
            self._write(data)

        return deepcopy(conversation)

    def delete_conversation(self, session_id: str) -> bool:
        with self._lock:
            data = self._read()
            existed = session_id in data
            data.pop(session_id, None)
            self._write(data)

        return existed

    def _read(self) -> Dict[str, Dict[str, Any]]:
        if not self._file_path.exists():
            return {}

        try:
            with self._file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            logger.warning(
                "Conversation store JSON was invalid; starting with empty store",
                extra={"path": str(self._file_path)},
            )
            return {}

        if not isinstance(data, dict):
            return {}

        return data

    def _write(self, data: Dict[str, Dict[str, Any]]) -> None:
        temp_path = self._file_path.with_suffix(".tmp")

        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        temp_path.replace(self._file_path)

    def _summary(self, conversation: Dict[str, Any]) -> Dict[str, Any]:
        selected_document = conversation.get("selected_document") or {}

        return {
            "session_id": conversation.get("session_id"),
            "title": conversation.get("title") or "New chat",
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "message_count": len(conversation.get("messages", [])),
            "selected_document": conversation.get("selected_document"),
            "selected_document_name": selected_document.get("filename"),
        }

    def _derive_title(self, messages: Optional[List[Dict[str, Any]]]) -> str:
        if not messages:
            return "New chat"

        for message in messages:
            if message.get("role") == "user" and message.get("content"):
                title = str(message["content"]).strip()
                return title[:48] + ("..." if len(title) > 48 else "")

        return "New chat"


_conversation_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    global _conversation_store

    if _conversation_store is None:
        _conversation_store = ConversationStore(settings.CONVERSATION_STORE_PATH)

    return _conversation_store