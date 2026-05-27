from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.conversation_store import get_conversation_store

router = APIRouter(prefix="/conversations", tags=["Conversations"])


class ConversationSnapshot(BaseModel):
    session_id: str
    title: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    selected_document: Optional[Dict[str, Any]] = None
    preview_document: Optional[Dict[str, Any]] = None
    retrieved_sources: List[Dict[str, Any]] = Field(default_factory=list)
    highlights: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/")
def list_conversations() -> Dict[str, Any]:
    store = get_conversation_store()
    conversations = store.list_conversations()

    return {
        "conversations": conversations,
        "total": len(conversations),
    }


@router.get("/{session_id}")
def get_conversation(session_id: str) -> Dict[str, Any]:
    store = get_conversation_store()
    conversation = store.get_conversation(session_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found for session_id '{session_id}'.",
        )

    return conversation


@router.put("/{session_id}")
def save_conversation(session_id: str, snapshot: ConversationSnapshot) -> Dict[str, Any]:
    if snapshot.session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="Path session_id must match request body session_id.",
        )

    store = get_conversation_store()
    conversation = store.upsert_conversation(
        session_id,
        title=snapshot.title,
        messages=snapshot.messages,
        selected_document=snapshot.selected_document,
        preview_document=snapshot.preview_document,
        retrieved_sources=snapshot.retrieved_sources,
        highlights=snapshot.highlights,
    )

    return conversation


@router.delete("/{session_id}")
def delete_conversation(session_id: str) -> Dict[str, Any]:
    store = get_conversation_store()
    deleted = store.delete_conversation(session_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No conversation found for session_id '{session_id}'.",
        )

    return {
        "status": "deleted",
        "session_id": session_id,
    }